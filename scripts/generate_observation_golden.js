// Gera tests/fixtures/observation_golden.json: entradas fixas e saidas do project() de
// dashboard/hub-topology.js (fonte da verdade). O teste Python compara o porte contra este arquivo.
// Uso: node scripts/generate_observation_golden.js
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {project} = require('../dashboard/hub-topology.js');

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
const samples = latest => latest.observation.report.snapshots;
function mutated(change, environment = 'production') {
  const latest = envelope(environment);
  change(latest);
  return latest;
}

// [name, environment, latest, now]
const INPUTS = [
  ['all green production', 'production', envelope(), NOW],
  ['all green hml', 'hml', envelope('hml'), NOW],
  ['observation absent (null)', 'production', null, NOW],
  ['observation absent (empty object)', 'hml', {}, NOW],
  ['stale by age 181s', 'production', envelope(), NOW + 181],
  ['stale at the 180s boundary stays green', 'production', mutated(l => {
    l.observation.collected_at = NOW - 180; l.last_attempt.collected_at = NOW - 180;
    samples(l).forEach(item => {item.at = iso(NOW - 180);});
  }), NOW],
  ['stale flag from BFF', 'production', mutated(l => {l.stale = true;}), NOW],
  ['old source sample with recent collection', 'production', mutated(l => {samples(l)[0].at = iso(NOW - 181);}), NOW],
  ['collection failed keeps direct failure as yellow history', 'production', mutated(l => {
    samples(l)[0].process.status = 'stopped';
    l.collection_failed = true;
    l.last_attempt = {id: 8, collected_at: NOW - 1, error: 'SOURCE_UNAVAILABLE'};
  }), NOW],
  ['collection failed without observation', 'hml', {environment: 'hml', collection_failed: true,
    last_attempt: {collected_at: NOW - 1, error: 'SOURCE_UNAVAILABLE'}, observation: null}, NOW],
  ['database unreadable', 'production', mutated(l => {samples(l)[0].database.ok = false;}), NOW],
  ['database failed queue growing', 'production', mutated(l => {samples(l)[1].database.failed = 3;}), NOW],
  ['database failed value invalid (string)', 'production', mutated(l => {samples(l)[0].database.failed = '0';}), NOW],
  ['database terminal errors', 'production', mutated(l => {samples(l)[0].database.terminalErrorsSinceDeploy = 1;}), NOW],
  ['database legacy aggregate errors', 'production', mutated(l => {
    samples(l).forEach(item => {delete item.database.terminalErrorsSinceDeploy; item.database.errorsSinceDeploy = 1;});
  }), NOW],
  ['rate limits yellow', 'production', mutated(l => {
    samples(l)[0].database.rateLimitsSinceDeploy = 2; samples(l)[0].database.errorsSinceDeploy = 2;
  }), NOW],
  ['logistics review jobs', 'production', mutated(l => {samples(l)[0].database.logisticsReviewJobs = 1;}), NOW],
  ['multiple volume review jobs', 'production', mutated(l => {samples(l)[0].database.multipleVolumeReviewJobs = 1;}), NOW],
  ['hml processing and automatic shops alerts', 'hml', mutated(l => {
    samples(l)[0].database.processing = 1; samples(l)[1].database.automaticShops = 1;
  }, 'hml'), NOW],
  ['hml database logistics and rate limit together', 'hml', mutated(l => {
    samples(l)[0].database.logisticsReviewJobs = 2; samples(l)[1].database.rateLimitsSinceDeploy = 1;
    samples(l)[1].database.processing = 3;
  }, 'hml'), NOW],
  ['process stopped', 'production', mutated(l => {samples(l)[0].process.status = 'stopped';}), NOW],
  ['process restarted between samples', 'production', mutated(l => {samples(l)[1].process.restarts = 3;}), NOW],
  ['process section missing', 'production', mutated(l => {delete samples(l)[0].process;}), NOW],
  ['process offline in both samples and restarted', 'production', mutated(l => {
    samples(l).forEach(item => {item.process.status = 'errored';}); samples(l)[1].process.restarts = 5;
  }), NOW],
  ['internal revision mismatch', 'production', mutated(l => {samples(l)[0].internal.revision = 'b'.repeat(40);}), NOW],
  ['external revision missing', 'production', mutated(l => {delete samples(l)[0].external.revision;}), NOW],
  ['expected sha invalid', 'production', mutated(l => {l.observation.report.expected_sha = 'invalid';}), NOW],
  ['internal and external SHA mismatch', 'production', mutated(l => {
    samples(l)[0].internal.revision = 'c'.repeat(40); samples(l)[1].external.revision = 'd'.repeat(40);
  }), NOW],
  ['internal http error', 'production', mutated(l => {samples(l)[0].internal.status = 'error';}), NOW],
  ['internal http status 503', 'production', mutated(l => {samples(l)[0].internal.httpStatus = 503;}), NOW],
  ['external wrong environment', 'production', mutated(l => {samples(l)[1].external.environment = 'hml';}), NOW],
  ['workerEnabled false in production', 'production', mutated(l => {samples(l)[0].internal.workerEnabled = false;}), NOW],
  ['workerEnabled true in hml', 'hml', mutated(l => {samples(l)[0].external.workerEnabled = true;}, 'hml'), NOW],
  ['workerEnabled false in hml is normal', 'hml', mutated(l => {samples(l)[0].internal.workerEnabled = false;}, 'hml'), NOW],
  ['emissionEnabled mismatch production', 'production', mutated(l => {samples(l)[0].external.emissionEnabled = false;}), NOW],
  ['emissionEnabled true in hml', 'hml', mutated(l => {samples(l)[1].internal.emissionEnabled = true;}, 'hml'), NOW],
  ['endpoint workerEnabled string', 'production', mutated(l => {samples(l)[1].external.workerEnabled = 'true';}), NOW],
  ['aggregate failure unattributed', 'production', mutated(l => {
    l.observation.report.ok = false; samples(l)[0].ok = false; samples(l)[0].failure_count = 1;
  }), NOW],
  ['unattributed warning count', 'production', mutated(l => {samples(l)[0].warning_count = 1;}), NOW],
  ['missing failure_count', 'production', mutated(l => {delete samples(l)[1].failure_count;}), NOW],
  ['sample timestamps absent use collection time', 'production', mutated(l => {
    delete samples(l)[0].at; samples(l)[1].at = null;
  }), NOW],
  ['sample timestamp invalid date', 'production', mutated(l => {samples(l)[0].at = '2026-02-30T00:00:00.000Z';}), NOW],
  ['sample timestamp in the future', 'production', mutated(l => {samples(l)[0].at = iso(NOW + 1);}), NOW],
  ['collected_at in the future', 'production', mutated(l => {l.observation.collected_at = NOW + 1;}), NOW],
  ['collected_at as string', 'production', mutated(l => {l.observation.collected_at = '1791540000';}), NOW],
  ['envelope environment diverges', 'hml', envelope('production'), NOW],
  ['report environment diverges', 'production', mutated(l => {l.observation.report.environment = 'hml';}), NOW],
  ['malformed snapshots length 1', 'production', mutated(l => {l.observation.report.snapshots = [sample()];}), NOW],
  ['malformed snapshots with null item', 'production', mutated(l => {l.observation.report.snapshots = [sample(), null];}), NOW],
  ['malformed snapshots empty', 'production', mutated(l => {l.observation.report.snapshots = [];}), NOW],
  ['malformed snapshots string', 'production', mutated(l => {l.observation.report.snapshots = 'invalid';}), NOW],
  ['stale flag as string', 'production', mutated(l => {l.stale = 'yes';}), NOW],
  ['collection_failed flag as string', 'production', mutated(l => {l.collection_failed = 'false';}), NOW],
  ['last_attempt collected_at in the future', 'production', mutated(l => {l.last_attempt.collected_at = NOW + 1;}), NOW],
  ['last_attempt not an object', 'production', mutated(l => {l.last_attempt = 'x';}), NOW],
  ['last_attempt absent', 'production', mutated(l => {delete l.last_attempt;}), NOW],
  ['stale and collection failed with unknown node', 'production', mutated(l => {
    delete samples(l)[0].process; l.stale = true; l.collection_failed = true;
  }), NOW],
  ['report ok false', 'production', mutated(l => {l.observation.report.ok = false;}), NOW]
];

function expectedOf(environment, latest, now) {
  const model = project(environment, latest, now);
  const evaluated = model.nodes[0].observedAt !== null;
  // O modelo JS nao expoe flag de obsolescencia: deriva-se da mesma regra de project()
  // (ageSeconds > 180 || latest.stale === true), valida apenas quando a observacao foi avaliada.
  const stale = evaluated && (model.nodes[0].ageSeconds > 180 || latest.stale === true);
  return {
    status: model.summary.status, reason: model.summary.reason, stale,
    nodes: model.nodes.map(({id, status, reason}) => ({id, status, reason}))
  };
}

const cases = INPUTS.map(([name, environment, latest, now]) => ({
  name, environment, latest: JSON.parse(JSON.stringify(latest)), now,
  expected: expectedOf(environment, latest, now)
}));
const out = path.join(__dirname, '..', 'tests', 'fixtures', 'observation_golden.json');
fs.writeFileSync(out, JSON.stringify({cases}, null, 2) + '\n');
console.log('wrote ' + cases.length + ' cases to ' + path.relative(process.cwd(), out));
