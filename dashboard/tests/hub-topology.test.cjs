const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {project, dependencies} = require('../hub-topology.js');

const NOW = 1791540000;
const SHA = 'a'.repeat(40);
const iso = seconds => new Date(seconds * 1000).toISOString();
function sample(environment = 'production') {
  const enabled = environment === 'production';
  const health = {status: 'ok', environment, revision: SHA, emissionEnabled: enabled, workerEnabled: enabled, version: '1.0.0'};
  return {
    at: iso(NOW - 5), ok: true, failure_count: 0, failure_reasons: [], warning_count: 0,
    process: {status: 'online', restarts: 2, uptime: 1000, memoryBytes: 100000},
    internal: {...health}, external: {...health},
    database: {ok: true, pending: 3, processing: 0, failed: 2, errorsSinceDeploy: 0,
      automaticShops: 0, rateLimitsSinceDeploy: 0, terminalErrorsSinceDeploy: 0,
      logisticsReviewJobs: 0, multipleVolumeReviewJobs: 0}
  };
}
function envelope(environment = 'production') {
  return {schema_version: 1, space_id: 'kiosk', environment, age_seconds: 5, stale: false, collection_failed: false,
    last_attempt: {id: 7, collected_at: NOW - 5, error: null},
    observation: {id: 7, collected_at: NOW - 5,
      report: {environment, expected_sha: SHA, ok: true, source: 'hub/post-deploy-check', schema_version: 1,
        window_seconds: 300, snapshots: [sample(environment), sample(environment)]}}};
}
const node = (model, id) => model.nodes.find(item => item.id === id);
const states = model => Object.fromEntries(model.nodes.map(item => [item.id, item.status]));
const allGreen = {process: 'green', internal: 'green', external: 'green', database: 'green'};
const allUnknown = {process: 'unknown', internal: 'unknown', external: 'unknown', database: 'unknown'};
const allYellow = {process: 'yellow', internal: 'yellow', external: 'yellow', database: 'yellow'};
const samples = latest => latest.observation.report.snapshots;

// A missing observation must not erase the architecture or manufacture health.
test('missing observations retain topology with unknown health and directed dependencies', () => {
  const model = project('production', null, NOW);
  assert.deepEqual(states(model), allUnknown);
  assert.equal(model.observation, null);
  assert.deepEqual(model.collection, {status: 'missing', lastAttemptAt: null});
  assert.equal(model.summary.status, 'unknown');
  assert.deepEqual(dependencies(model, 'process').dependsOn.map(item => item.id), ['database']);
  assert.deepEqual(dependencies(model, 'process').dependents.map(item => item.id), ['internal', 'external']);
  assert.deepEqual(dependencies(model, 'internal').dependsOn.map(item => item.id), ['process']);
  assert.deepEqual(dependencies(model, 'database').dependents.map(item => item.id), ['process']);
  assert.deepEqual(dependencies(model, 'missing'), {dependsOn: [], dependents: []});
  assert.ok(model.edges.every(edge => typeof edge.relation === 'string' && /hub-logistico\/.+\.js:\d+/.test(edge.sourceRef)));
});

// Removing the environment policy or using only the latest sample breaks these cases.
for (const environment of ['production', 'hml']) {
  test(`${environment} requires two normal samples and preserves metadata without mutating input`, () => {
    const latest = envelope(environment), before = structuredClone(latest);
    const model = project(environment, latest, NOW);
    assert.deepEqual(states(model), allGreen);
    assert.equal(model.summary.status, 'green');
    assert.deepEqual(model.observation, {id: 7, collectedAt: NOW - 5, source: 'hub/post-deploy-check'});
    assert.deepEqual(model.collection, {status: 'ok', lastAttemptAt: NOW - 5});
    for (const aspect of model.nodes) {
      assert.equal(aspect.observedAt, NOW - 5);
      assert.equal(aspect.ageSeconds, 5);
      assert.ok(aspect.checks.length > 0);
      assert.ok(aspect.checks.every(check => check.ok === true));
    }
    assert.deepEqual(latest, before);
  });
}

