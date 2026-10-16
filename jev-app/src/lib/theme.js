import { onMessage } from './post-message.js';

export function syncParentTheme(win = window) {
  const noop = () => {};
  if (!win || win.parent === win) return noop;

  const disconnects = [];

  // Primary: postMessage THEME_SYNC (BUS-02)
  try {
    const unsub = onMessage((type, payload) => {
      if (type === 'THEME_SYNC') {
        const ownRoot = win.document ? win.document.documentElement : null;
        if (ownRoot) {
          if (payload && payload.theme) {
            ownRoot.dataset.theme = payload.theme;
          } else {
            delete ownRoot.dataset.theme;
          }
        }
      }
    }, win);
    if (typeof unsub === 'function') {
      disconnects.push(unsub);
    }
  } catch {
    /* ignore if postMessage setup fails */
  }

  // Fallback: MutationObserver (same-origin DOM inspection)
  try {
    const parentRoot = win.parent.document.documentElement;
    const ownRoot = win.document.documentElement;
    const copy = () => {
      const theme = parentRoot.dataset.theme;
      if (theme) ownRoot.dataset.theme = theme;
      else delete ownRoot.dataset.theme;
    };
    copy();
    const Observer = win.MutationObserver || globalThis.MutationObserver;
    if (Observer) {
      const observer = new Observer(copy);
      observer.observe(parentRoot, { attributes: true, attributeFilter: ['data-theme'] });
      disconnects.push(() => observer.disconnect());
    }
  } catch {
    /* cross-origin: MutationObserver cannot access parent.document; relies on postMessage */
  }

  return () => {
    for (const fn of disconnects) {
      try { fn(); } catch (_) { /* swallow */ }
    }
  };
}
