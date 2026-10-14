/**
 * @file BaseConnector.js
 * @description Classe base abstrata e agnóstica para todos os conectores (ERPs, Transportadoras e WMS).
 * Implementa resiliência, retries com backoff exponencial + jitter, rate-limiting e telemetria.
 */

const { ConnectorErrorCode } = require('./types');

class ConnectorError extends Error {
  /**
   * @param {string} message 
   * @param {string} code Código canônico do enum ConnectorErrorCode
   * @param {object} [options] 
   */
  constructor(message, code = ConnectorErrorCode.CONFIGURATION_ERROR, options = {}) {
    super(message);
    this.name = 'ConnectorError';
    this.code = code;
    this.statusCode = options.statusCode || 500;
    this.isRetryable = Boolean(options.isRetryable);
    this.connectorId = options.connectorId || null;
    this.details = options.details || null;
    this.originalError = options.originalError || null;
  }
}

class BaseConnector {
  /**
   * @param {object} params
   * @param {string|number} params.id
   * @param {'erp'|'carrier'|'wms'} params.type
   * @param {string} params.name
   * @param {string} [params.label]
   * @param {object} params.config
   * @param {boolean} [params.active=true]
   * @param {Function} [params.onConfigUpdate] Callback assíncrono para persistir atualizações de credenciais
   * @param {number} [params.minIntervalMs=0] Intervalo mínimo entre requisições para rate-limiting
   */
  constructor(params) {
    if (!params.id || !params.type || !params.name) {
      throw new ConnectorError('Parâmetros obrigatórios ausentes: id, type e name são necessários.', ConnectorErrorCode.CONFIGURATION_ERROR);
    }

    this.id = params.id;
    this.type = params.type;
    this.name = params.name;
    this.label = params.label || params.name;
    this.config = params.config || {};
    this.active = params.active !== false;
    this.onConfigUpdate = params.onConfigUpdate || null;
    this.minIntervalMs = params.minIntervalMs || 0;
    this._lastRequestTimestamp = 0;
    this._lock = Promise.resolve();

    this.validateConfig();
  }

  /**
   * Valida as propriedades de configuração do conector. Deve ser sobrescrito pelas subclasses.
   */
  validateConfig() {
    if (typeof this.config !== 'object' || this.config === null) {
      throw new ConnectorError(`Configuração inválida para o conector ${this.name}`, ConnectorErrorCode.CONFIGURATION_ERROR, {
        connectorId: this.id
      });
    }
  }

  /**
   * Atualiza a configuração em memória e dispara o callback de persistência (ex: atualizar hub.db).
   * @param {object} newPartialConfig
   */
  async updateConfig(newPartialConfig) {
    this.config = { ...this.config, ...newPartialConfig };
    this.log('info', `Configuração atualizada para conector [${this.id}] ${this.name}`, {
      keysUpdated: Object.keys(newPartialConfig)
    });

    if (typeof this.onConfigUpdate === 'function') {
      try {
        await this.onConfigUpdate(this.id, this.config);
      } catch (err) {
        this.log('error', `Falha ao persistir configuração atualizada no banco: ${err.message}`, { err });
      }
    }
  }

  /**
   * Aplica taxa de espaçamento (Rate-Limiting) antes de enviar a requisição.
   */
  async _applyRateLimit() {
    if (this.minIntervalMs <= 0) return;

    // Enfileira de forma atômica
    const currentLock = this._lock;
    let release;
    this._lock = new Promise(resolve => { release = resolve; });

    await currentLock;

    try {
      const now = Date.now();
      const elapsed = now - this._lastRequestTimestamp;
      if (elapsed < this.minIntervalMs) {
        const waitTime = this.minIntervalMs - elapsed;
        await new Promise(resolve => setTimeout(resolve, waitTime));
      }
      this._lastRequestTimestamp = Date.now();
    } finally {
      release();
    }
  }

  /**
   * Executa uma função com retry automático, backoff exponencial e jitter.
   * @param {string} opName Nome da operação para logs e métricas
   * @param {Function} fn Função assíncrona a executar
   * @param {object} [options]
   * @param {number} [options.maxRetries=3]
   * @param {number} [options.baseDelayMs=350]
   */
  async executeWithRetry(opName, fn, options = {}) {
    const maxRetries = options.maxRetries ?? 3;
    const baseDelayMs = options.baseDelayMs ?? 350;

    let attempt = 0;

    while (attempt <= maxRetries) {
      try {
        await this._applyRateLimit();
        const start = Date.now();
        const result = await fn();
        const duration = Date.now() - start;
        this.log('debug', `Operação [${opName}] executada com sucesso (${duration}ms)`);
        return result;
      } catch (err) {
        attempt++;
        const statusCode = err.response?.status || err.statusCode || 500;
        const isRateLimit = statusCode === 429;
        const isTransient = isRateLimit || [500, 502, 503, 504].includes(statusCode) || err.code === 'ECONNRESET' || err.code === 'ETIMEDOUT';

        this.log('warn', `Falha na operação [${opName}] (tentativa ${attempt}/${maxRetries}): ${err.message} [Status: ${statusCode}]`);

        if (attempt > maxRetries || !isTransient) {
          // Erro definitivo
          if (err instanceof ConnectorError) throw err;

          let canonCode = ConnectorErrorCode.UPSTREAM_UNAVAILABLE;
          if (statusCode === 401 || statusCode === 403) canonCode = ConnectorErrorCode.UNAUTHORIZED;
          else if (statusCode === 404) canonCode = ConnectorErrorCode.ORDER_NOT_FOUND;
          else if (isRateLimit) canonCode = ConnectorErrorCode.RATE_LIMITED;

          throw new ConnectorError(
            `Falha na operação [${opName}] após ${attempt} tentativas: ${err.message}`,
            canonCode,
            {
              statusCode,
              isRetryable: isTransient,
              connectorId: this.id,
              originalError: err
            }
          );
        }

        // Backoff exponencial com jitter aleatório
        const jitter = Math.floor(Math.random() * 200);
        const delay = (baseDelayMs * Math.pow(2, attempt - 1)) + jitter;
        this.log('info', `Aguardando ${delay}ms antes da próxima tentativa...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  /**
   * Health check / Teste de conexão do conector. Deve ser sobrescrito pelas subclasses.
   * @returns {Promise<{ ok: boolean, message: string, details?: any }>}
   */
  async healthCheck() {
    return { ok: this.active, message: `Conector ${this.name} ativo.` };
  }

  /**
   * Registro estruturado de logs.
   * @param {'debug'|'info'|'warn'|'error'} level 
   * @param {string} message 
   * @param {object} [meta] 
   */
  log(level, message, meta = {}) {
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [${this.type.toUpperCase()}:${this.name}]`;
    const line = `${prefix} ${message}`;

    if (level === 'error') {
      console.error(line, Object.keys(meta).length ? meta : '');
    } else if (level === 'warn') {
      console.warn(line, Object.keys(meta).length ? meta : '');
    } else if (level === 'debug') {
      if (process.env.DEBUG) console.debug(line, meta);
    } else {
      console.log(line, Object.keys(meta).length ? meta : '');
    }
  }
}

module.exports = {
  BaseConnector,
  ConnectorError
};