test('browser export runs the same projection without CommonJS', () => {
  const context = {window: {}, Date};
  vm.runInNewContext(fs.readFileSync(require.resolve('../hub-topology.js'), 'utf8'), context);
  const model = context.window.BrainHubTopology.project('hml', envelope('hml'), NOW);
  assert.equal(node(model, 'internal').status, 'green');
  assert.equal(context.window.BrainHubTopology.dependencies(model, 'external').dependsOn[0].id, 'process');
});

test('an explicit failed PM2 state in either sample affects only process', () => {
  const latest = envelope();
  samples(latest)[0].process.status = 'stopped';
  const model = project('production', latest, NOW);
  assert.deepEqual(states(model), {...allGreen, process: 'red'});
  assert.equal(model.summary.status, 'red');
  assert.ok(node(model, 'process').checks.some(check => check.value === 'stopped' && check.ok === false));
});

test('restart change is a process failure even when both states are online', () => {
  const latest = envelope();
  samples(latest)[1].process.restarts = 3;
  const processNode = node(project('production', latest, NOW), 'process');
  assert.equal(processNode.status, 'red');
  assert.match(processNode.reason, /rein[ií]cio/i);
  assert.ok(processNode.checks.some(check => check.ok === false));
});

test('missing PM2 information is unknown rather than an inferred outage', () => {
  const latest = envelope();
  delete samples(latest)[0].process;
  const model = project('production', latest, NOW);
  assert.deepEqual(states(model), {...allGreen, process: 'unknown'});
  assert.ok(node(model, 'process').checks.some(check => check.ok === null));
});

for (const [name, change] of [
  ['HTTP error', health => {health.status = 'error';}],
  ['HTTP unavailable', health => {health.status = 'unavailable';}],
  ['incompatible HTTP response', health => {health.status = 'unexpected';}],
  ['HTTP status failure', health => {health.httpStatus = 503;}],
  ['wrong environment', health => {health.environment = 'hml';}],
  ['wrong revision', health => {health.revision = 'b'.repeat(40);}],
  ['wrong worker policy', health => {health.workerEnabled = false;}],
  ['wrong emission policy', health => {health.emissionEnabled = false;}]
]) {
  test(`${name} in the first endpoint sample is a direct failure on that endpoint`, () => {
    const latest = envelope(); change(samples(latest)[0].internal);
    const model = project('production', latest, NOW);
    assert.deepEqual(states(model), {...allGreen, internal: 'red'});
    assert.ok(node(model, 'internal').checks.some(check => check.ok === false));
    assert.ok(node(model, 'internal').reason.length > 0);
  });
}

test('both hml endpoints must prove worker and emission disabled', () => {
  const latest = envelope('hml');
  samples(latest)[0].external.workerEnabled = true;
  samples(latest)[1].internal.emissionEnabled = true;
  assert.deepEqual(states(project('hml', latest, NOW)), {...allGreen, internal: 'red', external: 'red'});
});

test('unknown endpoint fields never inherit report.ok as healthy', () => {
  const latest = envelope();
  delete samples(latest)[0].internal.revision;
  samples(latest)[1].external.workerEnabled = 'true';
  const model = project('production', latest, NOW);
  assert.deepEqual(states(model), {...allGreen, internal: 'unknown', external: 'unknown'});
});

test('expected SHA remains the validated report expectation rather than the received revision', () => {
  const latest = envelope();
  latest.observation.report.expected_sha = 'invalid';
  const model = project('production', latest, NOW);
  assert.deepEqual(states(model), {...allGreen, internal: 'unknown', external: 'unknown'});
  assert.ok(node(model, 'internal').checks.some(check => check.ok === null));
});

for (const [name, change] of [
  ['unreadable database', db => {db.ok = false;}],
  ['terminal errors', db => {db.terminalErrorsSinceDeploy = 1;}],
  ['missing logistics objects', db => {db.logisticsReviewJobs = 1;}],
  ['multiple volume reviews', db => {db.multipleVolumeReviewJobs = 1;}]
]) {
  test(`${name} is attributed to the database without poisoning unrelated aspects`, () => {
    const latest = envelope(); change(samples(latest)[0].database);
    assert.deepEqual(states(project('production', latest, NOW)), {...allGreen, database: 'red'});
  });
}

