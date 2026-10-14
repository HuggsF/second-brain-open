'use strict';
// The JEV page embeds the built React app (dashboard/jev/) in a same-origin iframe.
// app.js needs a full browser DOM to run, so these are static source checks (same approach as ux-gates).
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const DIR = path.join(__dirname, '..');
const app = fs.readFileSync(path.join(DIR, 'app.js'), 'utf8');
const html = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(DIR, 'style.css'), 'utf8');
const route = () => {
  const start = app.indexOf("if(route.page==='jev')");
  assert.ok(start >= 0, 'jev route not found');
  const end = app.indexOf("if(route.page==='knowledge'&&route.doc", start);
  return app.slice(start, end);
};
test('jev route renders a same-origin iframe with a class and no inline style', () => {
  const code = route();
  const iframe = code.match(/el\('iframe',\{[^}]*\}/);
  assert.ok(iframe, 'iframe not created');
  assert.match(iframe[0], /src:'jev\/index\.html'/);
  assert.match(iframe[0], /class:'jev-frame'/);
  assert.match(iframe[0], /title:'JEV'/);
  assert.doesNotMatch(iframe[0], /style/);
  assert.doesNotMatch(code, /BrainJEV/);
});
test('jev route opens in a new tab and shows an error card when the frame is not the JEV app', () => {
  const code = route();
  assert.match(code, /window\.open\('\.\/jev\/index\.html','_blank','noopener'\)/);
  assert.match(code, /contentDocument/);
  assert.match(code, /application-name/);
  assert.match(code, /jev-app/);
  assert.doesNotMatch(code, /doc\.title/);
  assert.match(code, /JEV indispon/);
  assert.match(code, /try\{/);
});
test('the old vanilla JEV is gone', () => {
  assert.ok(!html.includes('jev-ui.js'));
  assert.ok(!app.includes('BrainJEV'));
  assert.ok(!fs.existsSync(path.join(DIR, 'jev-ui.js')));
});
test('.jev-frame is a CSS class using theme tokens', () => {
  const rule = css.match(/\.jev-frame\{([^}]*)\}/);
  assert.ok(rule, '.jev-frame missing in style.css');
  assert.match(rule[1], /height:calc\(100vh - 180px\)/);
  assert.match(rule[1], /var\(--panel\)/);
});
