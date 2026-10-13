'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const markdown = require('../markdown.js');

class FakeNode {
    constructor(tag, doc, text = '') { this.tagName = tag; this.ownerDocument = doc; this.children = []; this.attributes = {}; this.listeners = {}; this.text = text; }
    set textContent(text) { this.children = []; this.text = String(text); }
    get textContent() { return this.text + this.children.map(c => c.textContent).join(''); }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    appendChild(node) { if (node.tagName === '#fragment') this.children.push(...node.children); else this.children.push(node); return node; }
    replaceChildren(...nodes) { this.children = []; this.text = ''; for (const node of nodes) this.appendChild(node); }
    set innerHTML(_) { throw new Error('Unsafe HTML assignment'); }
}
function container() {
    const doc = { createElement: tag => new FakeNode(tag, doc), createTextNode: text => new FakeNode('#text', doc, text), createDocumentFragment: () => new FakeNode('#fragment', doc) };
    return new FakeNode('div', doc);
}
function find(node, tag) { return [node, ...node.children.flatMap(child => find(child, tag))].filter(n => n.tagName === tag); }

test('links admit only explicit http(s), without controls or credentials', () => {
    for (const url of ['javascript:alert(1)', 'data:text/html,<script>', 'vbscript:evil', 'file:///C:/secret', '//evil.com', 'https://user:password@evil.com', 'https://evil.com\n/x', '\u0000https://evil.com']) assert.equal(markdown.safeURL(url), null);
    assert.equal(markdown.safeURL('https://example.com/docs?q=1&x=2'), 'https://example.com/docs?q=1&x=2');
    assert.equal(markdown.safeURL('http://localhost:8000/docs'), 'http://localhost:8000/docs');
});
test('injections remain text and do not produce script or image nodes', () => {
    const el = container();
    markdown.render(el, '<script>alert(1)</script> <img src=x onerror=alert(1)>\n\n![screenshot](https://evil.com/tracker.png)\n\n[bad](javascript:alert(1))');
    assert.equal(find(el, 'script').length, 0); assert.equal(find(el, 'img').length, 0); assert.equal(find(el, 'a').length, 0);
    assert.ok(el.textContent.includes('<script>alert(1)</script>')); assert.ok(el.textContent.includes('[Imagem: screenshot]'));
});
test('external links carry noreferrer and noopener, labels remain plain text', () => {
    const el = container(); markdown.render(el, '[<img onerror=evil>](https://example.com)');
    const link = find(el, 'a')[0]; assert.equal(link.attributes.href, 'https://example.com/');
    assert.equal(link.attributes.target, '_blank'); assert.equal(link.attributes.rel, 'noopener noreferrer'); assert.equal(find(el, 'img').length, 0);
});
test('tables have headers, scoped cells, aligned columns and escaped pipes', () => {
    const blocks = markdown.parseBlocks('| Name | Value |\n| :--- | ---: |\n| A\\|B | `x|y` |');
    assert.equal(blocks[0].type, 'table'); assert.deepEqual(blocks[0].align, ['left', 'right']); assert.deepEqual(blocks[0].rows, [['A|B', '`x|y`']]);
    const el = container(); markdown.render(el, '| A | B |\n| --- | --- |\n| x | y |');
    assert.equal(find(el, 'table').length, 1); assert.equal(find(el, 'thead').length, 1); assert.equal(find(el, 'tbody').length, 1);
    assert.equal(find(el, 'th')[0].attributes.scope, 'col'); assert.equal(find(el, 'td').length, 2);
});
test('wiki references preserve document and heading as inert callback values', () => {
    const el = container(), calls = [];
    markdown.render(el, '[[systems/hub-producao#Política de rollback|Ver política]]', { onWikiLink: (...args) => calls.push(args) });
    assert.equal(calls.length, 0); const button = find(el, 'button')[0]; assert.equal(button.textContent, 'Ver política');
    button.listeners.click(); assert.deepEqual(calls, [['systems/hub-producao', 'Política de rollback']]); assert.equal(find(el, 'a').length, 0);
});
test('headings get deterministic unique IDs, without executing content', () => {
    const el = container(); const result = markdown.render(el, '# Política & ações\n## Política & ações\n# <script>evil()</script>');
    assert.deepEqual(result.headings.map(h => h.id), ['politica-acoes', 'politica-acoes-2', 'script-evil-script']); assert.equal(find(el, 'script').length, 0);
    assert.equal(markdown.slug('    '), 'section'); assert.equal(markdown.parseBlocks('# ' + 'x'.repeat(1000))[0].text.length, markdown.limits.heading);
});
test('ordered/unordered lists, fenced code, strong and inline code are semantic', () => {
    const el = container(); markdown.render(el, '- **One**\n- `Two`\n\n3. Three\n4. Four\n\n```html\n<script>evil()</script>\n```');
    assert.equal(find(el, 'ul').length, 1); assert.equal(find(el, 'ol').length, 1); assert.equal(find(el, 'ol')[0].attributes.start, '3');
    assert.equal(find(el, 'li').length, 4); assert.equal(find(el, 'strong').length, 1); assert.equal(find(el, 'pre').length, 1); assert.equal(find(el, 'script').length, 0);
});
test('citation callbacks are optional and document/code lengths are bounded', () => {
    const el = container(), citations = [];
    markdown.render(el, 'Evidence [^source-1]', { onCitation: ref => citations.push(ref) }); find(el, 'button')[0].listeners.click(); assert.deepEqual(citations, ['source-1']);
    const blocks = markdown.parseBlocks('```txt\n' + 'a'.repeat(markdown.limits.code + 1000) + '\n```'); assert.equal(blocks[0].text.length, markdown.limits.code);
    assert.ok(markdown.parseBlocks('x'.repeat(markdown.limits.document + 1000))[0].text.length <= markdown.limits.document);
});
test('leading YAML frontmatter becomes a metadata block instead of a rule and loose text', () => {
    const blocks = markdown.parseBlocks('---\r\ntype: adr\r\nstatus: Aceito\r\ntags: [hub, sap]\r\ndate: \'2026-10-12\'\r\n---\r\n# Title\r\n\r\nBody\r\n\r\n---\r\n');
    assert.deepEqual(blocks[0], { type: 'frontmatter', entries: [['type', 'adr'], ['status', 'Aceito'], ['tags', 'hub, sap'], ['date', '2026-10-12']] });
    assert.deepEqual(blocks.slice(1).map(b => b.type), ['heading', 'paragraph', 'rule']);
    const el = container(); markdown.render(el, '---\ntitle: <b>x</b>\n---\nText');
    const dl = find(el, 'dl')[0]; assert.equal(dl.className, 'markdown-meta');
    assert.equal(find(dl, 'dt')[0].textContent, 'title'); assert.equal(find(dl, 'dd')[0].textContent, '<b>x</b>');
});
test('an unterminated or non-leading --- block stays ordinary markdown', () => {
    assert.deepEqual(markdown.parseBlocks('---\ntype: adr\n').map(b => b.type), ['rule', 'paragraph']);
    assert.equal(markdown.parseBlocks('Intro\n\n---\na: b\n---').some(b => b.type === 'frontmatter'), false);
});