test('growing failed queue is red while a stable failed queue is normal', () => {
  const latest = envelope();
  samples(latest)[1].database.failed = 3;
  assert.deepEqual(states(project('production', latest, NOW)), {...allGreen, database: 'red'});
});

test('legacy aggregate errors are used only when terminal classification is absent', () => {
  const latest = envelope();
  for (const item of samples(latest)) {delete item.database.terminalErrorsSinceDeploy; item.database.errorsSinceDeploy = 1;}
  assert.equal(node(project('production', latest, NOW), 'database').status, 'red');
});

test('rate limiting is yellow even when aggregate assessment is successful', () => {
  const latest = envelope();
  samples(latest)[0].database.rateLimitsSinceDeploy = 2;
  samples(latest)[0].database.errorsSinceDeploy = 2;
  const model = project('production', latest, NOW);
  assert.deepEqual(states(model), {...allGreen, database: 'yellow'});
  assert.equal(model.summary.status, 'yellow');
  assert.match(node(model, 'database').reason, /rate/i);
});

test('hml processing and automatic shops are alerts rather than a false healthy policy', () => {
  const latest = envelope('hml');
  samples(latest)[0].database.processing = 1;
  samples(latest)[1].database.automaticShops = 1;
  assert.deepEqual(states(project('hml', latest, NOW)), {...allGreen, database: 'yellow'});
});

test('missing or invalid numeric database signals are insufficient evidence', () => {
  for (const value of ['0', false, -1, NaN, Infinity, 0.5, null]) {
    const latest = envelope(); samples(latest)[0].database.failed = value;
    assert.equal(node(project('production', latest, NOW), 'database').status, 'unknown', String(value));
  }
  const latest = envelope(); delete samples(latest)[1].database.logisticsReviewJobs;
  assert.equal(node(project('production', latest, NOW), 'database').status, 'unknown');
});

test('aggregate failure without attributable signals makes summary yellow while aspects stay green', () => {
  const latest = envelope(); latest.observation.report.ok = false;
  samples(latest)[0].ok = false; samples(latest)[0].failure_count = 1;
  samples(latest)[0].failure_reasons = ['Unattributed assessment'];
  const model = project('production', latest, NOW);
  assert.deepEqual(states(model), allGreen);
  assert.equal(model.summary.status, 'yellow');
});

test('unattributed warning count prevents aggregate green without inventing failed aspects', () => {
  const latest = envelope(); samples(latest)[0].warning_count = 1;
  const model = project('production', latest, NOW);
  assert.deepEqual(states(model), allGreen);
  assert.equal(model.summary.status, 'yellow');
});

test('cache ages at the strict 180 second boundary independently of BFF age hints', () => {
  const latest = envelope();
  latest.observation.collected_at = NOW - 180;
  latest.last_attempt.collected_at = NOW - 180;
  for (const item of samples(latest)) item.at = iso(NOW - 180);
  assert.deepEqual(states(project('production', latest, NOW)), allGreen);
  const old = project('production', latest, NOW + 1);
  assert.deepEqual(states(old), allYellow);
  assert.equal(old.nodes[0].ageSeconds, 181);
  assert.equal(old.summary.status, 'yellow');
});

test('old source samples remain historical after a recent successful collection', () => {
  const latest = envelope(); samples(latest)[0].at = iso(NOW - 181);
  const model = project('production', latest, NOW);
  assert.deepEqual(states(model), allYellow);
  assert.equal(model.nodes[0].ageSeconds, 181);
  assert.equal(model.observation.collectedAt, NOW - 5);
});

test('optional absent sample timestamps use the valid collection timestamp', () => {
  const latest = envelope();
  delete samples(latest)[0].at; samples(latest)[1].at = null;
  assert.deepEqual(states(project('production', latest, NOW)), allGreen);
});

