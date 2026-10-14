/**
 * @file types.js
 * @description Contratos de dados universais e validadores para o ecossistema de Conectores do Hub Logístico.
 */

const ConnectorErrorCode = Object.freeze({
  UNAUTHORIZED: 'UNAUTHORIZED',
  TOKEN_EXPIRED: 'TOKEN_EXPIRED',
  INVALID_REFRESH_TOKEN: 'INVALID_REFRESH_TOKEN',
  RATE_LIMITED: 'RATE_LIMITED',
  ORDER_NOT_FOUND: 'ORDER_NOT_FOUND',
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  INVOICE_INVALID: 'INVOICE_INVALID',
  DUPLICATE_EMISSION_PREVENTED: 'DUPLICATE_EMISSION_PREVENTED',
  CARRIER_REJECTED: 'CARRIER_REJECTED',
  UPSTREAM_UNAVAILABLE: 'UPSTREAM_UNAVAILABLE',
  NETWORK_TIMEOUT: 'NETWORK_TIMEOUT',
  CONFIGURATION_ERROR: 'CONFIGURATION_ERROR',
});

/**
 * Validação de chave de acesso de NF-e (44 dígitos numéricos não nulos).
 * Bloqueia chaves fictícias como 00000000000000000000000000000000000000000000.
 */
function isValidNfeAccessKey(key) {
  if (!key || typeof key !== 'string') return false;
  const cleaned = key.trim();
  if (cleaned.length !== 44) return false;
  if (!/^\d{44}$/.test(cleaned)) return false;
  // Bloquear sequência de zeros
  if (/^0{44}$/.test(cleaned)) return false;
  return true;
}

/**
 * Limpa e padroniza CEP (8 dígitos numéricos).
 */
function cleanZipCode(zip) {
  if (!zip) return '';
  return String(zip).replace(/\D/g, '').padStart(8, '0').slice(0, 8);
}

/**
 * Limpa documento (CPF ou CNPJ).
 */
function cleanDocument(doc) {
  if (!doc) return '';
  return String(doc).replace(/\D/g, '');
}

/**
 * Valida se um objeto obedece a estrutura mínima de UniversalOrder.
 */
function validateUniversalOrder(order) {
  const errors = [];
  if (!order) {
    return { valid: false, errors: ['Pedido não fornecido'] };
  }

  if (!order.orderId) errors.push('Campo orderId obrigatório');
  if (!order.customer || !order.customer.name) errors.push('Nome do cliente obrigatório');
  
  if (!order.shippingAddress) {
    errors.push('shippingAddress obrigatório');
  } else {
    const addr = order.shippingAddress;
    if (!addr.street) errors.push('Endereço/rua obrigatório');
    if (!addr.city) errors.push('Cidade obrigatória');
    if (!addr.state || addr.state.length !== 2) errors.push('UF de 2 letras obrigatória');
    if (!cleanZipCode(addr.zipCode) || cleanZipCode(addr.zipCode).length !== 8) {
      errors.push('CEP de 8 dígitos obrigatório');
    }
  }

  if (!order.packages) {
    errors.push('packages obrigatório');
  } else {
    if (typeof order.packages.grossWeightKg !== 'number' || order.packages.grossWeightKg <= 0) {
      errors.push('grossWeightKg deve ser um número positivo (> 0)');
    }
  }

  if (order.invoice && order.invoice.accessKey) {
    if (!isValidNfeAccessKey(order.invoice.accessKey)) {
      errors.push(`Chave de acesso da NF-e inválida: "${order.invoice.accessKey}" (deve ter 44 dígitos numéricos)`);
    }
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

module.exports = {
  ConnectorErrorCode,
  isValidNfeAccessKey,
  cleanZipCode,
  cleanDocument,
  validateUniversalOrder
};
