/**
 * @file BlingV3Connector.js
 * @description Conector ERP para Bling API v3.
 * Implementa renovação automática e atômica de tokens OAuth 2.0, taxa controlada (3 req/s),
 * extração de rastreio pré-existente (proteção anti-duplicidade) e gravação idempotente de rastreamento.
 */

const { BaseConnector, ConnectorError } = require('./BaseConnector');
const { ConnectorErrorCode, isValidNfeAccessKey, cleanZipCode, cleanDocument } = require('./types');

class BlingV3Connector extends BaseConnector {
  /**
   * @param {object} params
   * @param {string|number} params.id
   * @param {string} [params.name='Bling v3']
   * @param {object} params.config
   * @param {string} params.config.clientId
   * @param {string} params.config.clientSecret
   * @param {string} [params.config.accessToken]
   * @param {string} [params.config.refreshToken]
   * @param {number} [params.config.expiresAt] Timestamp epoch ms
   * @param {string} [params.config.baseUrl='https://api.bling.com.br/Api/v3']
   * @param {Function} [params.onConfigUpdate]
   * @param {object} [params.httpClient] Cliente HTTP injetável (compatível com axios / fetch)
   */
  constructor(params) {
    super({
      ...params,
      type: 'erp',
      name: params.name || 'Bling v3',
      minIntervalMs: 350 // Respeita o limite estrito de 3 requisições por segundo
    });

    this.baseUrl = (this.config.baseUrl || 'https://api.bling.com.br/Api/v3').replace(/\/$/, '');
    this.authUrl = (this.config.authUrl || 'https://www.bling.com.br/Api/v3/oauth/token');
    this.httpClient = params.httpClient || null; // Se não fornecido, usa módulo padrão
  }

  validateConfig() {
    super.validateConfig();
    const { clientId, clientSecret } = this.config;
    if (!clientId || !clientSecret) {
      throw new ConnectorError(
        'BlingV3Connector requer "clientId" e "clientSecret" configurados.',
        ConnectorErrorCode.CONFIGURATION_ERROR,
        { connectorId: this.id }
      );
    }
  }

