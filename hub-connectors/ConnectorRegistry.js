/**
 * @file ConnectorRegistry.js
 * @description Fábrica e Gerenciador de instâncias de Conectores do Hub Logístico.
 * Realiza carregamento dinâmico a partir da tabela `connectors` do SQLite (hub.db)
 * e gerencia persistência transparente de credenciais renovadas.
 */

const { BlingV3Connector } = require('./BlingV3Connector');
const { JTExpressConnector } = require('./JTExpressConnector');
const { CorpemWMSConnector } = require('./CorpemWMSConnector');
const { ConnectorError } = require('./BaseConnector');
const { ConnectorErrorCode } = require('./types');

class ConnectorRegistry {
  constructor() {
    /** @type {Map<string|number, import('./BaseConnector').BaseConnector>} */
    this.connectors = new Map();
    this.db = null;
  }

  /**
   * Instancia a classe de conector apropriada com base no tipo e nome.
   * @param {object} row Registro vindo do SELECT * FROM connectors
   * @param {object} [options]
   */
  createConnectorInstance(row, options = {}) {
    let config = row.config;
    if (typeof config === 'string') {
      try {
        config = JSON.parse(config);
      } catch (e) {
        throw new ConnectorError(
          `Falha ao parsear JSON do config para conector ID ${row.id}: ${e.message}`,
          ConnectorErrorCode.CONFIGURATION_ERROR
        );
      }
    }

    const onConfigUpdate = async (connectorId, newConfig) => {
      if (this.db) {
        const jsonStr = JSON.stringify(newConfig);
        await new Promise((resolve, reject) => {
          this.db.run(
            'UPDATE connectors SET config = ? WHERE id = ?',
            [jsonStr, connectorId],
            function (err) {
              if (err) reject(err);
              else resolve(this.changes);
            }
          );
        });
      }
    };

    const params = {
      id: row.id,
      name: row.name,
      label: row.label || row.name,
      config,
      active: row.active === 1 || row.active === true,
      onConfigUpdate,
      httpClient: options.httpClient
    };

    if (row.type === 'erp') {
      return new BlingV3Connector(params);
    } else if (row.type === 'carrier') {
      return new JTExpressConnector(params);
    } else if (row.type === 'wms') {
      return new CorpemWMSConnector(params);
    }

    throw new ConnectorError(
      `Tipo de conector não suportado: "${row.type}" (ID: ${row.id})`,
      ConnectorErrorCode.CONFIGURATION_ERROR
    );
  }

  /**
   * Registra manualmente uma instância de conector.
   * @param {import('./BaseConnector').BaseConnector} connector 
   */
  register(connector) {
    this.connectors.set(String(connector.id), connector);
  }

  /**
   * Retorna um conector pelo ID numérico ou string.
   * @param {string|number} id 
   */
  get(id) {
    return this.connectors.get(String(id)) || null;
  }

  /**
   * Retorna todos os conectores de determinado tipo ('erp', 'carrier', 'wms').
   * @param {'erp'|'carrier'|'wms'} type 
   */
  getByType(type) {
    const results = [];
    for (const connector of this.connectors.values()) {
      if (connector.type === type && connector.active) {
        results.push(connector);
      }
    }
    return results;
  }

  /**
   * Retorna o conector ERP principal ativo (ex: Bling v3).
   * @returns {BlingV3Connector}
   */
  getPrimaryErp() {
    const erps = this.getByType('erp');
    if (!erps.length) {
      throw new ConnectorError('Nenhum conector ERP ativo encontrado na base.', ConnectorErrorCode.CONFIGURATION_ERROR);
    }
    return erps[0];
  }

  /**
   * Retorna a transportadora ativa correspondente ao ID da loja ou conector.
   * @param {string|number} carrierId 
   * @returns {JTExpressConnector}
   */
  getCarrier(carrierId) {
    const carrier = this.get(carrierId);
    if (!carrier) {
      throw new ConnectorError(`Transportadora ID ${carrierId} não encontrada.`, ConnectorErrorCode.CONFIGURATION_ERROR);
    }
    return carrier;
  }

  /**
   * Carrega e inicializa todos os conectores a partir de uma instância de SQLite3 ou mock.
   * @param {object} db Instância do sqlite3
   * @param {object} [options]
   */
  async loadFromDatabase(db, options = {}) {
    this.db = db;
    this.connectors.clear();

    const rows = await new Promise((resolve, reject) => {
      db.all('SELECT id, type, name, label, config, active FROM connectors WHERE active = 1', (err, rows) => {
        if (err) reject(err);
        else resolve(rows || []);
      });
    });

    for (const row of rows) {
      try {
        const instance = this.createConnectorInstance(row, options);
        this.register(instance);
      } catch (err) {
        console.error(`[ConnectorRegistry] Falha ao instanciar conector ID ${row.id}: ${err.message}`);
      }
    }

    return this.connectors.size;
  }

  /**
   * Executa checagem de saúde em todos os conectores ativos.
   */
  async healthCheckAll() {
    const results = {};
    for (const [id, conn] of this.connectors.entries()) {
      results[id] = await conn.healthCheck();
    }
    return results;
  }
}

module.exports = {
  ConnectorRegistry
};
