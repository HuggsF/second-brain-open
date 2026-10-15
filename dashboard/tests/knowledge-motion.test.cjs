'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {dom, find, walk} = require('./topology-dom.cjs');
const modulePath = require.resolve('../graph-layout.js').replace('graph-layout.js', 'knowledge-motion.js');
function engine() {
  assert.ok(fs.existsSync(modulePath), 'the product motion engine exists');
  return require(modulePath);
}
const node = (id, kind = 'entity', label = id) => ({id, kind, label, subtitle: 'Conhecimento documentado', token: 'blue'});
function overview() {
  const nodes = [node('@core', 'core', 'Segundo Cérebro'), ...['Sistemas e integrações', 'Regras de negócio', 'Evidências e decisões', 'Arquitetura e operação', 'Demandas e entregas'].map((label, i) => node('category:' + i, 'category', label))];
  return {mode: 'overview', nodes, links: nodes.slice(1).map(item => ({id: 'member:' + item.id, source: '@core', target: item.id, kind: 'membership'})), edges: []};
}
function focused() {
  const selected = node('focus', 'entity', 'Um sistema com nome completo e suficientemente longo');
  const incoming = node('in'), outgoing = node('out'), isolated = node('isolated');
  return {mode: 'entity', selectedId: 'focus', nodes: [outgoing, isolated, selected, incoming], links: [], edges: [
    {id: 'incoming', source: 'in', target: 'focus', relation: 'documenta', evidence: {source: 'vault/in.md'}},
    {id: 'outgoing', source: 'focus', target: 'out', relation: 'consulta', evidence: {source: 'vault/out.md'}},
    {id: 'parallel', source: 'focus', target: 'out', relation: 'observa'},
    {id: 'cycle', source: 'out', target: 'focus', relation: 'responde'},
    {id: 'self', source: 'focus', target: 'focus', relation: 'registra'}
  ]};
}
function environment({reduced = false} = {}) {
  const {document, main} = dom();
  const Element = document.body.constructor;
  Element.prototype.removeAttribute ??= function (key) { delete this.attributes[key]; };
  Element.prototype.removeEventListener ??= function (type, handler) { this.listeners[type] = (this.listeners[type] || []).filter(item => item !== handler); };
  Element.prototype.getBoundingClientRect ??= function () { return {left: 0, top: 0, width: 960, height: 620}; };
  Element.prototype.setPointerCapture ??= function () {};
  Element.prototype.releasePointerCapture ??= function () {};
  document.createElementNS = (_, tag) => document.createElement(tag);
  let time = 0, nextFrame = 0, observed = 0, disconnected = 0;
  const frames = new Map();
  document.defaultView = {
    performance: {now: () => time},
    matchMedia: () => ({matches: reduced}),
    requestAnimationFrame: callback => { frames.set(++nextFrame, callback); return nextFrame; },
    cancelAnimationFrame: id => frames.delete(id),
    ResizeObserver: class { constructor(callback) { this.callback = callback; } observe() { observed++; } disconnect() { disconnected++; } }
  };
  const svg = document.createElementNS('', 'svg');
  main.append(svg);
  return {document, svg, frames, step(milliseconds) { time += milliseconds; const pending = [...frames.values()]; frames.clear(); for (const callback of pending) callback(time); }, resources: () => ({observed, disconnected})};
}
function byNode(svg, id) { return find(svg, item => item.getAttribute('data-kp-node') === id)[0]; }
function byEdge(svg, id) { return find(svg, item => item.getAttribute('data-kp-edge') === id)[0]; }
function transform(svg, id) { return byNode(svg, id).getAttribute('transform'); }

test('overview gives six readable cards with deterministic, separated positions and a centered core', () => {
  const Motion = engine(), scene = overview(), points = Motion.layout(scene);
  assert.ok(points instanceof Map);
  assert.equal(points.size, 6);
  assert.deepEqual(points.get('@core'), {x: 480, y: 310});
  const categories = scene.nodes.slice(1);
  for (let i = 0; i < categories.length; i++) {
    const point = points.get(categories[i].id);
    assert.ok(point.x >= 100 && point.x <= 860 && point.y >= 40 && point.y <= 580);
    for (let j = i + 1; j < categories.length; j++) {
      const other = points.get(categories[j].id);
      assert.ok(Math.abs(point.x - other.x) >= 196 || Math.abs(point.y - other.y) >= 76);
    }
  }
  assert.deepEqual([...Motion.layout({...scene, nodes: [...scene.nodes].reverse()})], [...points]);
  assert.deepEqual([...Motion.layout({nodes: [], edges: [], links: []})], []);
});

