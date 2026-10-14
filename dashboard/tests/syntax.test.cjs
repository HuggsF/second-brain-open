const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const DIR = path.join(__dirname, '..');

test('syntax: every dashboard script compiles (a broken app.js blanks the whole page)', () => {
  const broken = [];
  for (const file of fs.readdirSync(DIR).filter(f => f.endsWith('.js'))) {
    const source = fs.readFileSync(path.join(DIR, file), 'utf8').replace(/^﻿/, '');
    try {
      new vm.Script(source, { filename: file }); // parse only, never runs
    } catch (error) {
      broken.push(`${file}: ${error.message}`);
    }
  }
  assert.deepEqual(broken, []);
});
