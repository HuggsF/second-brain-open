/**
 * BUS-02: postMessage adapter for JEV (child iframe side).
 * INV-N03: targetOrigin is window.location.origin (same-origin, explicit, never '*').
 */
export const CHANNEL = 'bus-02';

function getTargetOrigin(win) {
  if (win && win.location && win.location.origin && win.location.origin !== 'null') {
    return win.location.origin;
  }
  if (typeof window !== 'undefined' && window.location && window.location.origin && window.location.origin !== 'null') {
    return window.location.origin;
  }
  return 'http://127.0.0.1:8847';
}

/**
 * Send a typed message to parent window.
 * @param {string} type - message type
 * @param {any} payload - message payload
 * @param {Window} [win] - window reference
 */
export function send(type, payload, win = (typeof window !== 'undefined' ? window : null)) {
  const w = win || (typeof window !== 'undefined' ? window : null);
  if (!w || !w.parent) return;

  const origin = getTargetOrigin(w);
  const envelope = {
    type,
    channel: CHANNEL,
    payload,
    origin,
    timestamp: Date.now(),
  };

  // INV-N03: targetOrigin is ALWAYS explicit, never '*'
  w.parent.postMessage(envelope, origin);
}

/**
 * Listen for messages from parent window.
 * @param {(type: string, payload: any) => void} handler
 * @param {Window} [win] - window reference
 * @returns {() => void} unsubscribe function
 */
export function onMessage(handler, win = (typeof window !== 'undefined' ? window : null)) {
  const w = win || (typeof window !== 'undefined' ? window : null);
  if (!w || typeof w.addEventListener !== 'function') {
    return () => {};
  }

  const expectedOrigin = getTargetOrigin(w);
  const listener = (event) => {
    if (
      event.origin !== expectedOrigin &&
      event.origin !== 'http://127.0.0.1:8847' &&
      event.origin !== 'http://localhost:8847'
    ) {
      return;
    }
    const { type, channel, payload } = event.data || {};
    if (channel !== CHANNEL || !type) return;
    handler(type, payload);
  };

  w.addEventListener('message', listener);
  return () => {
    if (typeof w.removeEventListener === 'function') {
      w.removeEventListener('message', listener);
    }
  };
}

/**
 * Signal to Dashboard parent that JEV is ready to receive messages.
 * @param {string} [appName='jev']
 * @param {Window} [win]
 */
export function signalReady(appName = 'jev', win = (typeof window !== 'undefined' ? window : null)) {
  send('BRIDGE_READY', { app: appName }, win);
}
