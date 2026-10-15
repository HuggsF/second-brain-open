import { describe, expect, it } from 'vitest';
import { syncParentTheme } from './theme.js';

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

function makeFrame(parentTheme) {
  const parentDoc = document.implementation.createHTMLDocument('parent');
  if (parentTheme) parentDoc.documentElement.dataset.theme = parentTheme;
  const childDoc = document.implementation.createHTMLDocument('child');
  const win = { document: childDoc, parent: { document: parentDoc } };
  return { win, parentDoc, childDoc };
}

describe('syncParentTheme', () => {
  it('copies the parent data-theme and follows later changes until cleanup', async () => {
    const { win, parentDoc, childDoc } = makeFrame('light');
    const stop = syncParentTheme(win);
    expect(childDoc.documentElement.dataset.theme).toBe('light');
    parentDoc.documentElement.dataset.theme = 'dark';
    await tick();
    expect(childDoc.documentElement.dataset.theme).toBe('dark');
    stop();
    parentDoc.documentElement.dataset.theme = 'light';
    await tick();
    expect(childDoc.documentElement.dataset.theme).toBe('dark');
  });

  it('removes the attribute when the parent has none', () => {
    const { win, childDoc } = makeFrame(null);
    childDoc.documentElement.dataset.theme = 'dark';
    syncParentTheme(win)();
    expect(childDoc.documentElement.dataset.theme).toBeUndefined();
  });

  it('is a no-op at the top level', () => {
    const childDoc = document.implementation.createHTMLDocument('child');
    const win = { document: childDoc };
    win.parent = win;
    const stop = syncParentTheme(win);
    expect(childDoc.documentElement.dataset.theme).toBeUndefined();
    expect(() => stop()).not.toThrow();
  });

  it('does not throw when the parent is cross-origin', () => {
    const childDoc = document.implementation.createHTMLDocument('child');
    const parent = {};
    Object.defineProperty(parent, 'document', {
      get() {
        throw new DOMException('Blocked a frame', 'SecurityError');
      },
    });
    let stop;
    expect(() => {
      stop = syncParentTheme({ document: childDoc, parent });
    }).not.toThrow();
    expect(() => stop()).not.toThrow();
    expect(childDoc.documentElement.dataset.theme).toBeUndefined();
  });
});
