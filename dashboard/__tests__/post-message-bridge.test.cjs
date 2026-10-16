'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

// Require the bridge module
const Bridge = require('../post-message-bridge.js');

test('Bridge exports expected interface', () => {
  assert.equal(typeof Bridge.registerIframe, 'function');
  assert.equal(typeof Bridge.send, 'function');
  assert.equal(typeof Bridge.handleMessage, 'function');
  assert.equal(Bridge.CHANNEL, 'bus-02');
});

test('INV-N03: targetOrigin is NEVER "*"', () => {
  const sent = [];
  const fakeWindow = {
    postMessage: (msg, targetOrigin) => {
      sent.push({ msg, targetOrigin });
    }
  };

  Bridge.registerIframe('nexus', { contentWindow: fakeWindow });
  Bridge.send('nexus', 'TEST_EVENT', { foo: 'bar' });

  assert.equal(sent.length, 1);
  assert.notEqual(sent[0].targetOrigin, '*');
  assert.equal(sent[0].targetOrigin, 'http://127.0.0.1:5173');
  assert.equal(sent[0].msg.channel, 'bus-02');
  assert.equal(sent[0].msg.type, 'TEST_EVENT');
  assert.deepEqual(sent[0].msg.payload, { foo: 'bar' });
  assert.ok(sent[0].msg.timestamp > 0);
});

test('queues messages before iframe is registered and flushes on registration or BRIDGE_READY', () => {
  const sent = [];
  const fakeWindow = {
    postMessage: (msg, targetOrigin) => {
      sent.push({ msg, targetOrigin });
    }
  };

  Bridge.clearRegistry?.();
  Bridge.send('jev', 'THEME_SYNC', { theme: 'dark' });
  assert.equal(sent.length, 0, 'Should queue message when iframe not registered');

  Bridge.registerIframe('jev', { contentWindow: fakeWindow });
  assert.equal(sent.length, 1, 'Should flush queued messages once registered');
  assert.equal(sent[0].msg.type, 'THEME_SYNC');
  assert.equal(sent[0].msg.payload.theme, 'dark');
});

test('ignores messages from unknown origins (strict origin validation)', () => {
  let customEventFired = false;
  const originalDoc = globalThis.document;
  globalThis.document = {
    dispatchEvent: (ev) => {
      customEventFired = true;
    }
  };

  try {
    const ignored = Bridge.handleMessage({
      origin: 'http://malicious-site.com',
      data: {
        channel: 'bus-02',
        type: 'HITL_REQUEST',
        payload: { action: 'drop_database' }
      }
    });

    assert.equal(ignored, false);
    assert.equal(customEventFired, false);
  } finally {
    globalThis.document = originalDoc;
  }
});

test('ignores messages with invalid channel or missing type', () => {
  let customEventFired = false;
  const originalDoc = globalThis.document;
  globalThis.document = {
    dispatchEvent: () => {
      customEventFired = true;
    }
  };

  try {
    // Wrong channel
    let res = Bridge.handleMessage({
      origin: 'http://127.0.0.1:5173',
      data: {
        channel: 'random-channel',
        type: 'HITL_REQUEST',
        payload: {}
      }
    });
    assert.equal(res, false);
    assert.equal(customEventFired, false);

    // Missing type
    res = Bridge.handleMessage({
      origin: 'http://127.0.0.1:5173',
      data: {
        channel: 'bus-02',
        payload: {}
      }
    });
    assert.equal(res, false);
    assert.equal(customEventFired, false);
  } finally {
    globalThis.document = originalDoc;
  }
});

test('handles BRIDGE_READY from valid origin and dispatches known events', () => {
  let dispatched = null;
  const originalDoc = globalThis.document;
  globalThis.document = {
    dispatchEvent: (ev) => {
      dispatched = ev;
    }
  };

  try {
    const handledHitl = Bridge.handleMessage({
      origin: 'http://127.0.0.1:5173',
      data: {
        channel: 'bus-02',
        type: 'HITL_REQUEST',
        payload: { request_id: '123' }
      }
    });
    assert.equal(handledHitl, true);
    assert.ok(dispatched);
    assert.equal(dispatched.type, 'hitl-request');
    assert.deepEqual(dispatched.detail, { request_id: '123' });

    dispatched = null;
    const handledMission = Bridge.handleMessage({
      origin: 'http://127.0.0.1:5173',
      data: {
        channel: 'bus-02',
        type: 'MISSION_UPDATE',
        payload: { mission_id: 'm-1' }
      }
    });
    assert.equal(handledMission, true);
    assert.ok(dispatched);
    assert.equal(dispatched.type, 'mission-update');
    assert.deepEqual(dispatched.detail, { mission_id: 'm-1' });
  } finally {
    globalThis.document = originalDoc;
  }
});

test('rate limits flood from an origin (>100 msgs/sec)', () => {
  Bridge.resetRateLimit?.();
  const origin = 'http://127.0.0.1:5173';
  let accepted = 0;
  let rejected = 0;

  for (let i = 0; i < 110; i++) {
    const ok = Bridge.handleMessage({
      origin,
      data: {
        channel: 'bus-02',
        type: 'PING',
        payload: { i }
      }
    });
    if (ok) accepted++;
    else rejected++;
  }

  assert.equal(accepted, 100);
  assert.equal(rejected, 10);
});
