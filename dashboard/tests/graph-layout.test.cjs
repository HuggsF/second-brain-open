'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const layout = require('../graph-layout.js');

function fixture() {
  return {
    nodes: [
      {id: 'z', label: 'Última', domain: 'platform', views: {flow: [3, 5]}},
      {id: 'a', label: 'Minúscula', domain: 'hub', views: {flow: [1, 2]}},
      {id: 'A', label: 'Maiúscula', domain: 'hub', views: {flow: [0, 0]}},
      {id: 'ä', label: 'Isolada', domain: 'infra', views: {infra: [4, 8]}}
    ],
    edges: [
      {id: 'parallel', source: 'a', target: 'z', relation: 'observa', evidence: 'parcial'},
      {id: 'forward', source: 'a', target: 'z', relation: 'chama', evidence: 'documentado'},
      {id: 'cycle', source: 'z', target: 'a', relation: 'retorna', source_file: 'systems/test.md'},
      {id: 'self', source: 'A', target: 'A', relation: 'registra'}
    ]
  };
}

function freeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const item of Object.values(value)) freeze(item);
  }
  return value;
}

function assertFinite(scene, positions) {
  assert.ok(positions instanceof Map);
  assert.equal(positions.size, scene.nodes.length, 'every visible node gets a position');
  for (const node of scene.nodes) {
    const point = positions.get(node.id);
    assert.ok(point, node.id + ' has a position');
    assert.ok(Number.isFinite(point.x) && Number.isFinite(point.y), node.id + ' is finite');
  }
}

function assertCardsSeparated(scene, positions) {
  const entities = scene.nodes.filter(node => node.kind === 'entity');
  for (let i = 0; i < entities.length; i++) {
    for (let j = i + 1; j < entities.length; j++) {
      const first = positions.get(entities[i].id), second = positions.get(entities[j].id);
      assert.ok(Math.abs(first.x - second.x) >= 136 || Math.abs(first.y - second.y) >= 44,
        entities[i].id + ' and ' + entities[j].id + ' cards overlap');
    }
  }
}

test('projection adds visual core/categories and preserves each real entity ID', () => {
  const scene = layout.project(fixture(), {domainLabels: {hub: 'Hub', infra: 'Infraestrutura'}});
  assert.deepEqual(scene.nodes.map(node => [node.id, node.kind, node.entityId]), [
    ['@core', 'core', undefined],
    ['@domain:hub', 'category', undefined],
    ['@domain:infra', 'category', undefined],
    ['@domain:platform', 'category', undefined],
    ['A', 'entity', 'A'], ['a', 'entity', 'a'], ['z', 'entity', 'z'], ['ä', 'entity', 'ä']
  ]);
  assert.equal(scene.nodes.find(node => node.id === '@domain:infra').label, 'Infraestrutura');
  assert.equal(scene.nodes.find(node => node.id === '@domain:platform').label, 'platform');
  assert.equal(scene.nodes.find(node => node.id === 'A').domain, 'hub');
  assert.deepEqual(scene.links.map(link => [link.source, link.target, link.kind]), [
    ['@core', '@domain:hub', 'membership'],
    ['@core', '@domain:infra', 'membership'],
    ['@core', '@domain:platform', 'membership'],
    ['@domain:hub', 'A', 'membership'],
    ['@domain:hub', 'a', 'membership'],
    ['@domain:platform', 'z', 'membership'],
    ['@domain:infra', 'ä', 'membership']
  ]);
  assert.equal(new Set(scene.links.map(link => link.id)).size, scene.links.length);
});

test('projection preserves cycles, parallel edge payloads and isolated nodes without mutation', () => {
  const data = freeze(fixture()), before = JSON.stringify(data);
  const scene = layout.project(data);
  assert.notStrictEqual(scene.edges, data.edges);
  assert.deepEqual(scene.edges.map(edge => edge.id), ['cycle', 'forward', 'parallel', 'self']);
  for (const edge of data.edges) assert.strictEqual(scene.edges.find(item => item.id === edge.id), edge);
  assert.ok(scene.nodes.some(node => node.entityId === 'ä'));
  freeze(scene);
  layout.radial(scene);
  layout.layered(scene, {focusDomain: 'hub'});
  assert.equal(JSON.stringify(data), before);
});

