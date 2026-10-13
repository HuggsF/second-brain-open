/**
 * WebSocket Transport para o Nexus Agent Office.
 *
 * Conecta ao backend Python (ws://127.0.0.1:8848) e traduz
 * eventos/comandos entre o simulation-adapter e o orchestrator.
 *
 * Reconexão automática com backoff exponencial.
 */

const DEFAULT_URL = 'ws://127.0.0.1:8848';
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 16000;

export function createWsTransport(url = DEFAULT_URL) {
  let ws = null;
  let reconnectAttempts = 0;
  let reconnectTimer = null;
  let disposed = false;
  const listeners = new Set();
  const pendingQueue = [];

  function connect() {
    if (disposed) return;

    try {
      ws = new WebSocket(url);
    } catch (err) {
      console.error('[ws-transport] Failed to create WebSocket:', err);
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      console.info(`[ws-transport] ✅ Connected to ${url}`);
      reconnectAttempts = 0;

      // Enviar mensagens enfileiradas durante a desconexão
      while (pendingQueue.length > 0) {
        const msg = pendingQueue.shift();
        try { ws.send(msg); } catch (_) { break; }
      }

      // Notificar listeners com um evento de conexão
      for (const cb of listeners) {
        cb({ type: 'CONNECTION', status: 'connected', url });
      }
    };

    ws.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (err) {
        console.warn('[ws-transport] Invalid JSON:', event.data?.slice?.(0, 100));
        return;
      }
      for (const cb of listeners) cb(data);
    };

    ws.onerror = (err) => {
      console.warn('[ws-transport] WebSocket error', err);
    };

    ws.onclose = (event) => {
      console.info(`[ws-transport] 🔴 Disconnected (code=${event.code})`);
      ws = null;

      // Notificar listeners
      for (const cb of listeners) {
        cb({ type: 'CONNECTION', status: 'disconnected', code: event.code });
      }

      if (!disposed) scheduleReconnect();
    };
  }

  function scheduleReconnect() {
    if (disposed || reconnectTimer) return;
    const delay = Math.min(RECONNECT_BASE_MS * (2 ** reconnectAttempts), RECONNECT_MAX_MS);
    reconnectAttempts++;
    console.info(`[ws-transport] Reconnecting in ${delay}ms (attempt ${reconnectAttempts})...`);
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  }

  // Conectar imediatamente
  connect();

  return {
    send(envelope) {
      const msg = typeof envelope === 'string' ? envelope : JSON.stringify(envelope);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(msg);
      } else {
        // Enfileirar para enviar quando reconectar
        if (pendingQueue.length < 64) {
          pendingQueue.push(msg);
        }
      }
    },

    subscribe(callback) {
      if (typeof callback !== 'function') return () => {};
      listeners.add(callback);
      return () => listeners.delete(callback);
    },

    get connected() {
      return ws !== null && ws.readyState === WebSocket.OPEN;
    },

    dispose() {
      disposed = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (ws) {
        ws.close(1000, 'disposed');
        ws = null;
      }
      listeners.clear();
      pendingQueue.length = 0;
    },
  };
}