test('group focus reserves a left category and a non-overlapping three by four entity grid', () => {
  const Motion = engine();
  const category = node('category', 'category');
  const scene = {mode: 'group', nodes: [category, ...Array.from({length: 12}, (_, i) => ({...node('entity:' + String(i).padStart(2, '0')), groupId: 'category'}))], links: [], edges: []};
  const points = Motion.layout(scene);
  assert.equal(points.get('category').x, 150);
  assert.equal(new Set(scene.nodes.slice(1).map(item => points.get(item.id).x)).size, 3);
  assert.equal(new Set(scene.nodes.slice(1).map(item => points.get(item.id).y)).size, 4);
  const positions = scene.nodes.map(item => points.get(item.id));
  for (let i = 0; i < positions.length; i++) for (let j = i + 1; j < positions.length; j++) {
    assert.ok(Math.abs(positions[i].x - positions[j].x) >= 196 || Math.abs(positions[i].y - positions[j].y) >= 76);
  }
});

test('entity focus places directed neighbors on their respective sides and survives isolated nodes and cycles', () => {
  const Motion = engine(), scene = focused(), points = Motion.layout(scene);
  assert.equal(points.get('focus').x, 540);
  assert.ok(points.get('in').x < 540);
  assert.ok(points.get('out').x > 540, 'a reciprocal neighbor keeps the outgoing column');
  for (const point of points.values()) assert.ok(Number.isFinite(point.x) && Number.isFinite(point.y));
  const single = Motion.layout({mode: 'entity', selectedId: 'one', nodes: [node('one')], links: [], edges: []});
  assert.deepEqual(single.get('one'), {x: 540, y: 340});
});

test('one-sided entity neighborhoods keep all twelve cards separate without reversing relationship direction', () => {
  const Motion = engine(), nodes = [node('focus'), ...Array.from({length: 11}, (_, index) => node('neighbor:' + index))];
  const edges = nodes.slice(1).map(item => ({id: 'edge:' + item.id, source: 'focus', target: item.id, relation: 'consulta'}));
  const positions = Motion.layout({mode: 'entity', selectedId: 'focus', nodes, edges, links: []});
  for (const item of nodes.slice(1)) assert.ok(positions.get(item.id).x > 540);
  const points = [...positions.values()];
  for (let i = 0; i < points.length; i++) for (let j = i + 1; j < points.length; j++) {
    assert.ok(Math.abs(points[i].x - points[j].x) >= 180 || Math.abs(points[i].y - points[j].y) >= 66, 'neighbor cards must not overlap');
  }
});

test('SVG nodes retain full titles, accessible keyboard activation, and persistent DOM focus on updates', () => {
  const Motion = engine(), env = environment(), selected = [], scene = focused();
  const view = Motion.mount(env.svg, {onNode: item => selected.push(item)});
  view.update(scene, {animate: false});
  const card = byNode(env.svg, 'focus');
  assert.equal(card.getAttribute('role'), 'button');
  assert.equal(card.getAttribute('tabindex'), '0');
  assert.ok(card.getAttribute('aria-label').includes(scene.nodes.find(item => item.id === 'focus').label));
  assert.equal(find(card, 'title')[0].textContent.includes('suficientemente longo'), true);
  assert.ok(find(card, 'tspan').length <= 2);
  for (const text of find(env.svg, 'text')) assert.ok(Number(text.getAttribute('font-size')) >= 11);
  card.focus(); card.press('Enter'); card.press(' ');
  assert.strictEqual(selected[0], scene.nodes.find(item => item.id === 'focus'));
  assert.equal(selected.length, 2);
  view.update({...scene, nodes: scene.nodes.map(item => ({...item, subtitle: 'Atualizado'}))}, {animate: false});
  assert.strictEqual(byNode(env.svg, 'focus'), card);
  assert.strictEqual(env.document.activeElement, card);
  view.select('in');
  assert.ok(byNode(env.svg, 'in').className.includes('kp-selected'));
  assert.ok(!card.className.includes('kp-selected'));
  view.dispose();
});

