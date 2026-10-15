// The dashboard keeps its theme in <html data-theme>; the embedded app mirrors it when it runs in a
// same-origin iframe. Cross-origin or top-level contexts are left to prefers-color-scheme.
export function syncParentTheme(win = window) {
  const noop = () => {};
  try {
    if (!win || win.parent === win) return noop;
    const parentRoot = win.parent.document.documentElement;
    const ownRoot = win.document.documentElement;
    const copy = () => {
      const theme = parentRoot.dataset.theme;
      if (theme) ownRoot.dataset.theme = theme;
      else delete ownRoot.dataset.theme;
    };
    copy();
    const Observer = win.MutationObserver || globalThis.MutationObserver;
    if (!Observer) return noop;
    const observer = new Observer(copy);
    observer.observe(parentRoot, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  } catch {
    return noop;
  }
}
