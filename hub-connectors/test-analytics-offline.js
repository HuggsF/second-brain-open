/**
 * @file test-analytics-offline.js
 * @description Testes automatizados para o serviço BlingSalesAnalyticsService.
 * Valida agregação financeira, ticket médio, breakdown por canal, timeline e cache.
 */

const assert = require('assert');
const { BlingV3Connector, BlingSalesAnalyticsService } = require('./index');

let testsPassed = 0;
let testsFailed = 0;

function it(title, fn) {
  try {
    const result = fn();
    if (result && typeof result.then === 'function') {
      return result.then(() => {
        console.log(`  ✅ [PASS] ${title}`);
        testsPassed++;
      }).catch(err => {
        console.error(`  ❌ [FAIL] ${title}: ${err.message}`);
        testsFailed++;
      });
    }
    console.log(`  ✅ [PASS] ${title}`);
    testsPassed++;
    return Promise.resolve();
  } catch (err) {
    console.error(`  ❌ [FAIL] ${title}: ${err.message}`);
    testsFailed++;
    return Promise.resolve();
  }
}

async function run() {
  console.log('\n============================================================');
  console.log('🧪 SUÍTE DE TESTES: BLING SALES & LOGISTICS ANALYTICS');
  console.log('============================================================\n');

  // MOCK de dados de pedidos de venda retornados pelo Bling
  const mockBlingOrders = [
    {
      id: 101,
      numero: 1001,
      data: '2026-10-10',
      total: 200.00,
      loja: { id: 206085936 }, // KIOSK ESPIRITO SANTO
      transporte: { frete: 25.00 },
      itens: [
        { codigo: 'TOUTI-VIP-50', descricao: 'Perfume Touti VIP 50ml', quantidade: 2, valor: 100.00 }
      ]
    },
    {
      id: 102,
      numero: 1002,
      data: '2026-10-10',
      total: 100.00,
      loja: { id: 206084387 }, // KIOSK RECIFE
      transporte: { frete: 15.00 },
      itens: [
        { codigo: 'AMAVIA-SHAMP', descricao: 'Shampoo Amavia 250ml', quantidade: 1, valor: 100.00 }
      ]
    },
    {
      id: 103,
      numero: 1003,
      data: '2026-10-11',
      total: 300.00,
      loja: { id: 206085936 }, // KIOSK ESPIRITO SANTO
      transporte: { frete: 30.00 },
      itens: [
        { codigo: 'TOUTI-VIP-50', descricao: 'Perfume Touti VIP 50ml', quantidade: 3, valor: 100.00 }
      ]
    },
    {
      id: 104,
      numero: 1004,
      data: '2026-10-12',
      total: 400.00,
      loja: { id: 206133846 }, // Shopify
      transporte: { frete: 50.00 },
      itens: [
        { codigo: 'YES-BATOM-RED', descricao: 'Batom Yes! Red Velvet', quantidade: 4, valor: 100.00 }
      ]
    }
  ];

  const mockHttp = {
    request: async (opts) => {
      if (opts.url.includes('/pedidos/vendas')) {
        return {
          status: 200,
          data: {
            data: mockBlingOrders
          }
        };
      }
      throw new Error(`Rota inesperada: ${opts.url}`);
    }
  };

  const fakeBling = new BlingV3Connector({
    id: 1,
    config: {
      clientId: 'id',
      clientSecret: 'sec',
      accessToken: 'TOKEN_VALIDO',
      expiresAt: Date.now() + 3600000
    },
    httpClient: mockHttp
  });

  // Mock de banco SQLite para a fila orders_queue
  const mockDb = {
    all: (sql, cb) => cb(null, [
      { id_bling: 206085936, nome: 'KIOSK ESPIRITO SANTO' },
      { id_bling: 206084387, nome: 'KIOSK RECIFE' },
      { id_bling: 206133846, nome: 'Shopify E-Commerce' }
    ]),
    get: (sql, params, cb) => cb(null, {
      queuedTotal: 4,
      labelsGenerated: 3,
      pendingInQueue: 1,
      failedQueue: 0
    })
  };

  const analyticsService = new BlingSalesAnalyticsService({
    blingConnector: fakeBling,
    db: mockDb,
    cacheTtlMs: 2000 // 2 segundos para testar cache
  });

  // ----------------------------------------------------
  // TESTE 1: Agregação Financeira e Ticket Médio
  // ----------------------------------------------------
  await it('BlingSalesAnalytics: Calcula GMV Total (R$ 1000) e Ticket Médio (R$ 250)', async () => {
    const res = await analyticsService.getSalesAnalytics({
      startDate: '2026-10-10',
      endDate: '2026-10-12'
    });

    assert.strictEqual(res.summary.totalRevenue, 1000.00, 'GMV Total deve ser 1000.00');
    assert.strictEqual(res.summary.totalOrders, 4, 'Total de pedidos deve ser 4');
    assert.strictEqual(res.summary.averageTicket, 250.00, 'Ticket médio deve ser 250.00');
    assert.strictEqual(res.summary.totalShippingCost, 120.00, 'Custo de frete deve ser 120.00');
    assert.strictEqual(res.summary.averageShippingPerOrder, 30.00, 'Custo médio de frete deve ser 30.00');
  });

  // ----------------------------------------------------
  // TESTE 2: Breakdown por Loja / Canal
  // ----------------------------------------------------
  await it('BlingSalesAnalytics: Agrupa canais e calcula share de receita proporcional', async () => {
    const res = await analyticsService.getSalesAnalytics({
      startDate: '2026-10-10',
      endDate: '2026-10-12'
    });

    const stores = res.byStore;
    assert.strictEqual(stores.length, 3);

    // KIOSK ESPIRITO SANTO: 200 + 300 = 500 (50.0%)
    const es = stores.find(s => s.storeId === '206085936');
    assert.ok(es);
    assert.strictEqual(es.revenue, 500.00);
    assert.strictEqual(es.ordersCount, 2);
    assert.strictEqual(es.sharePercentage, 50.0);

    // Shopify: 400 (40.0%)
    const shopify = stores.find(s => s.storeId === '206133846');
    assert.ok(shopify);
    assert.strictEqual(shopify.revenue, 400.00);
    assert.strictEqual(shopify.sharePercentage, 40.0);

    // KIOSK RECIFE: 100 (10.0%)
    const recife = stores.find(s => s.storeId === '206084387');
    assert.ok(recife);
    assert.strictEqual(recife.revenue, 100.00);
    assert.strictEqual(recife.sharePercentage, 10.0);
  });

  // ----------------------------------------------------
  // TESTE 3: Linha do Tempo Diária
  // ----------------------------------------------------
  await it('BlingSalesAnalytics: Constrói timeline diária ordenada cronologicamente', async () => {
    const res = await analyticsService.getSalesAnalytics({
      startDate: '2026-10-10',
      endDate: '2026-10-12'
    });

    const timeline = res.timeline;
    assert.strictEqual(timeline.length, 3);
    assert.strictEqual(timeline[0].date, '2026-10-10');
    assert.strictEqual(timeline[0].revenue, 300.00);
    assert.strictEqual(timeline[1].date, '2026-10-11');
    assert.strictEqual(timeline[1].revenue, 300.00);
    assert.strictEqual(timeline[2].date, '2026-10-12');
    assert.strictEqual(timeline[2].revenue, 400.00);
  });

  // ----------------------------------------------------
  // TESTE 4: Top Produtos Vendidos
  // ----------------------------------------------------
  await it('BlingSalesAnalytics: Identifica Top SKUs por faturamento e unidades', async () => {
    const res = await analyticsService.getSalesAnalytics({
      startDate: '2026-10-10',
      endDate: '2026-10-12'
    });

    const top = res.topProducts;
    assert.strictEqual(top[0].sku, 'TOUTI-VIP-50');
    assert.strictEqual(top[0].quantity, 5); // 2 + 3 unidades
    assert.strictEqual(top[0].revenue, 500.00);

    assert.strictEqual(top[1].sku, 'YES-BATOM-RED');
    assert.strictEqual(top[1].quantity, 4);
    assert.strictEqual(top[1].revenue, 400.00);
  });

  // ----------------------------------------------------
  // TESTE 5: Funil de Conversão Logística (Fulfillment Rate)
  // ----------------------------------------------------
  await it('BlingSalesAnalytics: Calcula taxa de fulfillment da fila do Hub (75%)', async () => {
    const res = await analyticsService.getSalesAnalytics({
      startDate: '2026-10-10',
      endDate: '2026-10-12'
    });

    const ful = res.fulfillment;
    assert.strictEqual(ful.queuedTotal, 4);
    assert.strictEqual(ful.labelsGenerated, 3);
    assert.strictEqual(ful.pendingInQueue, 1);
    assert.strictEqual(ful.fulfillmentRatePercent, 75.0);
  });

  // ----------------------------------------------------
  // TESTE 6: Cache em Memória
  // ----------------------------------------------------
  await it('BlingSalesAnalytics: Responde do cache em segunda chamada idêntica', async () => {
    const res1 = await analyticsService.getSalesAnalytics({
      startDate: '2026-10-10',
      endDate: '2026-10-12'
    });
    assert.strictEqual(res1.fromCache, true, 'Segunda chamada imediata deve vir do cache');
  });

  console.log('\n------------------------------------------------------------');
  console.log(`📊 RESULTADO FINAL: ${testsPassed} Aprovados | ${testsFailed} Falhas`);
  console.log('------------------------------------------------------------\n');

  if (testsFailed > 0) process.exit(1);
}

run().catch(err => {
  console.error(err);
  process.exit(1);
});
