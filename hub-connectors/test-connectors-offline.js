/**
 * @file test-connectors-offline.js
 * @description Suíte de testes automatizados e isolados dos Conectores do Hub Logístico.
 * Executa sem bater em redes externas usando HTTP Mocking para comprovar todas as regras.
 */

const assert = require('assert');
const {
  BlingV3Connector,
  JTExpressConnector,
  CorpemWMSConnector,
  ConnectorRegistry,
  ConnectorErrorCode,
  isValidNfeAccessKey
} = require('./index');

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

async function runSuite() {
  console.log('\n============================================================');
  console.log('🧪 SUÍTE DE TESTES: CONECTORES DO HUB LOGÍSTICO (OFFLINE)');
  console.log('============================================================\n');

  // ----------------------------------------------------
  // TESTE 1: Validação de Chave de NF-e
  // ----------------------------------------------------
  await it('Validador de NF-e: Rejeita chaves vazias, curtas ou com 44 zeros', () => {
    assert.strictEqual(isValidNfeAccessKey(null), false);
    assert.strictEqual(isValidNfeAccessKey(''), false);
    assert.strictEqual(isValidNfeAccessKey('12345'), false);
    assert.strictEqual(isValidNfeAccessKey('00000000000000000000000000000000000000000000'), false, 'Sequência de zeros deve ser inválida');
    assert.strictEqual(isValidNfeAccessKey('32261061769169000103550010000279371000279371'), true, 'Chave válida de 44 dígitos deve passar');
  });

  // ----------------------------------------------------
  // TESTE 2: Bling OAuth - Renovação Automática Pró-Ativa
  // ----------------------------------------------------
  await it('BlingV3Connector: Renova token quando expiresAt está a menos de 10 min de expirar', async () => {
    let refreshCalls = 0;
    let savedConfig = null;

    const mockHttp = {
      request: async (opts) => {
        if (opts.url.includes('/oauth/token')) {
          refreshCalls++;
          return {
            status: 200,
            data: {
              access_token: 'NOVO_ACCESS_TOKEN_RENOVADO_XYZ',
              refresh_token: 'NOVO_REFRESH_TOKEN_999',
              expires_in: 21600
            }
          };
        }
        throw new Error(`Rota não esperada: ${opts.url}`);
      }
    };

    const bling = new BlingV3Connector({
      id: 1,
      name: 'Bling v3',
      config: {
        clientId: 'test_client_id',
        clientSecret: 'test_client_secret',
        accessToken: 'TOKEN_EXPIRANDO',
        refreshToken: 'REFRESH_TOKEN_123',
        expiresAt: Date.now() + (5 * 60 * 1000) // Expirando em 5 minutos!
      },
      httpClient: mockHttp,
      onConfigUpdate: async (id, cfg) => {
        savedConfig = cfg;
      }
    });

    const token = await bling.getValidAccessToken();

    assert.strictEqual(refreshCalls, 1, 'Deveria ter chamado refreshOAuthToken');
    assert.strictEqual(token, 'NOVO_ACCESS_TOKEN_RENOVADO_XYZ');
    assert.strictEqual(savedConfig.accessToken, 'NOVO_ACCESS_TOKEN_RENOVADO_XYZ');
    assert.strictEqual(savedConfig.refreshToken, 'NOVO_REFRESH_TOKEN_999');
    assert.ok(savedConfig.expiresAt > Date.now() + 20000000, 'expiresAt deve ser estendido');
  });

  // ----------------------------------------------------
  // TESTE 3: Bling getOrder com Extração de Rastreio Pré-Existente
  // ----------------------------------------------------
  await it('BlingV3Connector.getOrder: Captura rastreio existente em transporte.volumes[0].codigoRastreamento', async () => {
    const mockHttp = {
      request: async (opts) => {
        if (opts.url.includes('/pedidos/vendas/991827364')) {
          return {
            status: 200,
            data: {
              data: {
                id: 991827364,
                numero: 27937,
                data: '2026-10-13',
                contato: {
                  id: 123,
                  nome: 'Hugo Melo',
                  numeroDocumento: '111.222.333-44',
                  tipoPessoa: 'F',
                  telefone: '81999998888'
                },
                transporte: {
                  pesoBruto: 0.85,
                  etiqueta: {
                    nome: 'Hugo Melo',
                    endereco: 'Av Boa Viagem',
                    numero: '500',
                    bairro: 'Boa Viagem',
                    municipio: 'Recife',
                    uf: 'PE',
                    cep: '51011000'
                  },
                  volumes: [
                    {
                      id: 888777,
                      servico: 'JT_EXPRESS_PADRAO',
                      codigoRastreamento: 'JT8880192837465BR' // RASTREIO PRÉ-EXISTENTE!
                    }
                  ]
                },
                notaFiscal: { id: 555444 }
              }
            }
          };
        }
        if (opts.url.includes('/nfe/555444')) {
          return {
            status: 200,
            data: {
              data: {
                id: 555444,
                chaveAcesso: '32261061769169000103550010000279371000279371',
                numero: '27937',
                serie: '1'
              }
            }
          };
        }
        throw new Error(`Rota inesperada: ${opts.url}`);
      }
    };

    const bling = new BlingV3Connector({
      id: 1,
      config: {
        clientId: 'id',
        clientSecret: 'secret',
        accessToken: 'TOKEN_VALIDO',
        expiresAt: Date.now() + 3600000
      },
      httpClient: mockHttp
    });

    const order = await bling.getOrder('991827364');

    assert.strictEqual(order.orderId, '991827364');
    assert.strictEqual(order.orderNumber, '27937');
    assert.ok(order.existingTracking, 'existingTracking deve estar preenchido');
    assert.strictEqual(order.existingTracking.trackingNumber, 'JT8880192837465BR');
    assert.strictEqual(order.invoice.accessKey, '32261061769169000103550010000279371000279371');
    assert.strictEqual(order.shippingAddress.zipCode, '51011000');
  });

  // ----------------------------------------------------
  // TESTE 4: J&T Express - Proteção Anti-Duplicidade (Camada 1)
  // ----------------------------------------------------
  await it('JTExpressConnector.generateLabel: Reutiliza rastreio existente e NÃO chama /addOrder', async () => {
    let addOrderCalls = 0;

    const mockHttp = {
      request: async (opts) => {
        if (opts.url.includes('/addOrder')) {
          addOrderCalls++;
          return {
            status: 200,
            data: {
              responseitems: [{ success: 'true', billCode: 'NOVO_BILL_CODE_INDEVIDO' }]
            }
          };
        }
        throw new Error(`Rota inesperada: ${opts.url}`);
      }
    };

    const jt = new JTExpressConnector({
      id: 2,
      label: 'ESPIRITO SANTO - J&T',
      config: {
        code: 'J0086038727',
        acc: '899296264686898176',
        pwd: 'pwd',
        key: 'key',
        remetente: {
          nome: 'COSMETIC LOG',
          cep: '29135008',
          uf: 'ES',
          cidade: 'Viana',
          endereco: 'AV ALCACIBAS',
          numero: '800'
        }
      },
      httpClient: mockHttp
    });

    // Pedido que JÁ POSSUI rastreio
    const orderWithTracking = {
      orderId: '991827364',
      orderNumber: '27937',
      customer: { name: 'Hugo Melo', documentNumber: '11122233344' },
      shippingAddress: {
        recipientName: 'Hugo Melo',
        street: 'Av Boa Viagem',
        number: '500',
        city: 'Recife',
        state: 'PE',
        zipCode: '51011000'
      },
      packages: { grossWeightKg: 0.85, volumesCount: 1 },
      existingTracking: {
        trackingNumber: 'JT8880192837465BR'
      }
    };

    const result = await jt.generateLabel(orderWithTracking);

    assert.strictEqual(addOrderCalls, 0, '🚨 ERRO CRÍTICO: generateLabel chamou a J&T indevidamente!');
    assert.strictEqual(result.trackingNumber, 'JT8880192837465BR');
    assert.strictEqual(result.alreadyExisted, true);
    assert.strictEqual(result.reason, 'EXISTING_IN_ERP');
  });

  // ----------------------------------------------------
  // TESTE 5: J&T Express - Emissão Normal para Pedido Novo Sem Rastreio
  // ----------------------------------------------------
  await it('JTExpressConnector.generateLabel: Emite etiqueta normalmente para pedido novo', async () => {
    let addOrderCalls = 0;

    const mockHttp = {
      request: async (opts) => {
        if (opts.url.includes('/addOrder')) {
          addOrderCalls++;
          return {
            status: 200,
            data: {
              responseitems: [{ success: 'true', billCode: '888030999111222' }]
            }
          };
        }
        throw new Error(`Rota: ${opts.url}`);
      }
    };

    const jt = new JTExpressConnector({
      id: 2,
      config: {
        code: 'J0086038727',
        acc: '899296264686898176',
        pwd: 'pwd',
        key: 'key',
        remetente: {
          nome: 'COSMETIC LOG',
          cep: '29135008',
          uf: 'ES',
          cidade: 'Viana',
          endereco: 'AV ALCACIBAS',
          numero: '800'
        }
      },
      httpClient: mockHttp
    });

    const newOrder = {
      orderId: '100200300',
      orderNumber: '55441',
      customer: { name: 'Cliente Novo', documentNumber: '99988877766' },
      shippingAddress: {
        recipientName: 'Cliente Novo',
        street: 'Rua das Flores',
        number: '123',
        city: 'Viana',
        state: 'ES',
        zipCode: '29135000'
      },
      packages: { grossWeightKg: 1.2, volumesCount: 1 },
      invoice: {
        accessKey: '32261061769169000103550010000279371000279371'
      },
      existingTracking: null // Sem rastreio prévio!
    };

    const result = await jt.generateLabel(newOrder);

    assert.strictEqual(addOrderCalls, 1);
    assert.strictEqual(result.trackingNumber, '888030999111222');
    assert.strictEqual(result.alreadyExisted, false);
    assert.ok(result.txlogisticId.startsWith('HUB-100200300-'));
  });

  // ----------------------------------------------------
  // TESTE 6: Bling updateTracking Idempotente
  // ----------------------------------------------------
  await it('BlingV3Connector.updateTracking: Dispensa PUT redundante se rastreio já for igual', async () => {
    let putCalls = 0;

    const mockHttp = {
      request: async (opts) => {
        if (opts.method === 'GET' && opts.url.includes('/pedidos/vendas/991827364')) {
          return {
            status: 200,
            data: {
              data: {
                id: 991827364,
                transporte: {
                  volumes: [
                    { id: 777666, codigoRastreamento: '888030999111222' } // Já tem esse rastreio!
                  ]
                }
              }
            }
          };
        }
        if (opts.method === 'PUT') {
          putCalls++;
          return { status: 200, data: {} };
        }
        throw new Error(`Rota: ${opts.url}`);
      }
    };

    const bling = new BlingV3Connector({
      id: 1,
      config: {
        clientId: 'id',
        clientSecret: 'secret',
        accessToken: 'TOKEN',
        expiresAt: Date.now() + 3600000
      },
      httpClient: mockHttp
    });

    const res = await bling.updateTracking('991827364', '888030999111222');

    assert.strictEqual(putCalls, 0, 'Não deve fazer PUT quando o rastreio já é idêntico!');
    assert.strictEqual(res.alreadyUpToDate, true);
  });

  // ----------------------------------------------------
  // TESTE 7: Corpem WMS - Ordem de Separação (DEM-12)
  // ----------------------------------------------------
  await it('CorpemWMSConnector.sendSeparationOrder: Envia Ordem de Separação formatada', async () => {
    let sentPayload = null;

    const mockHttp = {
      request: async (opts) => {
        sentPayload = opts.data;
        return {
          status: 200,
          data: { status: 'OK', separation_id: 'WMS-SEP-8899' }
        };
      }
    };

    const corpem = new CorpemWMSConnector({
      id: 4,
      config: { url: 'https://wms.corpem.com.br/api/separacao', apiKey: 'CORPEM_KEY_123' },
      httpClient: mockHttp
    });

    const order = {
      orderId: '778899',
      orderNumber: '1234',
      customer: { name: 'Carlos Lima', documentNumber: '12345678900' },
      shippingAddress: {
        recipientName: 'Carlos Lima',
        street: 'Rua A',
        number: '10',
        city: 'Viana',
        state: 'ES',
        zipCode: '29135000'
      },
      packages: { grossWeightKg: 0.5 },
      existingTracking: { trackingNumber: '88801928374' }
    };

    const res = await corpem.sendSeparationOrder(order);

    assert.strictEqual(res.success, true);
    assert.strictEqual(sentPayload.codigo_pedido_erp, '778899');
    assert.strictEqual(sentPayload.rastreio_transportadora, '88801928374');
  });

  // ----------------------------------------------------
  // TESTE 8: ConnectorRegistry - Carregamento e Fábrica
  // ----------------------------------------------------
  await it('ConnectorRegistry: Instancia conector pelo tipo correto', () => {
    const registry = new ConnectorRegistry();

    const erp = registry.createConnectorInstance({
      id: 1,
      type: 'erp',
      name: 'Bling v3',
      config: JSON.stringify({ clientId: 'c', clientSecret: 's' }),
      active: 1
    });
    assert.ok(erp instanceof BlingV3Connector);

    const carrier = registry.createConnectorInstance({
      id: 2,
      type: 'carrier',
      name: 'J&T Express',
      config: JSON.stringify({ code: 'c', pwd: 'p', key: 'k', remetente: { cep: '29135008' } }),
      active: 1
    });
    assert.ok(carrier instanceof JTExpressConnector);

    registry.register(erp);
    registry.register(carrier);

    assert.strictEqual(registry.getPrimaryErp().name, 'Bling v3');
    assert.strictEqual(registry.getCarrier(2).name, 'J&T Express');
  });

  console.log('\n------------------------------------------------------------');
  console.log(`📊 RESULTADO FINAL: ${testsPassed} Aprovados | ${testsFailed} Falhas`);
  console.log('------------------------------------------------------------\n');

  if (testsFailed > 0) {
    process.exit(1);
  }
}

runSuite().catch(err => {
  console.error('Erro na suíte de testes:', err);
  process.exit(1);
});
