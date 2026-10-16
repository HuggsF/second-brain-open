import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { send, onMessage, signalReady } from '../post-message.js';
import { syncParentTheme } from '../theme.js';

describe('post-message in JEV', () => {
  let originalParent;

  beforeEach(() => {
    originalParent = window.parent;
  });

  afterEach(() => {
    window.parent = originalParent;
    vi.restoreAllMocks();
  });

  it('send() uses channel bus-02, timestamp, and explicit targetOrigin (never "*")', () => {
    const postMessageMock = vi.fn();
    window.parent = { postMessage: postMessageMock };

    send('TEST_TYPE', { foo: 'bar' });

    expect(postMessageMock).toHaveBeenCalledTimes(1);
    const [envelope, targetOrigin] = postMessageMock.mock.calls[0];

    expect(targetOrigin).not.toBe('*');
    expect(targetOrigin).toBe(window.location.origin);
    expect(envelope).toMatchObject({
      channel: 'bus-02',
      type: 'TEST_TYPE',
      payload: { foo: 'bar' },
      origin: window.location.origin,
    });
    expect(typeof envelope.timestamp).toBe('number');
  });

  it('signalReady() sends BRIDGE_READY with app name', () => {
    const postMessageMock = vi.fn();
    window.parent = { postMessage: postMessageMock };

    signalReady('jev');

    expect(postMessageMock).toHaveBeenCalledWith(
      expect.objectContaining({
        channel: 'bus-02',
        type: 'BRIDGE_READY',
        payload: { app: 'jev' },
      }),
      window.location.origin
    );
  });

  it('onMessage filters out events with wrong origin or wrong channel', () => {
    const handler = vi.fn();
    const unsubscribe = onMessage(handler);

    // Event with wrong origin
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'http://malicious-origin.com',
        data: { channel: 'bus-02', type: 'SOME_TYPE', payload: {} },
      })
    );
    expect(handler).not.toHaveBeenCalled();

    // Event with wrong channel
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        data: { channel: 'other-channel', type: 'SOME_TYPE', payload: {} },
      })
    );
    expect(handler).not.toHaveBeenCalled();

    // Event with missing type
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        data: { channel: 'bus-02', payload: {} },
      })
    );
    expect(handler).not.toHaveBeenCalled();

    // Valid event
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        data: { channel: 'bus-02', type: 'THEME_SYNC', payload: { theme: 'dark' } },
      })
    );
    expect(handler).toHaveBeenCalledWith('THEME_SYNC', { theme: 'dark' });

    unsubscribe();
    // After unsubscribe, no more calls
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        data: { channel: 'bus-02', type: 'THEME_SYNC', payload: { theme: 'light' } },
      })
    );
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('syncParentTheme applies theme from THEME_SYNC message as primary', () => {
    const childDoc = document.implementation.createHTMLDocument('child');
    const win = {
      document: childDoc,
      parent: {}, // parent without document (cross-origin or postMessage only)
      addEventListener: window.addEventListener.bind(window),
      removeEventListener: window.removeEventListener.bind(window),
      location: window.location,
    };

    const stop = syncParentTheme(win);

    // Post THEME_SYNC message
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        data: {
          channel: 'bus-02',
          type: 'THEME_SYNC',
          payload: { theme: 'dark' },
        },
      })
    );

    expect(childDoc.documentElement.dataset.theme).toBe('dark');

    // Send another theme
    window.dispatchEvent(
      new MessageEvent('message', {
        origin: window.location.origin,
        data: {
          channel: 'bus-02',
          type: 'THEME_SYNC',
          payload: { theme: 'light' },
        },
      })
    );

    expect(childDoc.documentElement.dataset.theme).toBe('light');

    stop();
  });
});
