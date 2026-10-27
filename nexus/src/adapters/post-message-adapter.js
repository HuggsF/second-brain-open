/**
 * BUS-02: postMessage adapter for Nexus (child iframe side).
 * INV-N03: targetOrigin is ALWAYS explicit, never '*'.
 */
export const CHANNEL = 'bus-02';
export const PARENT_ORIGIN = 'http://127.0.0.1:8847';

const ACCEPTED_ORIGINS = new Set([
  PARENT_ORIGIN,
  'http://localhost:8847',
]);

/**
 * Send a typed message to the Dashboard parent.
 * @param {string} type - message type
 * @param {any} payload - message payload
 */
export function send(type, payload) {
  if (typeof window === 'undefined' || !window.parent) return;

  const origin = window.location && window.location.origin ? window.location.origin : '';
  const envelope = {
    type,
    channel: CHANNEL,
    payload,
    origin,
    timestamp: Date.now(),
  };

  // INV-N03: explicit targetOrigin, never '*'
  window.parent.postMessage(envelope, PARENT_ORIGIN);
}

/**
 * Listen for messages from Dashboard parent.
 * @param {(type: string, payload: any) => void} handler
 * @returns {() => void} unsubscribe function
 */
export function onMessage(handler) {
  if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') {
    return () => {};
  }

  const listener = (event) => {
    if (!ACCEPTED_ORIGINS.has(event.origin)) return;
    const { type, channel, payload } = event.data || {};
    if (channel !== CHANNEL || !type) return;
    handler(type, payload);
  };

  window.addEventListener('message', listener);
  return () => window.removeEventListener('message', listener);
}

/**
 * Signal to Dashboard parent that Nexus is ready to receive messages.
 */
export function signalReady() {
  send('BRIDGE_READY', { app: 'nexus' });
}