test('invalid or future times cannot prove healthy current observations', () => {
  for (const collected of ['1791540000', null, NaN, Infinity, -1, NOW + 1]) {
    const latest = envelope(); latest.observation.collected_at = collected;
    assert.deepEqual(states(project('production', latest, NOW)), allUnknown);
  }
  for (const at of ['not-a-date', '2026-02-30T00:00:00.000Z', iso(NOW + 1), false, Infinity]) {
    const latest = envelope(); samples(latest)[0].at = at;
    assert.deepEqual(states(project('production', latest, NOW)), allUnknown);
  }
  assert.deepEqual(states(project('production', envelope(), NaN)), allUnknown);
});

test('divergent envelope or report environment never leaks health into another environment', () => {
  assert.deepEqual(states(project('hml', envelope('production'), NOW)), allUnknown);
  const latest = envelope(); latest.observation.report.environment = 'hml';
  assert.deepEqual(states(project('production', latest, NOW)), allUnknown);
  assert.throws(() => project('staging', envelope(), NOW), RangeError);
});

test('one or malformed source samples cannot satisfy the two sample contract', () => {
  for (const snapshots of [[sample()], [sample(), null], [], 'invalid']) {
    const latest = envelope(); latest.observation.report.snapshots = snapshots;
    assert.deepEqual(states(project('production', latest, NOW)), allUnknown);
  }
});

test('failed collection keeps a fresh direct failure only as yellow historical evidence', () => {
  const latest = envelope(); samples(latest)[0].process.status = 'stopped';
  latest.collection_failed = true;
  latest.last_attempt = {id: 8, collected_at: NOW - 1, error: 'SOURCE_UNAVAILABLE'};
  const model = project('production', latest, NOW);
  assert.deepEqual(states(model), allYellow);
  assert.equal(model.summary.status, 'yellow');
  assert.deepEqual(model.collection, {status: 'failed', lastAttemptAt: NOW - 1});
  assert.equal(model.observation.collectedAt, NOW - 5);
  assert.ok(node(model, 'process').checks.some(check => check.value === 'stopped' && check.ok === false));
  assert.match(node(model, 'process').reason, /hist[oó]ric|anterior/i);
  assert.match(node(model, 'process').reason, /PM2|processo/i);
});

test('expired direct failure is yellow rather than a current outage', () => {
  const latest = envelope(); samples(latest)[0].external.status = 'error';
  const model = project('production', latest, NOW + 181);
  assert.deepEqual(states(model), allYellow);
  assert.ok(node(model, 'external').checks.some(check => check.ok === false));
  assert.match(node(model, 'external').reason, /hist[oó]ric|anterior/i);
});

test('failed collection without any observation stays unknown', () => {
  const model = project('hml', {environment: 'hml', collection_failed: true,
    last_attempt: {collected_at: NOW - 1, error: 'SOURCE_UNAVAILABLE'}, observation: null}, NOW);
  assert.deepEqual(states(model), allUnknown);
  assert.equal(model.collection.status, 'failed');
  assert.equal(model.summary.status, 'unknown');
});

test('raw payloads and arbitrary assessment text are excluded from node checks', () => {
  const latest = envelope();
  samples(latest)[0].database.orders = [{private: 'payload-marker'}];
  samples(latest)[0].failure_reasons = ['payload-marker'];
  samples(latest)[0].process.raw = 'payload-marker';
  const model = project('production', latest, NOW);
  assert.ok(!JSON.stringify(model).includes('payload-marker'));
  assert.deepEqual(states(model), allGreen);
});

test('invalid collection flags and attempt timestamps cannot certify a successful current collection', () => {
  for (const [key, value] of [['stale', 'false'], ['collection_failed', 'false']]) {
    const latest = envelope(); latest[key] = value;
    assert.deepEqual(states(project('production', latest, NOW)), allUnknown, key);
  }
  for (const at of ['1791540000', false, null, NaN, Infinity, -1, NOW + 1]) {
    const latest = envelope(); latest.last_attempt.collected_at = at;
    const model = project('production', latest, NOW);
    assert.deepEqual(states(model), allUnknown, String(at));
    assert.deepEqual(model.collection, {status: 'missing', lastAttemptAt: null});
  }
});