test('projection and both layouts are deterministic under binary ID order and input permutations', () => {
  const original = fixture();
  const shuffled = {nodes: [...original.nodes].reverse(), edges: [...original.edges].reverse()};
  const first = layout.project(original), second = layout.project(shuffled);
  assert.deepEqual(second, first);
  assert.deepEqual([...layout.radial(second)], [...layout.radial(first)]);
  assert.deepEqual([...layout.layered(second)], [...layout.layered(first)]);
  const permutedScene = {...second, nodes: [...second.nodes].reverse(), links: [...second.links].reverse()};
  assert.deepEqual([...layout.radial(permutedScene)], [...layout.radial(first)]);
  assert.deepEqual([...layout.layered(permutedScene)], [...layout.layered(first)]);
});

test('empty projections and explicitly empty scenes stay finite', () => {
  const scene = layout.project({nodes: [], edges: []});
  assert.deepEqual(scene.nodes.map(node => node.id), ['@core']);
  assert.deepEqual(scene.links, []);
  for (const method of [layout.radial, layout.layered]) {
    assertFinite(scene, method(scene));
    assert.deepEqual([...method({nodes: [], edges: [], links: []})], []);
  }
});

test('radial layout centers the core, places categories on one circle, and groups entity rings', () => {
  const scene = layout.project(fixture()), positions = layout.radial(scene);
  assertFinite(scene, positions);
  assert.deepEqual(positions.get('@core'), {x: 0, y: 0});
  const categories = scene.nodes.filter(node => node.kind === 'category');
  const radii = categories.map(node => Math.hypot(positions.get(node.id).x, positions.get(node.id).y));
  assert.ok(radii[0] > 0);
  assert.ok(radii.every(radius => Math.abs(radius - radii[0]) < 1e-7));
  const category = positions.get('@domain:hub');
  const distances = ['A', 'a'].map(id => {
    const point = positions.get(id);
    return Math.hypot(point.x - category.x, point.y - category.y);
  });
  assert.ok(distances[0] > 100);
  assert.ok(Math.abs(distances[0] - distances[1]) < 1e-7);
  assertCardsSeparated(scene, positions);
});

test('radial rings expand for dense domains and prevent compact card overlaps', () => {
  const small = layout.project({nodes: [{id: 'single', label: 'Single', domain: 'one'}], edges: []});
  const data = {nodes: [], edges: []};
  for (let domain = 0; domain < 9; domain++) {
    for (let index = 0; index < (domain === 0 ? 84 : 3); index++) {
      data.nodes.push({id: domain + ':' + index, label: 'Entity ' + index, domain: 'd' + domain});
    }
  }
  const scene = layout.project(data), positions = layout.radial(scene), smallPositions = layout.radial(small);
  assertFinite(scene, positions);
  assertCardsSeparated(scene, positions);
  const smallCategory = smallPositions.get('@domain:one');
  const bigCategory = positions.get('@domain:d0');
  const smallRadius = Math.hypot(smallCategory.x, smallCategory.y);
  assert.ok(Math.hypot(bigCategory.x, bigCategory.y) > smallRadius);
  const localRadii = scene.nodes.filter(node => node.kind === 'entity' && node.domain === 'd0').map(node => {
    const point = positions.get(node.id);
    return Math.round(Math.hypot(point.x - bigCategory.x, point.y - bigCategory.y));
  });
  assert.ok(new Set(localRadii).size > 1, 'dense groups use multiple local rings');
});

