import assert from 'node:assert/strict';
import test from 'node:test';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
let App = () => null;
try {
  if (existsSync(resolve('src/App.jsx'))) App = (await server.ssrLoadModule('/src/App.jsx')).default;
} finally {
  await server.close();
}
const markup = () => renderToStaticMarkup(React.createElement(App));

test('the initial office contains all five rooms and named agent controls', () => {
  const html = markup();
  for (const label of ['Pesquisa', 'Desenvolvimento', 'Redação', 'Reunião', 'Orquestrador', 'Maia', 'Noah', 'Theo', 'Lia', 'Eva']) {
    assert.ok(html.includes(label), 'Missing office element: ' + label);
  }
  for (const name of ['Maia', 'Noah', 'Theo', 'Lia', 'Eva']) {
    assert.ok(html.includes('Ver detalhes de ' + name), 'Agent should be keyboard selectable: ' + name);
  }
});

test('simulation is explicitly local and starts only through an action', () => {
  const html = markup();
  assert.ok(html.includes('Iniciar simulação'), 'Start action should exist');
  assert.ok(html.includes('Nova tarefa'), 'Task submission should be discoverable');
  assert.match(html, /simula[çc][ãa]o local/i);
  assert.match(html, /Ocioso/);
});

test('activity panel and progress have accessible text on the first render', () => {
  const html = markup();
  assert.ok(html.includes('Atividade'), 'Logs should be visible before starting');
  assert.ok(html.includes('progressbar'), 'Progress should have a semantic accessible representation');
  assert.ok(html.includes('role="log"'), 'Activity events should be exposed as a live log');
});
