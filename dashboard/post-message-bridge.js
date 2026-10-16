/**
 * BUS-02: postMessage Bridge — Dashboard (parent) side.
 * Manages bidirectional communication with child iframes (Nexus, JEV).
 * INV-N03: NEVER use targetOrigin '*'.
 */
(function(root) {
  'use strict';

  const CHANNEL = 'bus-02';

  function getCurrentOrigin() {
    if (typeof root !== 'undefined' && root.location && root.location.origin) {
      return root.location.origin;
    }
    return 'http://127.0.0.1:8847';
  }

  // Target origins per iframe
  const ORIGINS = {
    nexus: 'http://127.0.0.1:5173',
    jev: getCurrentOrigin(),
    'jev-playbooks': getCurrentOrigin(),
  };

  function getKnownOrigins() {
    const origins = new Set([
      'http://127.0.0.1:5173',
      'http://localhost:5173',
      'http://127.0.0.1:8847',
      'http://localhost:8847',
      getCurrentOrigin(),
    ]);
    return origins;
  }

  // Registry of active iframe windows: name -> { window, origin }
  const registry = new Map();

  // Pending messages queue before iframe is ready: name -> [envelope]
  const pending = new Map();

  // Rate limit: max 100 msgs/s per origin
  const rateCounts = new Map();
  const rateTimer = setInterval(() => rateCounts.clear(), 1000);
  if (rateTimer && typeof rateTimer.unref === 'function') {
    rateTimer.unref();
  }

  /**
   * Flush pending messages when iframe becomes ready.
   * @param {string} name
   */
  function flushPending(name) {
    const msgs = pending.get(name) || [];
    pending.delete(name);
    const entry = registry.get(name);
    if (!entry || !entry.window) return;
    for (const envelope of msgs) {
      // INV-N03: targetOrigin is ALWAYS explicit
      entry.window.postMessage(envelope, entry.origin);
    }
  }

  /**
   * Register an iframe for communication.
   * @param {string} name - 'nexus' | 'jev' | 'jev-playbooks'
   * @param {HTMLIFrameElement|object} iframe
   */
  function registerIframe(name, iframe) {
    const targetOrigin = ORIGINS[name] || getCurrentOrigin();
    if (!targetOrigin || targetOrigin === '*') {
      throw new Error(`Invalid or unspecified targetOrigin for iframe: ${name}`);
    }
    const win = (iframe && iframe.contentWindow) ? iframe.contentWindow : iframe;
    registry.set(name, { window: win, origin: targetOrigin });
    flushPending(name);
  }

  /**
   * Send a typed message to a specific iframe.
   * INV-N03: targetOrigin is ALWAYS explicit, never '*'.
   * @param {string} target - iframe name
   * @param {string} type - message type
   * @param {any} payload - message payload
   */
  function send(target, type, payload) {
    const envelope = {
      type,
      channel: CHANNEL,
      payload,
      origin: getCurrentOrigin(),
      timestamp: Date.now(),
    };

    const entry = registry.get(target);
    if (!entry || !entry.window) {
      if (!pending.has(target)) pending.set(target, []);
      pending.get(target).push(envelope);
      return;
    }

    if (!entry.origin || entry.origin === '*') {
      throw new Error('INV-N03: Target origin cannot be wildcard *');
    }

    entry.window.postMessage(envelope, entry.origin);
  }

  /**
   * Global message listener handler — validates origin and envelope.
   * @param {MessageEvent|object} event
   * @returns {boolean} true if processed, false if dropped/ignored
   */
  function handleMessage(event) {
    if (!event || !event.origin) return false;

    // Validate origin
    const known = getKnownOrigins();
    if (!known.has(event.origin)) {
      return false; // Ignore unknown origins
    }

    // Rate limit check
    const currentCount = (rateCounts.get(event.origin) || 0) + 1;
    rateCounts.set(event.origin, currentCount);
    if (currentCount > 100) {
      return false; // Flood protection: max 100 msgs/s per origin
    }

    // Validate envelope
    const data = event.data || {};
    const { type, channel, payload } = data;
    if (channel !== CHANNEL || !type) {
      return false; // Not our message
    }

    // Dispatch by type
    switch (type) {
      case 'BRIDGE_READY':
        if (payload && payload.app) {
          flushPending(payload.app);
        }
        break;
      case 'HITL_REQUEST':
        if (typeof document !== 'undefined' && typeof document.dispatchEvent === 'function') {
          const ev = typeof CustomEvent === 'function'
            ? new CustomEvent('hitl-request', { detail: payload })
            : { type: 'hitl-request', detail: payload };
          document.dispatchEvent(ev);
        }
        break;
      case 'MISSION_UPDATE':
        if (typeof document !== 'undefined' && typeof document.dispatchEvent === 'function') {
          const ev = typeof CustomEvent === 'function'
            ? new CustomEvent('mission-update', { detail: payload })
            : { type: 'mission-update', detail: payload };
          document.dispatchEvent(ev);
        }
        break;
      default:
        break;
    }

    return true;
  }

  // Clear registry (helper for testing)
  function clearRegistry() {
    registry.clear();
    pending.clear();
  }

  // Reset rate limits (helper for testing)
  function resetRateLimit() {
    rateCounts.clear();
  }

  if (typeof root !== 'undefined' && typeof root.addEventListener === 'function') {
    root.addEventListener('message', handleMessage);
  }

  const BrainBridge = Object.freeze({
    CHANNEL,
    registerIframe,
    send,
    handleMessage,
    clearRegistry,
    resetRateLimit,
  });

  root.BrainBridge = BrainBridge;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = BrainBridge;
  }
})(typeof window !== 'undefined' ? window : globalThis);
