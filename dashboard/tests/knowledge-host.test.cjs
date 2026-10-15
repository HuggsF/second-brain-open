'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {dom, find} = require('./topology-dom.cjs');
const DIR = path.join(__dirname, '..');
const graph = JSON.parse(fs.readFileSync(path.join(DIR, 'graph-data.js'), 'utf8')
  .slice('window.KIOSK_GRAPH = '.length).trim().replace(/;$/, ''));

// Execute the whole dashboard host and product together: separate module tests cannot
// detect the two document key handlers competing or a hash render retaining a listener.
function setup(initialHash = '#page=graph') {
  const {document, main} = dom();
  const proto = Object.getPrototypeOf(main);
  proto.showModal = function () { this.open = true; };
  proto.close = function () { this.open = false; this.dispatch('close'); };
  const ids = {main};
  for (const id of ['theme', 'page-name', 'navigation', 'snapshot-label', 'search-open',
    'search-dialog', 'search-close', 'global-query', 'global-results', 'help-open',
    'help-dialog', 'help-close', 'notice']) {
    ids[id] = document.createElement(id.includes('dialog') ? 'dialog' : 'div');
    ids[id].value = '';
    ids[id].setAttribute('id', id);
    document.body.append(ids[id]);
  }
  const skip = document.createElement('a');
  skip.className = 'skip';
  document.body.append(skip);
  const bodyClasses = new Set();
  document.body.classList = {
    toggle(name, enabled) { if (enabled) bodyClasses.add(name); else bodyClasses.delete(name); }
  };
  ids.notice.classList = {add() {}, remove() {}};
  document.documentElement = {dataset: {}};
  document.createElementNS = (_, tag) => document.createElement(tag);
  document.getElementById = id => ids[id];
  document.querySelector = selector => selector === '.skip' ? skip
    : selector === 'dialog[open]' ? find(document.body, node => node.tagName === 'dialog' && node.open)[0] || null : null;
  const keyHandlers = [], hashHandlers = [];
  document.addEventListener = (type, handler) => { if (type === 'keydown') keyHandlers.push(handler); };
  document.removeEventListener = (type, handler) => {
    if (type === 'keydown') { const index = keyHandlers.indexOf(handler); if (index >= 0) keyHandlers.splice(index, 1); }
  };
  let hash = initialHash, product, disposed = 0, technicalRenders = 0;
  const location = {get hash() { return hash; }, set hash(value) { hash = value; }};
  const window = {
    KIOSK_GRAPH: graph,
    BrainCore: require('../core.js'),
    BrainSchema: require('../schema.js'),
    BrainKnowledgeModel: require('../knowledge-model.js'),
    BrainMarkdown: {render(container, text) { container.textContent = text; }},
    BrainKnowledgeMotion: {mount() { return {update() {}, zoom() {}, fit() {}, dispose() { disposed++; }}; }},
    BrainGraphUI: {dispose() {}, render(host) { technicalRenders++; host.append(document.createTextNode('Technical view')); }},
    addEventListener(type, handler) { if (type === 'hashchange') hashHandlers.push(handler); },
    scrollTo() {}
  };
  const context = vm.createContext({window, document, Node: main.constructor,
    localStorage: {getItem() { return null; }, setItem() {}},
    matchMedia: () => ({matches: false}), location,
    history: {replaceState(_state, _title, value) { hash = value; }},
    navigator: {}, URLSearchParams, Intl, Date, Map, Set, JSON, setTimeout, clearTimeout});
  vm.runInContext(fs.readFileSync(path.join(DIR, 'knowledge-view.js'), 'utf8'), context);
  const original = window.BrainKnowledgeView;
  window.BrainKnowledgeView = {mount(host, options) { product = original.mount(host, options); return product; }};
  vm.runInContext(fs.readFileSync(path.join(DIR, 'app.js'), 'utf8'), context);
  function key(key, modifiers = {}) {
    const event = {key, ctrlKey: false, metaKey: false, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; }, ...modifiers};
    for (const handler of [...keyHandlers]) handler(event);
    // Native dialog cancellation happens after event listeners unless prevented.
    if (key === 'Escape' && !event.defaultPrevented) document.querySelector('dialog[open]')?.close();
    return event;
  }
  return {document, main, ids, key, get product() { return product; },
    get disposed() { return disposed; }, get technicalRenders() { return technicalRenders; },
    get keyHandlerCount() { return keyHandlers.length; },
    get productMode() { return bodyClasses.has('knowledge-product-mode'); },
    flushHash() { for (const handler of hashHandlers) handler(); }};
}
function button(root, label) {
  const found = find(root, node => node.tagName === 'button' && node.textContent.includes(label))[0];
  assert.ok(found, 'button ' + label);
  return found;
}

test('dashboard Ctrl+K focuses the product search without opening the host search dialog', () => {
  const h = setup('#page=graph&experience=product');
  const event = h.key('k', {ctrlKey: true});
  assert.ok(event.defaultPrevented);
  assert.equal(h.ids['search-dialog'].open, false);
  assert.equal(h.document.activeElement.getAttribute('aria-label'), 'Buscar no conhecimento');
});

test('Escape closes a product source dialog and preserves the selected entity in the host', () => {
  const h = setup('#page=graph&experience=product');
  button(h.main, 'Agentes de IA').click();
  button(h.main, 'Cartões').click();
  button(h.main, 'Explorar item').click();
  const nodeId = h.product.getState().nodeId;
  assert.ok(nodeId);
  button(h.main, 'Ler fonte do item').click();
  const dialog = find(h.main, 'dialog')[0];
  assert.ok(dialog.open);
  h.key('Escape');
  assert.equal(dialog.open, false);
  assert.equal(h.product.getState().nodeId, nodeId);
});

test('technical navigation disposes the product handler and the return action mounts one fresh product', () => {
  const h = setup('#page=graph&experience=product');
  assert.equal(h.productMode, true);
  assert.equal(h.keyHandlerCount, 2);
  button(h.main, 'Sobre o protótipo').click();
  button(h.main, 'Abrir explorador técnico').click();
  h.flushHash();
  assert.equal(h.disposed, 1);
  assert.equal(h.keyHandlerCount, 1);
  assert.equal(h.productMode, false);
  assert.equal(h.technicalRenders, 1);
  button(h.main, 'Explorar como produto').click();
  h.flushHash();
  assert.equal(h.keyHandlerCount, 2);
  assert.equal(h.productMode, true);
  h.key('k', {ctrlKey: true});
  assert.equal(h.ids['search-dialog'].open, false);
});

test('product deep links restore entities outside the default technical view', () => {
  const h = setup('#page=graph&experience=product&node=eva');
  assert.equal(h.product.getState().nodeId, 'eva');
  assert.ok(button(h.main, 'Ler fonte do item'));
});
