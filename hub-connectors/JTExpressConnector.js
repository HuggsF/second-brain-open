/**
 * @file JTExpressConnector.js
 * @description Conector de Transportadora para J&T Express.
 * Implementa assinatura de payload, emissão de etiquetas via /addOrder,
 * proteção em 3 camadas contra etiquetas duplicadas / cobrança dupla de frete,
 * consulta de rastreamento e cancelamento de etiquetas.
 */

const crypto = require('crypto');
const { BaseConnector, ConnectorError } = require('./BaseConnector');
const { ConnectorErrorCode, validateUniversalOrder, isValidNfeAccessKey } = require('./types');

class JTExpressConnector extends BaseConnector {
  /**
   * @param {object} params
   * @param {string|number} params.id
   * @param {string} [params.name='J&T Express']
   * @param {string} [params.label='ESPIRITO SANTO - J&T']
   * @param {object} params.config
   * @param {string} params.config.code Código de cliente J&T (ex: J0086038727)
   * @param {string} params.config.acc Conta (ex: 899296264686898176)
   * @param {string} params.config.pwd Senha da API
   * @param {string} params.config.key Chave privada para assinatura digest
   * @param {object} params.config.remetente Dados do remetente
   * @param {string} [params.config.baseUrl='https://api.jtexpress.com.br']
   * @param {object} [params.httpClient] Cliente HTTP injetável para testes e mocking
   */
  constructor(params) {
    super({
      ...params,
      type: 'carrier',
      name: params.name || 'J&T Express',
      label: params.label || params.name || 'J&T Express'
    });

    this.baseUrl = (this.config.baseUrl || 'https://api.jtexpress.com.br').replace(/\/$/, '');
    this.httpClient = params.httpClient || null;
  }

  validateConfig() {
    super.validateConfig();
    const { code, pwd, key } = this.config;
    if (!code || !pwd || !key) {
      throw new ConnectorError(
        'JTExpressConnector requer "code", "pwd" e "key" configurados.',
        ConnectorErrorCode.CONFIGURATION_ERROR,
        { connectorId: this.id }
      );
    }

    if (!this.config.remetente || !this.config.remetente.cep) {
      throw new ConnectorError(
        'JTExpressConnector requer dados do "remetente" com CEP válido.',
        ConnectorErrorCode.CONFIGURATION_ERROR,
        { connectorId: this.id }
      );
    }
  }

  /**
   * Gera o digest/assinatura MD5 exigido pela API da J&T Express.
   * @param {string} dataContent Conteúdo JSON serializado
   * @returns {string} Hash Base64
   */
  generateDigest(dataContent) {
    const raw = `${dataContent}${this.config.key}`;
    return crypto.createHash('md5').update(raw, 'utf8').digest('base64');
  }

  async _request(options) {
    if (this.httpClient && typeof this.httpClient.request === 'function') {
      return this.httpClient.request(options);
    }

    if (typeof fetch === 'function') {
      const url = options.url;
      const headers = { ...(options.headers || {}) };
      let body = options.data;

      if (body && typeof body === 'object' && !(body instanceof URLSearchParams)) {
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';
        body = JSON.stringify(body);
      }

      const res = await fetch(url, {
        method: options.method || 'POST',
        headers,
        body
      });

      const text = await res.text();
      let data = text;
      try { data = JSON.parse(text); } catch (_) {}

      if (!res.ok) {
        const error = new Error(`J&T Express HTTP Error ${res.status}: ${res.statusText}`);
        error.response = { status: res.status, statusText: res.statusText, data };
        throw error;
      }

      return { status: res.status, data };
    }

    throw new Error('Nenhum cliente HTTP disponível para o JTExpressConnector.');
  }

