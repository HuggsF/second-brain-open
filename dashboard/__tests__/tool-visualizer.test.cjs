'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { dom, find } = require('../tests/topology-dom.cjs');

const VISUALIZER_PATH = path.join(__dirname, '../tool-visualizer.js');

// Mock EventSource for SSE testing
class MockEventSource {
  static instances = [];
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.closed = false;
    MockEventSource.instances.push(this);
  }
  open() {
    this.readyState = 1;
    if (this.onopen) this.onopen();
  }
  send(data) {
    if (this.onmessage) {
      this.onmessage({ data: typeof data === 'string' ? data : JSON.stringify(data) });
    }
  }
  error(err) {
    if (this.onerror) this.onerror(err || new Error('SSE error'));
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
}

function loadVisualizerModule() {
  MockEventSource.instances = [];
  globalThis.EventSource = MockEventSource;
  // If previously required, delete from cache to get a fresh instance
  delete require.cache[require.resolve(VISUALIZER_PATH)];
  return require(VISUALIZER_PATH);
}

test('1. Syntax check: tool-visualizer.js compiles without error', () => {
  assert.ok(fs.existsSync(VISUALIZER_PATH), 'tool-visualizer.js must exist');
  const source = fs.readFileSync(VISUALIZER_PATH, 'utf8');
  assert.doesNotThrow(() => {
    new vm.Script(source, { filename: 'tool-visualizer.js' });
  });
});

test('2. Module exports expected interface', () => {
  const Visualizer = loadVisualizerModule();
  assert.equal(typeof Visualizer.render, 'function', 'render must be a function');
  assert.equal(typeof Visualizer.dispose, 'function', 'dispose must be a function');
  assert.equal(Visualizer.MAX_EVENTS, 200, 'MAX_EVENTS must be 200');
});

test('3. Empty state shows "Nenhuma tool call" message when no events', () => {
  const Visualizer = loadVisualizerModule();
  const { main, U } = dom();
  const session = Visualizer.render(main, U);

  const emptyEl = main.querySelector('.tool-viz-empty');
  assert.ok(emptyEl, '.tool-viz-empty element must be rendered');
  assert.match(emptyEl.textContent, /Nenhuma tool call/i);

  session.dispose();
});

test('4. EventSource connects to /v1/events and cleans up on dispose', () => {
  const Visualizer = loadVisualizerModule();
  const { main, U } = dom();
  const session = Visualizer.render(main, U);

  assert.equal(MockEventSource.instances.length, 1, 'EventSource should be created');
  assert.equal(MockEventSource.instances[0].url, '/v1/events', 'SSE endpoint must be /v1/events');
  assert.equal(MockEventSource.instances[0].closed, false);

  Visualizer.dispose();
  assert.equal(MockEventSource.instances[0].closed, true, 'EventSource must be closed on dispose');
});

test('5. addEvent only processes channel="tool" events', () => {
  const Visualizer = loadVisualizerModule();
  const { main, U } = dom();
  const session = Visualizer.render(main, U);
  const es = MockEventSource.instances[0];

  // Send non-tool channel event (e.g. graph event)
  es.send({
    channel: 'graph',
    type: 'graph.node_updated',
    nodeId: 'n1'
  });

  // Should still show empty message
  let entries = main.querySelectorAll ? main.querySelectorAll('.tool-viz-entry') : find(main, item => item.className?.includes('tool-viz-entry'));
  assert.equal(entries.length, 0, 'Non-tool event should not be added');
  assert.ok(main.querySelector('.tool-viz-empty'), 'Empty message should still be visible');

  // Send tool channel event
  es.send({
    channel: 'tool',
    type: 'tool.start',
    status: 'start',
    tool_name: 'search_knowledge_base',
    timestamp: 1729100000000
  });

  entries = find(main, item => item.className?.includes('tool-viz-entry'));
  assert.equal(entries.length, 1, 'Tool event must be added to timeline');
  assert.match(entries[0].textContent, /search_knowledge_base/);

  session.dispose();
});

