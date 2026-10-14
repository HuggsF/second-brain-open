/**
 * @file BlingSalesAnalytics.js
 * @description Serviço de Analytics de Vendas & Operações integrado à API v3 do Bling e ao banco hub.db.
 * Agrega faturamento, ticket médio, curva temporal diária, breakdown por canal/loja,
 * top SKUs vendidos e funil de fulfillment logístico (Bling -> Hub -> J&T).
 */

class BlingSalesAnalyticsService {
  /**
   * @param {object} params
   * @param {import('./BlingV3Connector').BlingV3Connector} params.blingConnector
   * @param {object} [params.db] Conexão com SQLite hub.db (opcional)
   * @param {number} [params.cacheTtlMs=300000] TTL do cache em ms (padrão 5 min)
   */
  constructor(params) {
    if (!params.blingConnector) {
      throw new Error('blingConnector é obrigatório para BlingSalesAnalyticsService');
    }
    this.bling = params.blingConnector;
    this.db = params.db || null;
    this.cacheTtlMs = params.cacheTtlMs ?? (5 * 60 * 1000); // 5 minutos
    this.cache = new Map();
  }

  /**
   * Formata uma data no formato AAAA-MM-DD
   * @param {Date|string} date 
   */
  _formatDate(date) {
    const d = new Date(date);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  /**
   * Obtém nomes amigáveis das lojas cadastradas no Hub ou fallback.
   */
  async _getStoreNamesMap() {
    const map = {
      206084387: 'KIOSK RECIFE (Touti PE)',
      206085936: 'KIOSK ESPIRITO SANTO (Touti ES)',
      206133846: 'Shopify E-Commerce',
      206171604: 'TikTok Shop (Essência Mariana)',
      206236677: 'Mercado Livre - Oficial',
      206264482: 'Yampi (Essência Mariana)',
      206271368: 'API Transportadora',
      206281888: 'Shopify Secundário',
      206288765: 'Yes! Cosmetics',
      206293377: 'Bonificado Recife'
    };

    if (this.db) {
      try {
        const rows = await new Promise((resolve, reject) => {
          this.db.all('SELECT id_bling, nome FROM lojas', (err, rows) => {
            if (err) reject(err);
            else resolve(rows || []);
          });
        });
        for (const row of rows) {
          map[row.id_bling] = row.nome;
        }
      } catch (_) {
        // Usa mapa padrão se falhar a consulta ao SQLite
      }
    }

    return map;
  }

  /**
   * Busca dados da fila do Hub para calcular o funil logístico de fulfillment.
   * @param {string} startDate 
   * @param {string} endDate 
   */
  async _getHubFulfillmentStats(startDate, endDate) {
    if (!this.db) {
      return {
        queuedTotal: 0,
        labelsGenerated: 0,
        pendingInQueue: 0,
        failedQueue: 0,
        fulfillmentRatePercent: 0
      };
    }

    return new Promise((resolve) => {
      const sql = `
        SELECT 
          COUNT(*) as queuedTotal,
          SUM(CASE WHEN status = 'success' OR tracking_number IS NOT NULL THEN 1 ELSE 0 END) as labelsGenerated,
          SUM(CASE WHEN status = 'pending' OR status = 'processing' THEN 1 ELSE 0 END) as pendingInQueue,
          SUM(CASE WHEN status LIKE 'failed%' THEN 1 ELSE 0 END) as failedQueue
        FROM orders_queue
        WHERE created_at >= ? AND created_at <= ?
      `;

      this.db.get(sql, [`${startDate} 00:00:00`, `${endDate} 23:59:59`], (err, row) => {
        if (err || !row) {
          resolve({
            queuedTotal: 0,
            labelsGenerated: 0,
            pendingInQueue: 0,
            failedQueue: 0,
            fulfillmentRatePercent: 0
          });
        } else {
          const total = row.queuedTotal || 0;
          const generated = row.labelsGenerated || 0;
          const rate = total > 0 ? Number(((generated / total) * 100).toFixed(1)) : 0;
          resolve({
            queuedTotal: total,
            labelsGenerated: generated,
            pendingInQueue: row.pendingInQueue || 0,
            failedQueue: row.failedQueue || 0,
            fulfillmentRatePercent: rate
          });
        }
      });
    });
  }

  /**
   * Consulta a lista de pedidos no Bling API v3.
   * Pagina os resultados respeitando o rate-limit do conector.
   * @param {object} params
   * @param {string} params.startDate AAAA-MM-DD
   * @param {string} params.endDate AAAA-MM-DD
   * @param {number|string} [params.storeId]
   * @param {number|string} [params.statusId=9] 9 = Atendido (faturado/pronto para expedição)
   * @param {number} [params.maxPages=5] Limite de páginas para segurança
   */
  async fetchRawOrdersFromBling({ startDate, endDate, storeId, statusId = 9, maxPages = 5 }) {
    const token = await this.bling.getValidAccessToken();
    const orders = [];
    let page = 1;
    let hasMore = true;

    while (hasMore && page <= maxPages) {
      let url = `${this.bling.baseUrl}/pedidos/vendas?pagina=${page}&limite=100&dataInicial=${startDate}&dataFinal=${endDate}`;
      if (statusId) url += `&idsSituacoes[]=${statusId}`;
      if (storeId) url += `&idLoja=${storeId}`;

      const res = await this.bling._request({
        url,
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Accept': 'application/json'
        }
      });

      const items = res.data?.data || [];
      if (!Array.isArray(items) || items.length === 0) {
        hasMore = false;
      } else {
        orders.push(...items);
        if (items.length < 100) {
          hasMore = false;
        } else {
          page++;
        }
      }
    }

    return orders;
  }