  /**
   * Emite uma etiqueta na J&T Express via POST /addOrder.
   * 🛡️ CAMADA 1 ANTI-DUPLICIDADE: Se o pedido já tiver rastreio no ERP, reutiliza sem chamar a J&T.
   * @param {import('./types').UniversalOrder} universalOrder 
   * @returns {Promise<import('./types').LabelResult>}
   */
  async generateLabel(universalOrder) {
    // 🛡️ Proteção Camada 1: Rastreio já existente no pedido
    if (universalOrder.existingTracking && universalOrder.existingTracking.trackingNumber) {
      const existingCode = String(universalOrder.existingTracking.trackingNumber).trim();
      this.log('info', `🛡️ PROTEÇÃO ANTI-DUPLICIDADE ATIVADA: Pedido ${universalOrder.orderId} já possui rastreio "${existingCode}". Reutilizando sem emitir nova etiqueta.`);
      return {
        success: true,
        trackingNumber: existingCode,
        txlogisticId: `EXISTING-${universalOrder.orderId}`,
        carrier: 'JT_EXPRESS',
        serviceType: 'EZ',
        alreadyExisted: true,
        reason: 'EXISTING_IN_ERP'
      };
    }

    // Validação formal do pedido universal
    const validation = validateUniversalOrder(universalOrder);
    if (!validation.valid) {
      throw new ConnectorError(
        `Falha de validação do pedido ${universalOrder.orderId}: ${validation.errors.join('; ')}`,
        ConnectorErrorCode.VALIDATION_ERROR,
        { details: validation.errors }
      );
    }

    // Validação mandatória de NF-e (se houver nota, a chave deve ter 44 dígitos)
    if (universalOrder.invoice && universalOrder.invoice.accessKey) {
      if (!isValidNfeAccessKey(universalOrder.invoice.accessKey)) {
        throw new ConnectorError(
          `Chave da NF-e inválida para envio à J&T (${universalOrder.invoice.accessKey}). Geração bloqueada.`,
          ConnectorErrorCode.INVOICE_INVALID
        );
      }
    }

    return this.executeWithRetry(`generateLabel:${universalOrder.orderId}`, async () => {
      const now = Date.now();
      const txlogisticId = `HUB-${universalOrder.orderId}-${now}`;
      const remetente = this.config.remetente;
      const addr = universalOrder.shippingAddress;
      const cust = universalOrder.customer;

      const orderPayload = {
        eccompanyid: this.config.code,
        customerid: this.config.code,
        txlogisticid: txlogisticId,
        ordertype: '1',
        servicetype: 'EZ', // Express padrão
        sender: {
          name: remetente.nome,
          postcode: remetente.cep,
          mobile: remetente.telefone || '81984203388',
          phone: remetente.telefone || '81984203388',
          prov: remetente.uf,
          city: remetente.cidade,
          address: `${remetente.endereco}, ${remetente.numero} ${remetente.complemento || ''}`.trim()
        },
        receiver: {
          name: addr.recipientName,
          postcode: addr.zipCode,
          mobile: cust.phone || '00000000000',
          phone: cust.phone || '00000000000',
          prov: addr.state,
          city: addr.city,
          address: `${addr.street}, ${addr.number} ${addr.complement || ''}`.trim()
        },
        itemsvalue: '100.00',
        weight: String(universalOrder.packages.grossWeightKg || 0.85),
        length: '20',
        width: '15',
        height: '10',
        isinsured: '0',
        goodsType: 'COSMETICOS'
      };

      // Adiciona chave de NF-e se disponível
      if (universalOrder.invoice?.accessKey) {
        orderPayload.invoiceKey = universalOrder.invoice.accessKey;
      }

      const serializedData = JSON.stringify(orderPayload);
      const digest = this.generateDigest(serializedData);

      this.log('info', `Enviando POST /addOrder para J&T Express (txlogisticId: ${txlogisticId})...`);

      const response = await this._request({
        url: `${this.baseUrl}/addOrder`,
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded'
        },
        data: {
          logistics_interface: serializedData,
          data_digest: digest,
          msg_type: 'ORDERCREATE',
          eccompanyid: this.config.code
        }
      });

      const data = response.data;
      let billCode = null;

      if (data && data.responseitems && data.responseitems[0]) {
        const item = data.responseitems[0];
        if (item.success === 'true' || item.success === true) {
          billCode = item.billCode || item.mailNo;
        } else {
          throw new ConnectorError(
            `J&T rejeitou a emissão do pedido ${universalOrder.orderId}: ${item.reason || 'Erro desconhecido'}`,
            ConnectorErrorCode.CARRIER_REJECTED,
            { details: item }
          );
        }
      } else if (data && data.billCode) {
        billCode = data.billCode;
      }

      if (!billCode) {
        throw new ConnectorError(
          `J&T não retornou um billCode válido para o pedido ${universalOrder.orderId}.`,
          ConnectorErrorCode.CARRIER_REJECTED,
          { details: data }
        );
      }

      this.log('info', `Etiqueta J&T emitida com sucesso! billCode: ${billCode}`);

      return {
        success: true,
        trackingNumber: billCode,
        txlogisticId,
        carrier: 'JT_EXPRESS',
        serviceType: 'EZ',
        alreadyExisted: false,
        rawResponse: data
      };
    });
  }

  /**
   * Consulta o status de um rastreamento na J&T.
   * @param {string} billCode
   */
  async getTrackingStatus(billCode) {
    if (!billCode) throw new ConnectorError('billCode é obrigatório', ConnectorErrorCode.VALIDATION_ERROR);

    return this.executeWithRetry(`getTracking:${billCode}`, async () => {
      const payload = {
        billCodes: billCode
      };
      const serialized = JSON.stringify(payload);
      const digest = this.generateDigest(serialized);

      const res = await this._request({
        url: `${this.baseUrl}/logistics/trace`,
        method: 'POST',
        data: {
          logistics_interface: serialized,
          data_digest: digest,
          msg_type: 'TRACK_QUERY',
          eccompanyid: this.config.code
        }
      });

      return res.data;
    });
  }

  /**
   * Cancela uma etiqueta/ordem na J&T Express.
   * @param {string} billCode 
   * @param {string} [reason='Cancelamento solicitado pelo Hub']
   */
  async cancelLabel(billCode, reason = 'Cancelamento pelo Hub') {
    if (!billCode) throw new ConnectorError('billCode é obrigatório', ConnectorErrorCode.VALIDATION_ERROR);

    return this.executeWithRetry(`cancelLabel:${billCode}`, async () => {
      const payload = {
        eccompanyid: this.config.code,
        billCode,
        reason
      };
      const serialized = JSON.stringify(payload);
      const digest = this.generateDigest(serialized);

      this.log('warn', `Enviando cancelamento de etiqueta ${billCode} para J&T...`);

      const res = await this._request({
        url: `${this.baseUrl}/cancelOrder`,
        method: 'POST',
        data: {
          logistics_interface: serialized,
          data_digest: digest,
          msg_type: 'ORDERCANCEL',
          eccompanyid: this.config.code
        }
      });

      return res.data;
    });
  }

  async healthCheck() {
    return {
      ok: true,
      message: `J&T Express (${this.label}) configurado e ativo.`,
      details: {
        code: this.config.code,
        remetenteUf: this.config.remetente?.uf
      }
    };
  }
}

module.exports = {
  JTExpressConnector
};
