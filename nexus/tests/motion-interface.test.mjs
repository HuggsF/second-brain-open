import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { createSimulation } from '../src/simulation.mjs';

const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
let App, OfficeFloor, activity;
try {
  App = (await server.ssrLoadModule('/src/App.jsx')).default;
  if (existsSync('src/components/ActivityPanel.jsx')) activity = await server.ssrLoadModule('/src/components/ActivityPanel.jsx');
  if (existsSync('src/components/OfficeFloor.jsx')) OfficeFloor = (await server.ssrLoadModule('/src/components/OfficeFloor.jsx')).default;
} finally { await server.close(); }

test('App SSR expõe preferência manual sem prometer sobrepor o SO', () => {
  const html = renderToStaticMarkup(React.createElement(App));
  assert.match(html, /motion-toggle[^>]*aria-pressed="false"/);
  assert.match(html, /Menos movimento/);
});

test('log preserva o texto visível quando um evento é inserido no topo', () => {
  assert.equal(typeof activity.captureLogAnchor, 'function', 'Âncora de leitura ainda ausente');
  // Geometry fixture at the browser boundary: old row remains visible at y=12.
  let rowTop = 12;
  const row = { dataset: { logId: 'old-log' }, getBoundingClientRect: () => ({top: rowTop, bottom: rowTop + 40}) };
  const stream = { children: [row], scrollTop: 180, getBoundingClientRect: () => ({top: 0}) };
  const anchor = activity.captureLogAnchor(stream);
  rowTop = 82;
  activity.restoreLogAnchor(stream, anchor);
  assert.equal(stream.scrollTop, 250);
});
test('OfficeFloor renderiza packet em overlay direto e strings inertes', () => {
  assert.equal(typeof OfficeFloor, 'function', 'OfficeFloor ainda ausente');
  const html = renderToStaticMarkup(React.createElement(OfficeFloor, {simulation: createSimulation(), missionId: 1, paused: false, reducedMotion: false,
    bubbles: {manager: {text: '<script>alert(1)</script>', key: 'message', type: 'message'}},
    transfers: [{id: 'a', from: 'researcher', to: 'coder', delay: 0, type: 'context_share'}], onSelect() {}, selectedId: null, celebrating: true}));
  assert.match(html, /&lt;script&gt;/); assert.doesNotMatch(html, /<script>/);
  assert.match(html, /class="transfer-overlay"/);
  assert.match(html, /floor-entry[^]*?NEXUS STUDIO<\/div><div class="transfer-overlay"[^]*?transfer-packet/);
});
test('OfficeFloor em movimento reduzido omite transfers e celebração', () => {
  assert.equal(typeof OfficeFloor, 'function', 'OfficeFloor ainda ausente');
  const html = renderToStaticMarkup(React.createElement(OfficeFloor, {simulation: createSimulation(), missionId: 1, paused: false, reducedMotion: true,
    bubbles: {}, transfers: [{id: 'a', from: 'researcher', to: 'coder', delay: 0, type: 'context_share'}], onSelect() {}, selectedId: null, celebrating: true}));
  assert.doesNotMatch(html, /transfer-packet/); assert.doesNotMatch(html, /confetti-piece/);
});
