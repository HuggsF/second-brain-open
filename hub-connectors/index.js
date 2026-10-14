/**
 * @file index.js
 * @description Ponto de entrada do ecossistema de Conectores do Hub Logístico KIOSK Brands.
 */

const { BaseConnector, ConnectorError } = require('./BaseConnector');
const { BlingV3Connector } = require('./BlingV3Connector');
const { JTExpressConnector } = require('./JTExpressConnector');
const { CorpemWMSConnector } = require('./CorpemWMSConnector');
const { ConnectorRegistry } = require('./ConnectorRegistry');
const types = require('./types');

module.exports = {
  BaseConnector,
  ConnectorError,
  BlingV3Connector,
  JTExpressConnector,
  CorpemWMSConnector,
  ConnectorRegistry,
  ...types
};