  /**
   * Retorna os Analytics de Vendas agregados para o período solicitado.
   * Possui suporte a cache em memória com invalidação forçada.
   * @param {object} [options]
   * @param {string|Date} [options.startDate] Padrão: 30 dias atrás
   * @param {string|Date} [options.endDate] Padrão: Hoje
   * @param {string|number} [options.storeId]
   * @param {string|number} [options.statusId=9]
   * @param {boolean} [options.forceRefresh=false]
   */
  async getSalesAnalytics(options = {}) {
    const today = new Date();
    const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);

    const startDate = options.startDate ? this._formatDate(options.startDate) : this._formatDate(thirtyDaysAgo);
    const endDate = options.endDate ? this._formatDate(options.endDate) : this._formatDate(today);
    const storeId = options.storeId ? String(options.storeId) : null;
    const statusId = options.statusId ?? 9; // 9 = Atendido

    const cacheKey = `${startDate}_${endDate}_${storeId || 'ALL'}_${statusId}`;

    if (!options.forceRefresh && this.cache.has(cacheKey)) {
      const cached = this.cache.get(cacheKey);
      if (Date.now() - cached.timestamp < this.cacheTtlMs) {
        return { ...cached.data, fromCache: true, cachedAt: new Date(cached.timestamp).toISOString() };
      }
    }

    // 1. Busca os dados brutos no Bling
    const rawOrders = await this.fetchRawOrdersFromBling({ startDate, endDate, storeId, statusId });

    // 2. Mapeamento de lojas
    const storeNamesMap = await this._getStoreNamesMap();

    // 3. Agregação Geral
    let totalRevenue = 0;
    let totalShippingCost = 0;
    let totalProductsQty = 0;
    const timelineMap = new Map();
    const storeMap = new Map();
    const productMap = new Map();

    for (const order of rawOrders) {
      const orderTotal = Number(order.total) || 0;
      const shipping = Number(order.transporte?.frete) || 0;
      const orderDate = (order.data || order.dataSaida || startDate).split('T')[0];

      totalRevenue += orderTotal;
      totalShippingCost += shipping;

      // Agregação na Linha do Tempo (por dia)
      if (!timelineMap.has(orderDate)) {
        timelineMap.set(orderDate, { date: orderDate, revenue: 0, ordersCount: 0 });
      }
      const tEntry = timelineMap.get(orderDate);
      tEntry.revenue += orderTotal;
      tEntry.ordersCount += 1;

      // Agregação por Loja/Canal
      const sId = String(order.loja?.id || 'SEM_LOJA');
      const sName = storeNamesMap[sId] || `Loja ID ${sId}`;
      if (!storeMap.has(sId)) {
        storeMap.set(sId, { storeId: sId, storeName: sName, revenue: 0, ordersCount: 0 });
      }
      const sEntry = storeMap.get(sId);
      sEntry.revenue += orderTotal;
      sEntry.ordersCount += 1;

      // Agregação de Produtos (se vierem no payload do pedido)
      if (Array.isArray(order.itens)) {
        for (const item of order.itens) {
          const sku = item.codigo || item.id || 'SKU_INDEFINIDO';
          const qty = Number(item.quantidade) || 1;
          const val = Number(item.valor) || 0;
          totalProductsQty += qty;

          if (!productMap.has(sku)) {
            productMap.set(sku, {
              sku,
              name: item.descricao || sku,
              quantity: 0,
              revenue: 0
            });
          }
          const pEntry = productMap.get(sku);
          pEntry.quantity += qty;
          pEntry.revenue += (val * qty);
        }
      }
    }

    const totalOrders = rawOrders.length;
    const averageTicket = totalOrders > 0 ? Number((totalRevenue / totalOrders).toFixed(2)) : 0;
    const averageShippingPerOrder = totalOrders > 0 ? Number((totalShippingCost / totalOrders).toFixed(2)) : 0;

    // Converte e ordena a Linha do Tempo
    const timeline = Array.from(timelineMap.values()).sort((a, b) => a.date.localeCompare(b.date));

    // Converte e ordena Canais por Faturamento
    const byStore = Array.from(storeMap.values())
      .map(store => ({
        ...store,
        revenue: Number(store.revenue.toFixed(2)),
        sharePercentage: totalRevenue > 0 ? Number(((store.revenue / totalRevenue) * 100).toFixed(1)) : 0
      }))
      .sort((a, b) => b.revenue - a.revenue);

    // Top 5 SKUs
    const topProducts = Array.from(productMap.values())
      .map(p => ({
        ...p,
        revenue: Number(p.revenue.toFixed(2))
      }))
      .sort((a, b) => b.revenue - a.revenue)
      .slice(0, 5);

    // 4. Integração com Fila do Hub (Fulfillment SLA)
    const hubFulfillment = await this._getHubFulfillmentStats(startDate, endDate);

    const result = {
      period: { startDate, endDate },
      summary: {
        totalRevenue: Number(totalRevenue.toFixed(2)),
        totalOrders,
        averageTicket,
        totalShippingCost: Number(totalShippingCost.toFixed(2)),
        averageShippingPerOrder,
        totalProductsSold: totalProductsQty
      },
      fulfillment: hubFulfillment,
      byStore,
      topProducts,
      timeline,
      fromCache: false,
      calculatedAt: new Date().toISOString()
    };

    // Salva no cache
    this.cache.set(cacheKey, { timestamp: Date.now(), data: result });

    return result;
  }

  /**
   * Limpa o cache de analytics.
   */
  clearCache() {
    this.cache.clear();
  }
}

module.exports = {
  BlingSalesAnalyticsService
};