test('only real relationships receive arrows, preserve full payloads, and distinguish loops and parallel edges', () => {
  const Motion = engine(), env = environment(), chosen = [], scene = focused();
  scene.links.push({id: 'membership', source: 'focus', target: 'isolated', kind: 'membership'});
  const view = Motion.mount(env.svg, {onEdge: edge => chosen.push(edge)});
  view.update(scene, {animate: false});
  assert.equal(find(env.svg, item => item.getAttribute('data-kp-edge') !== null).length, 5);
  const real = byEdge(env.svg, 'incoming'), path = find(real, 'path')[0];
  assert.match(path.getAttribute('marker-end'), /^url\(#kp-arrow-/);
  real.press('Enter');
  assert.strictEqual(chosen[0], scene.edges[0]);
  const membership = find(env.svg, item => item.className.split(' ').includes('kp-membership'))[0];
  assert.equal(membership.getAttribute('marker-end'), null);
  assert.ok(membership.getAttribute('stroke-dasharray'));
  const outgoing = find(byEdge(env.svg, 'outgoing'), 'path')[0].getAttribute('d');
  const parallel = find(byEdge(env.svg, 'parallel'), 'path')[0].getAttribute('d');
  assert.notEqual(outgoing, parallel);
  assert.match(find(byEdge(env.svg, 'self'), 'path')[0].getAttribute('d'), /C/);
  assert.ok(!walk(env.svg).some(item => /NaN|Infinity/.test(item.getAttribute('d') || '')));
  view.dispose();
});

test('parallel self relationships have distinct visible loops', () => {
  const Motion = engine(), env = environment(), scene = focused();
  scene.edges.push({id: 'self:second', source: 'focus', target: 'focus', relation: 'confere'});
  const view = Motion.mount(env.svg);
  view.update(scene, {animate: false});
  assert.notEqual(find(byEdge(env.svg, 'self'), 'path')[0].getAttribute('d'), find(byEdge(env.svg, 'self:second'), 'path')[0].getAttribute('d'));
  view.dispose();
});

test('transitions are finite, restart from the displayed frame, and keep edges attached to that frame', () => {
  const Motion = engine(), env = environment(), scene = focused();
  const view = Motion.mount(env.svg);
  view.update(scene, {animate: false});
  const original = transform(env.svg, 'in');
  view.update({...scene, selectedId: 'in'}, {selectedId: 'in'});
  assert.equal(env.frames.size, 1);
  env.step(325);
  const displayed = transform(env.svg, 'in');
  assert.notEqual(displayed, original);
  const beforeEdge = find(byEdge(env.svg, 'incoming'), 'path')[0].getAttribute('d');
  view.update(scene, {selectedId: 'focus'});
  assert.equal(transform(env.svg, 'in'), displayed, 'an interruption does not jump to an old endpoint');
  assert.equal(find(byEdge(env.svg, 'incoming'), 'path')[0].getAttribute('d'), beforeEdge);
  assert.equal(env.frames.size, 1, 'the old animation is canceled');
  env.step(650);
  assert.equal(transform(env.svg, 'in'), original);
  assert.equal(env.frames.size, 0, 'the animation does not run continuously');
  view.dispose();
});

test('reduced-motion and explicit motion opt-out update immediately without frame scheduling', () => {
  const Motion = engine();
  for (const reduced of [false, true]) {
    const env = environment({reduced}), view = Motion.mount(env.svg), scene = focused();
    view.update(scene, {animate: false});
    view.update({...scene, selectedId: 'in'}, reduced ? {} : {motion: false});
    assert.equal(env.frames.size, 0);
    assert.match(transform(env.svg, 'in'), /540/);
    view.dispose();
  }
});

test('zoom and pan update the SVG viewBox, fit restores it, and dispose releases all resources and handlers', () => {
  const Motion = engine(), env = environment(), changes = [], selected = [];
  const view = Motion.mount(env.svg, {onView: value => changes.push(value), onNode: value => selected.push(value)});
  view.update(overview(), {animate: false});
  const initial = env.svg.getAttribute('viewBox');
  view.zoom(1.5);
  assert.notEqual(env.svg.getAttribute('viewBox'), initial);
  view.fit();
  assert.equal(env.svg.getAttribute('viewBox'), initial);
  env.svg.dispatch('pointerdown', {target: env.svg, clientX: 200, clientY: 200, pointerId: 1, button: 0});
  env.svg.dispatch('pointermove', {clientX: 250, clientY: 225, pointerId: 1});
  env.svg.dispatch('pointerup', {pointerId: 1});
  assert.notEqual(env.svg.getAttribute('viewBox'), initial);
  assert.ok(changes.length >= 3);
  assert.equal(env.resources().observed, 1);
  const card = byNode(env.svg, '@core');
  view.update(focused());
  assert.ok(env.frames.size > 0);
  view.dispose();
  assert.equal(env.frames.size, 0);
  assert.equal(env.resources().disconnected, 1);
  assert.equal(walk(env.svg).reduce((count, item) => count + Object.values(item.listeners).flat().length, 0), 0);
  card.click();
  assert.equal(selected.length, 0);
});
