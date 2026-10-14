/**
 * @file CorpemWMSConnector.js
 * @description Conector WMS para integração com operador logístico Corpem (DEM-12).
 * Traduz o pedido universal para Ordem de Separação (Picking/Packing).
 */

const { BaseConnector, ConnectorError } = require('./BaseConnector');
const { ConnectorErrorCode, validateUniversalOrder } = require('./types');

class CorpemWMSConnector extends BaseConnector {
  /**
   * @param {object} params
   * @param {string|number} params.id
   * @param {string} [params.name='Corpem WMS']
   * @param {object} params.config
   * @param {string} params.config.url URL de integração da Corpem
   * @param {string} [params.config.apiKey]
   * @param {string} [params.config.token]
   * @param {object} [params.httpClient]
   */
  constructor(params) {
    super({
      ...params,
      type: 'wms',
      name: params.name || 'Corpem WMS',
      label: params.label || 'Corpem WMS'
    });

    this.endpointUrl = (this.config.url || '').trim();
    this.httpClient = params.httpClient || null;
  }

  validateConfig() {
    super.validateConfig();
    if (!this.config.url) {
      throw new ConnectorError(
        'CorpemWMSConnector requer "url" configurada.',
        ConnectorErrorCode.CONFIGURATION_ERROR,
        { connectorId: this.id }
      );
    }
  }

  async _request(options) {
    if (this.httpClient && typeof this.httpClient.request === 'function') {
      return this.httpClient.request(options);
    }

    if (typeof fetch === 'function') {
      const res = await fetch(options.url, {
        method: options.method || 'POST',
        headers: options.headers || { 'Content-Type': 'application/json' },
        body: JSON.stringify(options.data)
      });

      const text = await res.text();
      let data = text;
      try { data = JSON.parse(text); } catch (_) {}

      if (!res.ok) {
        const error = new Error(`Corpem WMS HTTP Error ${res.status}`);
        error.response = { status: res.status, data };
        throw error;
      }

      return { status: res.status, data };
    }

    throw new Error('Nenhum cliente HTTP disponível para o CorpemWMSConnector.');
  }

  /**
   * Envia Ordem de Separação para o WMS da Corpem.
   * @param {import('./types').UniversalOrder} universalOrder 
   */
  async sendSeparationOrder(universalOrder) {
    const validation = validateUniversalOrder(universalOrder);
    if (!validation.valid) {
      throw new ConnectorError(
        `Pedido inválido para envio ao WMS Corpem: ${validation.errors.join('; ')}`,
        ConnectorErrorCode.VALIDATION_ERROR
      );
    }

    return this.executeWithRetry(`sendSeparationOrder:${universalOrder.orderId}`, async () => {
      const trackingCode = universalOrder.existingTracking?.trackingNumber || null;

      const payload = {
        codigo_pedido_erp: universalOrder.orderId,
        numero_pedido: universalOrder.orderNumber,
        cliente: {
          nome: universalOrder.customer.name,
          documento: universalOrder.customer.documentNumber,
          email: universalOrder.customer.email,
          telefone: universalOrder.customer.phone
        },
        destinatario: {
          nome: universalOrder.shippingAddress.recipientName,
          logradouro: universalOrder.shippingAddress.street,
          numero: universalOrder.shippingAddress.number,
          complemento: universalOrder.shippingAddress.complement,
          bairro: universalOrder.shippingAddress.neighborhood,
          cidade: universalOrder.shippingAddress.city,
          uf: universalOrder.shippingAddress.state,
          cep: universalOrder.shippingAddress.zipCode
        },
        documento_fiscal: universalOrder.invoice ? {
          chave_acesso: universalOrder.invoice.accessKey,
          numero: universalOrder.invoice.number,
          serie: universalOrder.invoice.series
        } : null,
        rastreio_transportadora: trackingCode,
        data_integracao: new Date().toISOString()
      };

      this.log('info', `Enviando Ordem de Separação do pedido ${universalOrder.orderId} para Corpem WMS...`);

      const headers = {
        'Content-Type': 'application/json'
      };
      if (this.config.apiKey) headers['X-API-Key'] = this.config.apiKey;
      if (this.config.token) headers['Authorization'] = `Bearer ${this.config.token}`;

      const res = await this._request({
        url: this.endpointUrl,
        method: 'POST',
        headers,
        data: payload
      });

      this.log('info', `Ordem de separação do pedido ${universalOrder.orderId} aceita pelo WMS Corpem.`);

      return {
        success: true,
        orderId: universalOrder.orderId,
        wmsResult: res.data
      };
    });
  }

  async healthCheck() {
    return {
      ok: Boolean(this.endpointUrl),
      message: `Corpem WMS configurado (${this.endpointUrl}).`,
      details: { url: this.endpointUrl }
    };
  }
}

module.exports = {
  CorpemWMSConnector
};
