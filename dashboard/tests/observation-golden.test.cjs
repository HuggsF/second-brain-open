'use strict';
// Drift guard: dashboard/hub-topology.js project() is the source of truth for the Python port
// (core/domain/observation/projection.py). The committed golden must match what the JS produces now.
const test = require('node:test'), assert = require('node:assert/strict'), path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = path.join(__dirname, '..', '..');
test('observation golden is in sync with hub-topology.js project()', () => {
  const run = spawnSync(process.execPath, ['scripts/generate_observation_golden.js', '--check'], { cwd: root, encoding: 'utf8' });
  assert.equal(run.status, 0, run.stderr || run.stdout);
});