test('6. Denied events show red badge with reason', () => {
  const Visualizer = loadVisualizerModule();
  const { main, U } = dom();
  const session = Visualizer.render(main, U);
  const es = MockEventSource.instances[0];

  es.send({
    channel: 'tool',
    type: 'tool.denied',
    status: 'denied',
    tool_name: 'run_bash_command',
    reason: 'Policy violation: command not allowed in sandbox',
    timestamp: 1729100005000
  });

  const entries = find(main, item => item.className?.includes('tool-viz-entry'));
  assert.equal(entries.length, 1);
  const entry = entries[0];

  assert.ok(entry.className.includes('tool-viz-denied'), 'Entry should have tool-viz-denied class');
  assert.match(entry.textContent, /🔴/, 'Denied status should show red badge 🔴');
  assert.match(entry.textContent, /Policy violation: command not allowed in sandbox/, 'Denied event must show reason');

  session.dispose();
});

test('7. End and timeout statuses render with appropriate badges and duration', () => {
  const Visualizer = loadVisualizerModule();
  const { main, U } = dom();
  const session = Visualizer.render(main, U);
  const es = MockEventSource.instances[0];

  es.send({
    channel: 'tool',
    status: 'end',
    tool_name: 'read_sources',
    duration_ms: 142,
    timestamp: 1729100010000
  });

  es.send({
    channel: 'tool',
    status: 'timeout',
    tool_name: 'fetch_remote_url',
    duration_ms: 5000,
    timestamp: 1729100015000
  });

  const entries = find(main, item => item.className?.includes('tool-viz-entry'));
  assert.equal(entries.length, 2);

  // End event
  assert.match(entries[0].textContent, /✅/);
  assert.match(entries[0].textContent, /142ms/);

  // Timeout event
  assert.match(entries[1].textContent, /⏱️/);
  assert.match(entries[1].textContent, /5000ms/);

  session.dispose();
});

test('8. MAX_EVENTS cap (200) works', () => {
  const Visualizer = loadVisualizerModule();
  const { main, U } = dom();
  const session = Visualizer.render(main, U);
  const es = MockEventSource.instances[0];

  // Send 250 events
  for (let i = 1; i <= 250; i++) {
    es.send({
      channel: 'tool',
      status: 'end',
      tool_name: `tool_${i}`,
      duration_ms: i,
      timestamp: 1729100000000 + i * 1000
    });
  }

  const entries = find(main, item => item.className?.includes('tool-viz-entry'));
  assert.equal(entries.length, 200, 'Timeline must cap visible entries to MAX_EVENTS (200)');

  // Oldest visible entry should be tool_51, newest should be tool_250
  assert.match(entries[0].textContent, /tool_51/);
  assert.match(entries[entries.length - 1].textContent, /tool_250/);

  session.dispose();
});

test('9. Malformed JSON SSE data is ignored without throwing', () => {
  const Visualizer = loadVisualizerModule();
  const { main, U } = dom();
  const session = Visualizer.render(main, U);
  const es = MockEventSource.instances[0];

  assert.doesNotThrow(() => {
    es.send('INVALID_JSON{{{');
  });

  const entries = find(main, item => item.className?.includes('tool-viz-entry'));
  assert.equal(entries.length, 0);

  session.dispose();
});

test('10. App navigation and routing integration for tool-calls', () => {
  const appSrc = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
  const indexHtml = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');

  // Verify script tag in index.html
  assert.ok(indexHtml.includes('<script src="tool-visualizer.js" defer></script>'), 'index.html must load tool-visualizer.js');
  const toolVizPos = indexHtml.indexOf('tool-visualizer.js');
  const appPos = indexHtml.indexOf('app.js');
  assert.ok(toolVizPos < appPos, 'tool-visualizer.js must load before app.js');

  // Verify styles in index.html
  assert.ok(indexHtml.includes('.tool-viz-container'), 'index.html must include tool-viz styles');
  assert.ok(indexHtml.includes('.tool-viz-timeline'), 'index.html must include tool-viz-timeline');

  // Verify app.js pages and NAV_GROUPS
  assert.match(appSrc, /['"]tool-calls['"]\s*:\s*\[/, 'pages must define tool-calls');
  assert.match(appSrc, /children\s*:\s*\[[^\]]*['"]tool-calls['"]/, 'NAV_GROUPS must include tool-calls as child of Observabilidade');

  // Verify routing
  assert.match(appSrc, /route\.page\s*===\s*['"]tool-calls['"]/, 'app.js must route to tool-calls');
  assert.match(appSrc, /BrainToolVisualizer\.render/, 'app.js must call BrainToolVisualizer.render');
  assert.match(appSrc, /BrainToolVisualizer\?\.dispose/, 'app.js must dispose BrainToolVisualizer on rerender');
});
