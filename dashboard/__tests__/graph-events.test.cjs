'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const GRAPH_EVENTS_PATH = path.join(__dirname, '../graph-events.js');

function createEnvironment() {
  const eventSources = [];
  const webSockets = [];
  const activeTimers = new Map();
  let nextTimerId = 1;

  class MockEventSource {
    constructor(url) {
      this.url = url;
      this.readyState = 0; // CONNECTING
      this.onopen = null;
      this.onmessage = null;
      this.onerror = null;
      this.closed = false;
      eventSources.push(this);
    }
    open() {
      this.readyState = 1;
      if (this.onopen) this.onopen();
    }
    send(data) {
      if (this.onmessage) this.onmessage({ data: typeof data === 'string' ? data : JSON.stringify(data) });
    }
    error() {
      if (this.onerror) this.onerror(new Error('SSE connection error'));
    }
    close() {
      this.closed = true;
      this.readyState = 2;
    }
  }

  class MockWebSocket {
    constructor(url) {
      this.url = url;
      this.readyState = 0;
      this.onopen = null;
      this.onmessage = null;
      this.onerror = null;
      this.onclose = null;
      this.closed = false;
      webSockets.push(this);
    }
    open() {
      this.readyState = 1;
      if (this.onopen) this.onopen();
    }
    send(data) {
      if (this.onmessage) this.onmessage({ data: typeof data === 'string' ? data : JSON.stringify(data) });
    }
    error() {
      if (this.onerror) this.onerror(new Error('WS connection error'));
    }
    close() {
      this.closed = true;
      this.readyState = 3;
      if (this.onclose) this.onclose();
    }
  }

  const customSetTimeout = (fn, delay) => {
    const id = nextTimerId++;
    activeTimers.set(id, { fn, delay });
    return id;
  };

  const customClearTimeout = (id) => {
    activeTimers.delete(id);
  };

  const fireTimers = () => {
    const pending = [...activeTimers.entries()];
    activeTimers.clear();
    for (const [, timer] of pending) {
      timer.fn();
    }
  };

  const context = vm.createContext({
    EventSource: MockEventSource,
    WebSocket: MockWebSocket,
    setTimeout: customSetTimeout,
    clearTimeout: customClearTimeout,
    Date,
    Map,
    Set,
    JSON,
    Math,
    crypto: { randomUUID: () => 'test-uuid-1234' },
    console,
  });

  const code = fs.readFileSync(GRAPH_EVENTS_PATH, 'utf8');
  vm.runInContext(code, context);

  return {
    BrainGraphEvents: context.BrainGraphEvents,
    eventSources,
    webSockets,
    activeTimers,
    fireTimers,
  };
}

test('BUS-01-FE: SSE_ENDPOINT connects to /v1/events', () => {
  const env = createEnvironment();
  const BGE = env.BrainGraphEvents;

  BGE.connect();

  assert.equal(env.eventSources.length, 1, 'EventSource should be created on connect()');
  assert.equal(
    env.eventSources[0].url,
    '/v1/events',
    'SSE_ENDPOINT must be /v1/events (migrated from legacy /v1/graph-events)'
  );
  if (BGE.SSE_ENDPOINT !== undefined) {
    assert.equal(BGE.SSE_ENDPOINT, '/v1/events');
  }

  BGE.disconnect();
});

