"""BFF da fase 6: playbooks, regras e avaliação de observação numa origem só."""
import json
import shutil
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.assessment import build_assessment
from backend.playbooks_api import PlaybooksApi
from backend.server import handler_for
from backend.store import Store

REAL_VAULT = Path(__file__).resolve().parent.parent / 'vault'
REF = 'vault/playbooks/PB-001-suite-automatizada-do-hub.md:3'


def _sample(environment):
    enabled = environment == 'production'
    health = {'status': 'ok', 'environment': environment, 'revision': 'a' * 40,
              'emissionEnabled': enabled, 'workerEnabled': enabled, 'version': '1.0.0'}
    return {'at': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime()), 'ok': True,
            'failure_count': 0, 'failure_reasons': [], 'warning_count': 0,
            'process': {'status': 'online', 'restarts': 2, 'uptime': 1000, 'memoryBytes': 100000},
            'internal': dict(health), 'external': dict(health),
            'database': {'ok': True, 'pending': 3, 'processing': 0, 'failed': 2, 'errorsSinceDeploy': 0,
                         'automaticShops': 0, 'rateLimitsSinceDeploy': 0, 'terminalErrorsSinceDeploy': 0,
                         'logisticsReviewJobs': 0, 'multipleVolumeReviewJobs': 0}}


def _report(environment, database_ok=True):
    samples = [_sample(environment), _sample(environment)]
    if not database_ok:
        for sample in samples:
            sample['database']['ok'] = False
    return {'environment': environment, 'ok': database_ok, 'expected_sha': 'a' * 40, 'snapshots': samples}


def _rule(rule_id, light, environments):
    return {'id': rule_id, 'light': light, 'test_environments': environments}


class Phase6Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        vault = root / 'project' / 'vault'
        for part in ('rules', 'playbooks'):
            shutil.copytree(REAL_VAULT / part, vault / part)
        self.playbooks = PlaybooksApi(vault)
        self.store = Store(root / 'brain.db')
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.store, root, 0, playbooks=self.playbooks))
        self.port = server.server_port
        server.RequestHandlerClass = handler_for(self.store, root, self.port, playbooks=self.playbooks)
        self.server = server
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = 'brain_session=' + self.store.issue('session', 60)
        self.origin = f'http://127.0.0.1:{self.port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def call(self, path, method='GET', body=None, headers=None, session=True, origin=True, json_type=True):
        merged = dict(headers or {})
        if session:
            merged['Cookie'] = self.cookie
        if origin and method == 'POST':
            merged.setdefault('Origin', self.origin)
        if body is not None:
            merged['Content-Type'] = 'application/json' if json_type else 'text/plain'
        data = json.dumps(body).encode() if body is not None else (b'' if method == 'POST' else None)
        request = Request(self.origin + path, data=data, headers=merged, method=method)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            payload = json.load(error)
            error.close()
            return error.code, payload

    def execution(self, **over):
        body = {'playbook_id': 'PB-001', 'result': 'pass', 'environment': 'local',
                'summary': 'suite verde', 'evidence_ref': REF}
        body.update(over)
        return body

    def record(self, **over):
        status, payload = self.call('/api/playbooks/executions', 'POST', self.execution(**over))
        self.assertEqual(status, 201, payload)

    def inject(self, environment, report):
        self.store.record(environment, payload=report)


class AuthAndOriginTest(Phase6Base):
    def test_every_new_route_needs_a_session(self):
        for method, path in [('GET', '/api/playbooks'), ('GET', '/api/playbooks/'), ('GET', '/api/playbooks/PB-001'),
                             ('GET', '/api/playbooks/PB-001/executions'), ('GET', '/api/playbooks/executions'),
                             ('GET', '/api/rules'), ('GET', '/v1/observability/assessment'),
                             ('POST', '/api/playbooks/executions'), ('POST', '/api/playbooks/PB-001/render')]:
            with self.subTest(path=path, method=method):
                status, payload = self.call(path, method, {} if method == 'POST' else None, session=False)
                self.assertEqual(status, 401)
                self.assertEqual(payload['error'], 'AUTH_REQUIRED')

    def test_post_with_wrong_origin_is_denied(self):
        for path in ('/api/playbooks/executions', '/api/playbooks/PB-001/render'):
            with self.subTest(path=path):
                status, payload = self.call(path, 'POST', {}, headers={'Origin': 'https://evil.example'})
                self.assertEqual(status, 403)
                self.assertEqual(payload['error'], 'ORIGIN_DENIED')

    def test_post_without_origin_is_denied(self):
        status, _ = self.call('/api/playbooks/executions', 'POST', {}, origin=False)
        self.assertEqual(status, 403)

    def test_other_post_paths_stay_read_only_and_unknown_api_is_404(self):
        self.assertEqual(self.call('/api/rules', 'POST', {})[1]['error'], 'READ_ONLY_API')
        self.assertEqual(self.call('/api/playbooks', 'POST', {})[1]['error'], 'READ_ONLY_API')
        status, payload = self.call('/api/nothing')
        self.assertEqual((status, payload['error']), (404, 'NOT_FOUND'))