test('layered layout uses presentation depths despite knowledge cycles and keeps focused domain first', () => {
  const scene = layout.project(fixture());
  const positions = layout.layered(scene, {focusDomain: 'platform', orientation: 'horizontal'});
  assertFinite(scene, positions);
  const core = positions.get('@core');
  const categories = scene.nodes.filter(node => node.kind === 'category');
  const categoryX = positions.get(categories[0].id).x;
  assert.ok(categoryX > core.x);
  for (const node of categories) assert.equal(positions.get(node.id).x, categoryX);
  const focusedY = positions.get('@domain:platform').y;
  assert.ok(categories.filter(node => node.domain !== 'platform').every(node => positions.get(node.id).y > focusedY));
  for (const node of scene.nodes.filter(node => node.kind === 'entity')) {
    assert.ok(positions.get(node.id).x > categoryX);
  }
  const defaultPositions = layout.layered(scene);
  assert.ok(defaultPositions.get('@domain:hub').y < defaultPositions.get('@domain:infra').y);
  assert.deepEqual([...layout.layered(scene, {focusDomain: 'missing'})], [...defaultPositions]);
});

test('vertical orientation is the exact transpose of horizontal coordinates', () => {
  const scene = layout.project(fixture());
  const horizontal = layout.layered(scene, {focusDomain: 'infra', orientation: 'horizontal'});
  const vertical = layout.layered(scene, {focusDomain: 'infra', orientation: 'vertical'});
  for (const [id, point] of horizontal) assert.deepEqual(vertical.get(id), {x: point.y, y: point.x});
  assertCardsSeparated(scene, vertical);
});

test('layered dense domains pack rows and columns with room for compact cards', () => {
  const nodes = Array.from({length: 84}, (_, index) => ({id: 'n' + index, label: 'Node ' + index, domain: 'dense'}));
  const scene = layout.project({nodes, edges: []}), positions = layout.layered(scene);
  const points = nodes.map(node => positions.get(node.id));
  assertFinite(scene, positions);
  assertCardsSeparated(scene, positions);
  assertCardsSeparated(scene, layout.layered(scene, {orientation: 'vertical'}));
  const columns = [...new Set(points.map(point => point.x))].sort((a, b) => a - b);
  const rows = [...new Set(points.map(point => point.y))].sort((a, b) => a - b);
  assert.ok(columns.length > 1, 'an 84 entity domain must not become one long list');
  assert.ok(rows.length < 20, 'dense domains remain a compact grid');
  for (let i = 1; i < columns.length; i++) assert.ok(columns[i] - columns[i - 1] >= 176);
  for (let i = 1; i < rows.length; i++) assert.ok(rows[i] - rows[i - 1] >= 72);
});

test('actual catalog and each existing view produce finite, separated layouts', () => {
  const catalog = JSON.parse(fs.readFileSync(path.join(__dirname, '../graph-catalog.json'), 'utf8'));
  for (const view of [null, ...catalog.views.map(item => item.id)]) {
    const nodes = view ? catalog.nodes.filter(node => node.views[view]) : catalog.nodes;
    const ids = new Set(nodes.map(node => node.id));
    const edges = catalog.edges.filter(edge => (!view || edge.view === view) && ids.has(edge.source) && ids.has(edge.target));
    const scene = freeze(layout.project({nodes, edges}));
    const radial = layout.radial(scene), layered = layout.layered(scene);
    assertFinite(scene, radial);
    assertFinite(scene, layered);
    assertFinite(scene, layout.layered(scene, {orientation: 'vertical', focusDomain: 'platform'}));
    assertCardsSeparated(scene, radial);
    assertCardsSeparated(scene, layered);
  }
});

test('UMD browser export exposes the same pure projection and layouts without CommonJS', () => {
  const context = {window: {}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../graph-layout.js'), 'utf8'), context);
  const browser = context.window.BrainGraphLayout;
  const scene = browser.project(fixture());
  assert.equal(scene.nodes.length, 8);
  assert.equal(browser.radial(scene).size, 8);
  assert.equal(browser.layered(scene).size, 8);
});