test('BUS-01-FE: channel filtering accepts graph events and ignores other channels', () => {
  const env = createEnvironment();
  const BGE = env.BrainGraphEvents;
  const received = [];

  BGE.subscribe(event => received.push(event));
  BGE.connect();

  const sse = env.eventSources[0];
  sse.open();

  // 1. Channel 'graph' event -> MUST be emitted
  sse.send({
    channel: 'graph',
    agent: 'noah',
    action: 'query',
    nodes: ['node-1'],
    detail: 'Semantic search',
  });

  // 2. Channel 'tool' event -> MUST be ignored
  sse.send({
    channel: 'tool',
    agent: 'theo',
    action: 'tool.call',
    nodes: ['node-tool'],
    detail: 'Tool invocation',
  });

  // 3. Channel 'mission' event -> MUST be ignored
  sse.send({
    channel: 'mission',
    agent: 'maia',
    action: 'task.event',
    nodes: ['node-mission'],
    detail: 'Mission step',
  });

  // 4. Channel 'system' event -> MUST be ignored
  sse.send({
    channel: 'system',
    agent: 'system',
    action: 'heartbeat',
    nodes: ['node-sys'],
  });

  // Filter out connection events for checking payload events
  const payloadEvents = received.filter(e => e.type !== 'connection');

  assert.equal(payloadEvents.length, 1, 'Only graph channel event should be emitted');
  assert.equal(payloadEvents[0].agent, 'noah');
  assert.equal(payloadEvents[0].action, 'query');
  assert.deepEqual(payloadEvents[0].nodes, ['node-1']);

  // Check eventLog
  const log = BGE.getLog();
  assert.equal(log.length, 1, 'getLog() should only contain the graph event');
  assert.equal(log[0].agent, 'noah');

  // Check pulses
  const pulses = BGE.getPulses();
  assert.ok(pulses.has('node-1'), 'Active pulses must include node-1');
  assert.ok(!pulses.has('node-tool'), 'Active pulses must not include ignored events');

  BGE.disconnect();
});

test('BUS-01-FE: backward compatibility - events without channel field still pass', () => {
  const env = createEnvironment();
  const BGE = env.BrainGraphEvents;
  const received = [];

  BGE.subscribe(event => received.push(event));
  BGE.connect();

  const sse = env.eventSources[0];
  sse.open();

  // Legacy event without channel field
  sse.send({
    agent: 'lia',
    action: 'draft_adr',
    nodes: ['adr-node'],
  });

  const payloadEvents = received.filter(e => e.type !== 'connection');
  assert.equal(payloadEvents.length, 1, 'Legacy event without channel field must still pass');
  assert.equal(payloadEvents[0].agent, 'lia');
  assert.deepEqual(payloadEvents[0].nodes, ['adr-node']);

  BGE.disconnect();
});

test('INV-N05: fallback chain SSE error -> WS -> simulation is preserved', () => {
  const env = createEnvironment();
  const BGE = env.BrainGraphEvents;
  const connectionModes = [];

  BGE.subscribe(event => {
    if (event.type === 'connection') {
      connectionModes.push(event.mode);
    }
  });

  assert.equal(BGE.getMode(), 'disconnected');
  assert.equal(BGE.isConnected(), false);

  // 1. Connect initiates SSE
  BGE.connect();
  assert.equal(env.eventSources.length, 1);
  const sse = env.eventSources[0];

  // SSE connects successfully
  sse.open();
  assert.equal(BGE.getMode(), 'sse');
  assert.equal(BGE.isConnected(), true);
  assert.ok(connectionModes.includes('sse'));

  // 2. SSE errors out -> falls back to WS via reconnect timer
  sse.error();
  assert.equal(BGE.getMode(), 'disconnected');
  assert.equal(BGE.isConnected(), false);
  assert.equal(sse.closed, true);

  // Fire reconnect timer -> should attempt WS connection
  env.fireTimers();
  assert.equal(env.webSockets.length, 1, 'WebSocket fallback should be attempted');
  assert.equal(env.webSockets[0].url, 'ws://127.0.0.1:8848');

  const ws = env.webSockets[0];
  ws.open();
  assert.equal(BGE.getMode(), 'ws');
  assert.equal(BGE.isConnected(), true);

  // 3. WS closes -> attempts reconnect
  ws.close();
  assert.equal(BGE.getMode(), 'disconnected');
  assert.equal(BGE.isConnected(), false);

  // 4. Test simulation fallback when no connection connects within 3s
  BGE.disconnect();
  const simEnv = createEnvironment();
  const simBGE = simEnv.BrainGraphEvents;

  simBGE.connect();
  assert.equal(simBGE.getMode(), 'disconnected');

  // Let 3s timer fire without opening SSE
  simEnv.fireTimers();
  assert.equal(simBGE.getMode(), 'simulated', 'Must fall back to simulation when connection fails');

  simBGE.disconnect();
  assert.equal(simBGE.getMode(), 'disconnected');
});