  /**
   * Despacha uma requisição HTTP via httpClient injetado ou nativo.
   */
  async _request(options) {
    if (this.httpClient && typeof this.httpClient.request === 'function') {
      return this.httpClient.request(options);
    }

    // Fallback nativo usando fetch global (Node 18+)
    if (typeof fetch === 'function') {
      const url = options.url;
      const headers = { ...(options.headers || {}) };
      let body = options.data;

      if (body && typeof body === 'object' && !(body instanceof URLSearchParams)) {
        if (headers['Content-Type'] === 'application/x-www-form-urlencoded') {
          body = new URLSearchParams(body).toString();
        } else {
          headers['Content-Type'] = headers['Content-Type'] || 'application/json';
          body = JSON.stringify(body);
        }
      }

      const res = await fetch(url, {
        method: options.method || 'GET',
        headers,
        body: ['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase()) ? undefined : body
      });

      const text = await res.text();
      let data = text;
      try { data = JSON.parse(text); } catch (_) {}

      if (!res.ok) {
        const error = new Error(`HTTP Error ${res.status}: ${res.statusText}`);
        error.response = { status: res.status, statusText: res.statusText, data };
        throw error;
      }

      return { status: res.status, data };
    }

    throw new Error('Nenhum cliente HTTP disponível (httpClient ou fetch nativo do Node).');
  }

  /**
   * Garante a obtenção de um accessToken válido.
   * Se faltar menos de 10 minutos para expirar, realiza a renovação automática.
   */
  async getValidAccessToken() {
    const { accessToken, expiresAt, refreshToken } = this.config;
    const TEN_MINUTES_MS = 10 * 60 * 1000;
    const now = Date.now();

    const isExpiredOrClose = !expiresAt || now >= (expiresAt - TEN_MINUTES_MS);

    if (!accessToken || isExpiredOrClose) {
      if (!refreshToken) {
        throw new ConnectorError(
          'Token OAuth expirado e nenhum refreshToken disponível. Reautorização manual necessária.',
          ConnectorErrorCode.INVALID_REFRESH_TOKEN,
          { connectorId: this.id }
        );
      }

      this.log('info', `Token OAuth prestes a expirar ou ausente. Renovando com refreshToken...`);
      return await this.refreshOAuthToken();
    }

    return accessToken;
  }

  /**
   * Executa a renovação do token OAuth 2.0 via POST /oauth/token.
   */
  async refreshOAuthToken() {
    return this.executeWithRetry('refreshOAuthToken', async () => {
      const { clientId, clientSecret, refreshToken } = this.config;
      const basicAuth = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');

      const response = await this._request({
        url: this.authUrl,
        method: 'POST',
        headers: {
          'Authorization': `Basic ${basicAuth}`,
          'Content-Type': 'application/x-www-form-urlencoded'
        },
        data: {
          grant_type: 'refresh_token',
          refresh_token: refreshToken
        }
      });

      const data = response.data;
      if (!data || !data.access_token) {
        throw new ConnectorError(
          'Resposta inválida do servidor OAuth do Bling: access_token ausente.',
          ConnectorErrorCode.UNAUTHORIZED,
          { details: data }
        );
      }

      const expiresInSec = Number(data.expires_in) || 21600; // Default 6h
      const expiresAt = Date.now() + (expiresInSec * 1000);

      const updated = {
        accessToken: data.access_token,
        refreshToken: data.refresh_token || refreshToken,
        expiresAt
      };

      await this.updateConfig(updated);
      this.log('info', `Token OAuth renovado com sucesso! Válido até ${new Date(expiresAt).toLocaleString()}`);
      return updated.accessToken;
    }, { maxRetries: 2, baseDelayMs: 500 });
  }

  /**
   * Recupera o pedido de venda no Bling e normaliza para o contrato UniversalOrder.
   * 🛡️ Inclui a leitura crítica de rastreios pré-existentes e validação de NF-e.
   * @param {string|number} erpId ID do pedido de venda no Bling
   * @returns {Promise<import('./types').UniversalOrder>}
   */
  async getOrder(erpId) {
    if (!erpId) throw new ConnectorError('erpId é obrigatório', ConnectorErrorCode.VALIDATION_ERROR);

    return this.executeWithRetry(`getOrder:${erpId}`, async () => {
      const token = await this.getValidAccessToken();

      const res = await this._request({
        url: `${this.baseUrl}/pedidos/vendas/${erpId}`,
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Accept': 'application/json'
        }
      });

      const pedido = res.data?.data;
      if (!pedido) {
        throw new ConnectorError(`Pedido ${erpId} não encontrado no Bling.`, ConnectorErrorCode.ORDER_NOT_FOUND);
      }

      // 1. Extração do Rastreio Pré-Existente (Fix da Falha de Duplicidade)
      const primeiroVolume = pedido.transporte?.volumes?.[0];
      const trackingExistente = (
        primeiroVolume?.codigoRastreamento ||
        primeiroVolume?.rastreamento?.codigo ||
        pedido.transporte?.etiqueta?.rastreamento ||
        null
      );

      // 2. Extração de Endereço (Prioriza transporte.etiqueta, depois contato)
      const etiqueta = pedido.transporte?.etiqueta || {};
      const contato = pedido.contato || {};

      const shippingAddress = {
        recipientName: etiqueta.nome || contato.nome || 'Consumidor',
        street: etiqueta.endereco || contato.endereco?.geral || '',
        number: etiqueta.numero || contato.endereco?.numero || 'S/N',
        complement: etiqueta.complemento || contato.endereco?.complemento || '',
        neighborhood: etiqueta.bairro || contato.endereco?.bairro || '',
        city: etiqueta.municipio || contato.endereco?.municipio || '',
        state: (etiqueta.uf || contato.endereco?.uf || '').toUpperCase(),
        zipCode: cleanZipCode(etiqueta.cep || contato.endereco?.cep),
        country: etiqueta.nomePais || 'BRASIL'
      };

      // 3. Pacotes e Peso
      const grossWeight = Number(pedido.transporte?.pesoBruto) || 0.85;
      const volumesCount = Array.isArray(pedido.transporte?.volumes)
        ? pedido.transporte.volumes.length
        : Number(pedido.transporte?.quantidadeVolumes) || 1;

      // 4. Verificação de Nota Fiscal
      let invoiceData = null;
      if (pedido.notaFiscal && pedido.notaFiscal.id) {
        try {
          const nfRes = await this._request({
            url: `${this.baseUrl}/nfe/${pedido.notaFiscal.id}`,
            method: 'GET',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Accept': 'application/json'
            }
          });
          const nf = nfRes.data?.data;
          if (nf && nf.chaveAcesso) {
            invoiceData = {
              id: pedido.notaFiscal.id,
              accessKey: String(nf.chaveAcesso).trim(),
              number: nf.numero,
              series: nf.serie
            };
          }
        } catch (nfErr) {
          this.log('warn', `Não foi possível carregar dados detalhados da NF ${pedido.notaFiscal.id}: ${nfErr.message}`);
        }
      }

      // Montagem do Pedido Universal
      const universalOrder = {
        orderId: String(pedido.id),
        orderNumber: String(pedido.numero || pedido.id),
        storeId: pedido.loja?.id || null,
        status: pedido.situacao?.valor || 'Atendido',
        createdAt: pedido.data || new Date().toISOString(),
        customer: {
          id: contato.id,
          name: contato.nome,
          documentType: contato.tipoPessoa || 'F',
          documentNumber: cleanDocument(contato.numeroDocumento),
          email: contato.email,
          phone: contato.telefone || contato.celular
        },
        shippingAddress,
        packages: {
          grossWeightKg: grossWeight,
          volumesCount,
          volumeId: primeiroVolume?.id || null,
          serviceCode: primeiroVolume?.servico || null
        },
        invoice: invoiceData,
        existingTracking: trackingExistente ? {
          trackingNumber: String(trackingExistente).trim(),
          service: primeiroVolume?.servico || 'J&T'
        } : null
      };

      return universalOrder;
    });
  }

  /**
   * Atualiza o código de rastreamento no objeto logístico do pedido no Bling.
   * 🛡️ IDEMPOTÊNCIA: Se o rastreio atual já for igual, não despacha o PUT.
   * @param {string|number} erpId 
   * @param {string} trackingNumber Código da J&T (billCode)
   */
  async updateTracking(erpId, trackingNumber) {
    if (!erpId || !trackingNumber) {
      throw new ConnectorError('erpId e trackingNumber são obrigatórios', ConnectorErrorCode.VALIDATION_ERROR);
    }

    return this.executeWithRetry(`updateTracking:${erpId}`, async () => {
      const token = await this.getValidAccessToken();

      // 1. Consulta o pedido para obter o ID do volume e conferir se já está gravado
      const orderRes = await this._request({
        url: `${this.baseUrl}/pedidos/vendas/${erpId}`,
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Accept': 'application/json'
        }
      });

      const pedido = orderRes.data?.data;
      const volumes = pedido?.transporte?.volumes;

      if (!volumes || !volumes.length) {
        throw new ConnectorError(
          `Pedido ${erpId} não possui objeto de logística/volume vinculado no Bling.`,
          ConnectorErrorCode.VALIDATION_ERROR
        );
      }

      if (volumes.length > 1) {
        this.log('warn', `Pedido ${erpId} possui múltiplos volumes (${volumes.length}). O Hub atualizará o volume principal.`);
      }

      const volumeId = volumes[0].id;
      const rastreioAtual = volumes[0].codigoRastreamento || volumes[0].rastreamento?.codigo;

      // 🛡️ CHECAGEM DE IDEMPOTÊNCIA: Se já estiver igual, dispensa PUT!
      if (rastreioAtual && String(rastreioAtual).trim() === String(trackingNumber).trim()) {
        this.log('info', `Rastreio do pedido ${erpId} já é ${trackingNumber} no Bling. PUT redundante dispensado.`);
        return {
          success: true,
          erpId,
          volumeId,
          trackingNumber,
          alreadyUpToDate: true
        };
      }

      // 2. Executa o PUT para atualizar o rastreamento no objeto
      this.log('info', `Atualizando rastreio do volume ${volumeId} no Bling para "${trackingNumber}"...`);
      await this._request({
        url: `${this.baseUrl}/logisticas/objetos/${volumeId}`,
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        data: {
          rastreamento: {
            codigo: String(trackingNumber).trim()
          }
        }
      });

      // 3. Verificação de confirmação pós-gravação
      const verifyRes = await this._request({
        url: `${this.baseUrl}/logisticas/objetos/${volumeId}`,
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Accept': 'application/json'
        }
      });

      const objetoGravado = verifyRes.data?.data;
      const codigoConfirmado = objetoGravado?.rastreamento?.codigo || objetoGravado?.codigoRastreamento;

      if (codigoConfirmado && String(codigoConfirmado).trim() !== String(trackingNumber).trim()) {
        this.log('warn', `Confirmação de rastreio divergente no Bling: esperado ${trackingNumber}, recebido ${codigoConfirmado}`);
      }

      return {
        success: true,
        erpId,
        volumeId,
        trackingNumber,
        confirmed: true
      };
    });
  }

  async healthCheck() {
    try {
      const token = await this.getValidAccessToken();
      const expiresAt = this.config.expiresAt;
      const minutesRemaining = expiresAt ? Math.round((expiresAt - Date.now()) / 60000) : 0;

      return {
        ok: true,
        message: `Bling v3 conectado. Token válido por mais ~${minutesRemaining} minutos.`,
        details: {
          expiresAt: new Date(expiresAt).toISOString(),
          minutesRemaining
        }
      };
    } catch (err) {
      return {
        ok: false,
        message: `Falha na conexão Bling v3: ${err.message}`,
        details: { error: err.code || err.message }
      };
    }
  }
}

module.exports = {
  BlingV3Connector
};