class PlaybooksAndRulesTest(Phase6Base):
    def test_rules_one_row_per_rule_with_light(self):
        status, payload = self.call('/api/rules')
        self.assertEqual(status, 200)
        ids = [r['id'] for r in payload['rules']]
        self.assertEqual(ids, sorted(ids))
        self.assertGreaterEqual(len(ids), 2)
        for row in payload['rules']:
            self.assertIn(row['light'], ('green', 'yellow', 'red', 'grey'))

    def test_playbooks_list_and_detail_carry_kind(self):
        status, payload = self.call('/api/playbooks')
        self.assertEqual(status, 200)
        by_id = {p['id']: p for p in payload['playbooks']}
        self.assertEqual(by_id['PB-001']['kind'], 'test')
        status, detail = self.call('/api/playbooks/PB-001')
        self.assertEqual((status, detail['meta']['kind']), (200, 'test'))
        self.assertEqual(self.call('/api/playbooks/PB-001/executions')[0], 200)
        self.assertEqual(self.call('/api/playbooks/executions')[0], 200)
        self.assertEqual(self.call('/api/playbooks/PB-999')[0], 404)

    def test_execution_validation_and_content_type(self):
        status, payload = self.call('/api/playbooks/executions', 'POST', self.execution(evidence_ref=''))
        self.assertEqual((status, payload['error']), (400, 'VALIDATION_FAILED'))
        status, payload = self.call('/api/playbooks/executions', 'POST', self.execution(), json_type=False)
        self.assertEqual((status, payload['error']), (415, 'JSON_REQUIRED'))
        status, payload = self.call('/api/playbooks/PB-001/render', 'POST', {'params': {}}, json_type=False)
        self.assertEqual((status, payload['error']), (415, 'JSON_REQUIRED'))

    def test_recording_an_execution_changes_the_rule_light(self):
        def row(rule_id):
            return next(r for r in self.call('/api/rules')[1]['rules'] if r['id'] == rule_id)
        self.assertNotEqual(row('RULE-002')['light'], 'green')
        self.record()
        self.assertEqual(row('RULE-002')['light'], 'green')

    def test_render_returns_content(self):
        status, payload = self.call('/api/playbooks/PB-001/render', 'POST', {'params': {}})
        self.assertEqual(status, 200)
        self.assertIn('rendered_content', payload)

    def test_rules_503_when_evidence_db_is_unavailable(self):
        from core.evidence_store import EvidenceStoreError

        def broken(*args, **kwargs):
            raise EvidenceStoreError('boom')
        self.playbooks._store = broken
        status, payload = self.call('/api/rules')
        self.assertEqual((status, payload['error']), (503, 'DB_UNAVAILABLE'))


class AssessmentRouteTest(Phase6Base):
    def test_without_observation_is_200_and_not_green(self):
        status, payload = self.call('/v1/observability/assessment')
        self.assertEqual(status, 200)
        self.assertEqual(payload['environment'], 'production')
        self.assertIn(payload['status'], ('unknown', 'yellow'))
        self.assertEqual(payload['contradictions'], [])
        self.assertEqual([n['id'] for n in payload['nodes']], ['process', 'internal', 'external', 'database'])
        for key in ('schema_version', 'space_id', 'request_id', 'reason', 'stale'):
            self.assertIn(key, payload)

    def test_invalid_environment_and_space(self):
        status, payload = self.call('/v1/observability/assessment?environment=staging')
        self.assertEqual((status, payload['error']), (400, 'INVALID_ENVIRONMENT'))
        self.assertEqual(self.call('/v1/observability/assessment?space=other')[0], 403)

    def test_green_rule_against_red_environment_is_a_contradiction(self):
        self.record()                                                           # PB-001 local pass
        self.record(playbook_id='PB-002', environment='hml', evidence_ref=REF)  # PB-002 hml pass
        rules = {r['id']: r for r in self.call('/api/rules')[1]['rules']}
        self.assertEqual(rules['RULE-001']['light'], 'green')
        self.inject('hml', _report('hml', database_ok=False))
        self.inject('production', _report('production'))
        status, hml = self.call('/v1/observability/assessment?environment=hml')
        self.assertEqual(status, 200)
        self.assertEqual(hml['status'], 'red')
        self.assertEqual([(c['rule_id'], c['environment'], c['light'], c['health']) for c in hml['contradictions']],
                         [('RULE-001', 'hml', 'green', 'red')])
        status, production = self.call('/v1/observability/assessment?environment=production')
        self.assertNotEqual(production['status'], 'red')
        self.assertEqual(production['contradictions'], [])


class HardeningTest(Phase6Base):
    def raw_post(self, path, raw, headers=None):
        merged = {'Cookie': self.cookie, 'Origin': self.origin, 'Content-Type': 'application/json'}
        merged.update(headers or {})
        request = Request(self.origin + path, data=raw, headers=merged, method='POST')
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            payload = json.load(error)
            error.close()
            return error.code, payload

    def test_non_object_or_invalid_json_bodies_are_400_and_server_survives(self):
        for path in ('/api/playbooks/executions', '/api/playbooks/PB-001/render'):
            for raw in (b'[]', b'null', b'"x"', b'12', b'{not json'):
                with self.subTest(path=path, raw=raw):
                    status, payload = self.raw_post(path, raw)
                    self.assertEqual((status, payload['error']), (400, 'INVALID_JSON'))
                    self.assertEqual(self.call('/api/rules')[0], 200)

    def test_unexpected_exception_in_handle_is_a_clean_500(self):
        def boom(path, method='GET', body=b''):
            raise RuntimeError('secret detail /etc/passwd')
        self.playbooks.handle = boom
        status, payload = self.call('/api/rules')
        self.assertEqual((status, payload['error']), (500, 'INTERNAL'))
        self.assertNotIn('secret', json.dumps(payload))
        status, payload = self.call('/api/playbooks/executions', 'POST', self.execution())
        self.assertEqual((status, payload['error']), (500, 'INTERNAL'))

    def test_non_string_metadata_is_a_validation_error(self):
        for field in ('trace_id', 'source', 'recorded_by'):
            for value in (5, ['a'], {'a': 1}, True):
                with self.subTest(field=field, value=value):
                    status, payload = self.call('/api/playbooks/executions', 'POST', self.execution(**{field: value}))
                    self.assertEqual((status, payload['error']), (400, 'VALIDATION_FAILED'))

    def test_db_unavailable_detail_is_fixed_and_leaks_no_path(self):
        from core.evidence_store import EvidenceStoreError

        def broken(*args, **kwargs):
            raise EvidenceStoreError('cannot open C:\\secret\\evidence.db')
        self.playbooks._store = broken
        status, payload = self.call('/api/rules')
        self.assertEqual((status, payload['error'], payload['detail']), (503, 'DB_UNAVAILABLE', 'evidence database unavailable'))
        self.assertNotIn('secret', json.dumps(payload))
        status, payload = self.call('/api/playbooks/executions', 'POST', self.execution())
        self.assertEqual((status, payload['detail']), (503, 'evidence database unavailable'))

    def test_traversal_and_odd_ids_never_return_file_content(self):
        for path in ('/api/playbooks/..', '/api/playbooks/%2F', '/api/playbooks/%2e%2e', '/api/playbooks/..%2F..%2Fetc',
                     '/api/playbooks/' + 'A' * 300, '/api/playbooks/PB-001%0A'):
            with self.subTest(path=path):
                status, payload = self.call(path)
                self.assertIn(status, (400, 404))
                self.assertNotIn('content', payload)

    def test_cross_site_post_is_denied_even_with_matching_origin(self):
        status, payload = self.call('/api/playbooks/executions', 'POST', self.execution(),
                                    headers={'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual((status, payload['error']), (403, 'ORIGIN_DENIED'))


class BuildAssessmentTest(unittest.TestCase):
    NOW = time.time() + 30  # sample timestamps are taken at test time and must not be in the future

    def latest(self, **reports):
        return {env: {'environment': env, 'last_attempt': None, 'collection_failed': False, 'stale': False,
                      'age_seconds': 1.0,
                      'observation': {'id': 1, 'collected_at': self.NOW - 1, 'report': report}}
                for env, report in reports.items()}

    def test_contradictions_only_for_requested_environment(self):
        latest = self.latest(production=_report('production', database_ok=False), hml=_report('hml', database_ok=False))
        rules = [_rule('RULE-X', 'green', ['production', 'hml'])]
        production = build_assessment('production', latest, rules, self.NOW)
        self.assertEqual([c['environment'] for c in production['contradictions']], ['production'])
        self.assertEqual(build_assessment('hml', latest, rules, self.NOW)['contradictions'][0]['environment'], 'hml')
        self.assertIs(production['rules_available'], True)

    def test_non_green_or_unobserved_rules_do_not_contradict(self):
        latest = self.latest(production=_report('production', database_ok=False))
        rules = [_rule('A', 'yellow', ['production']), _rule('B', 'green', ['local'])]
        self.assertEqual(build_assessment('production', latest, rules, self.NOW)['contradictions'], [])

    def test_rules_failure_keeps_assessment_without_contradictions(self):
        latest = self.latest(production=_report('production', database_ok=False))

        def broken():
            raise RuntimeError('evidence down')
        result = build_assessment('production', latest, broken, self.NOW)
        self.assertEqual(result['status'], 'red')
        self.assertEqual(result['contradictions'], [])
        self.assertIs(result['rules_available'], False)

    def test_missing_latest_is_not_green(self):
        result = build_assessment('hml', {}, [], self.NOW)
        self.assertNotEqual(result['status'], 'green')
        self.assertEqual(len(result['nodes']), 4)


if __name__ == '__main__':
    unittest.main()
