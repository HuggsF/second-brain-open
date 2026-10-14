import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.store import Store
from backend.server import handler_for
from backend.workflow_api import MAX_BODY_BYTES, WorkflowApi
from dashboard.serve import make_handler


def make_root(tmp):
    root = Path(tmp)
    (root / 'vault' / 'adrs').mkdir(parents=True)
    (root / 'vault' / 'adrs' / 'ADR-013-adocao-padroes-mba-full-cycle-ia.md').write_bytes(b'# ADR-013\r\n')
    return root


class WorkflowApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(self.tmp.name)
        self.api = WorkflowApi(self.root, port=9999)

    def tearDown(self):
        self.tmp.cleanup()

    def test_execute_step_writes_audit_and_grounds_in_vault(self):
        status, data, headers = self.api.handle('POST', '/api/workflow/execute-step', json.dumps({'agent': 'architect', 'input': 'ADR 013', 'trace_id': 't1'}).encode())
        self.assertEqual(status, 200)
        self.assertEqual(data['backend']['trace_id'], 't1')
        self.assertEqual(data['backend']['server_port'], 9999)
        self.assertEqual(data['backend']['vault_grounding']['file'], 'vault/adrs/ADR-013-adocao-padroes-mba-full-cycle-ia.md')
        self.assertEqual(headers['X-Trace-ID'], 't1')
        records = self.api.handle('GET', '/api/workflow/audit-log', b'')[1]
        self.assertEqual(records['total'], 1)
        self.assertEqual(records['records'][0]['agent'], 'architect')

    def test_telemetry_and_reset(self):
        self.api.handle('POST', '/api/workflow/execute-step', b'{}')
        telemetry = self.api.handle('GET', '/api/workflow/telemetry', b'')[1]
        self.assertEqual(telemetry['vault_documents_on_disk'], 1)
        self.assertEqual(telemetry['server_port'], 9999)
        self.assertGreater(telemetry['audit_log_size_bytes'], 0)
        self.assertEqual(self.api.handle('POST', '/api/workflow/reset-audit', b'')[0], 200)
        self.assertEqual(self.api.handle('GET', '/api/workflow/audit-log', b'')[1]['total'], 0)

    def test_refuses_invalid_or_oversized_body_and_unknown_routes(self):
        self.assertEqual(self.api.handle('POST', '/api/workflow/execute-step', b'{not json')[0], 400)
        self.assertEqual(self.api.handle('POST', '/api/workflow/execute-step', b'[1]')[0], 400)
        self.assertEqual(self.api.handle('POST', '/api/workflow/execute-step', b'{}' + b' ' * MAX_BODY_BYTES)[0], 413)
        self.assertEqual(self.api.handle('GET', '/api/workflow/execute-step', b'')[0], 405)
        self.assertIsNone(self.api.handle('GET', '/api/workflow/other', b''))
        self.assertFalse(self.api.audit_file.exists())


class BffWorkflowRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = make_root(self.tmp.name)
        self.store = Store(root / 'brain.db')
        self.api = WorkflowApi(root)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.store, root, 0, self.api))
        self.port = self.server.server_port
        self.server.RequestHandlerClass = handler_for(self.store, root, self.port, self.api)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.port}'
        self.cookie = 'brain_session=' + self.store.issue('session', 60)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.tmp.cleanup()

    def request(self, path, method='GET', body=None, headers=None):
        return urlopen(Request(self.origin + path, data=body, method=method, headers=headers or {}), timeout=2)

    def status(self, *args, **kwargs):
        try:
            with self.request(*args, **kwargs) as response:
                return response.status
        except HTTPError as error:
            error.close()
            return error.code

    def test_session_can_use_workflow_api(self):
        with self.request('/api/workflow/telemetry', headers={'Cookie': self.cookie}) as response:
            self.assertEqual(json.load(response)['server_port'], self.port)
        body = json.dumps({'agent': 'qa'}).encode()
        with self.request('/api/workflow/execute-step', 'POST', body, {'Cookie': self.cookie, 'Origin': self.origin, 'Content-Type': 'application/json'}) as response:
            self.assertTrue(json.load(response)['success'])
        self.assertEqual(self.api.handle('GET', '/api/workflow/audit-log', b'')[1]['total'], 1)

    def test_refusals(self):
        post = {'Cookie': self.cookie, 'Origin': self.origin, 'Content-Type': 'application/json'}
        self.assertEqual(self.status('/api/workflow/telemetry'), 401)
        self.assertEqual(self.status('/api/workflow/execute-step', 'POST', b'{}', {**post, 'Cookie': ''}), 401)
        self.assertEqual(self.status('/api/workflow/execute-step', 'POST', b'{}', {**post, 'Origin': 'https://evil.example'}), 403)
        self.assertEqual(self.status('/api/workflow/reset-audit', 'POST', b'', {'Cookie': self.cookie}), 403)
        self.assertEqual(self.status('/api/workflow/execute-step', 'POST', b'{}', {**post, 'Content-Type': 'text/plain'}), 415)
        self.assertEqual(self.status('/v1/capabilities', 'POST', b'{}', post), 405)
        self.assertEqual(self.status('/api/workflow/unknown', 'POST', b'{}', post), 404)
        self.assertFalse(self.api.audit_file.exists())

    def test_refusal_with_unread_body_arrives_as_http_status(self):
        # Answering before reading the body made Windows reset the socket (ConnectionAbortedError).
        body = b'{"agent": "' + b'x' * 60000 + b'"}'
        for _ in range(10):
            self.assertEqual(self.status('/api/workflow/execute-step', 'POST', body, {'Origin': 'https://evil.example', 'Content-Type': 'application/json'}), 403)
            self.assertEqual(self.status('/api/workflow/execute-step', 'POST', body, {'Origin': self.origin, 'Content-Type': 'application/json'}), 401)


class DashboardServeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.api = WorkflowApi(make_root(self.tmp.name))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.api))
        self.port = self.server.server_port
        self.api.port = self.port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.tmp.cleanup()

    def call(self, path, method='GET', body=None, headers=None):
        try:
            with urlopen(Request(f'http://127.0.0.1:{self.port}' + path, data=body, method=method, headers=headers or {}), timeout=2) as response:
                return response.status, dict(response.headers), response.read()
        except HTTPError as error:
            error.close()
            return error.code, dict(error.headers), b''

    def test_same_origin_post_is_recorded_without_open_cors(self):
        origin = f'http://127.0.0.1:{self.port}'
        status, headers, body = self.call('/api/workflow/execute-step', 'POST', b'{"agent": "dev"}', {'Origin': origin, 'Content-Type': 'application/json'})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['success'])
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        status, headers, body = self.call('/api/workflow/telemetry')
        self.assertEqual((status, json.loads(body)['server_port']), (200, self.port))
        self.assertEqual(self.call('/index.html')[0], 404)  # tmp root has no dashboard files; static stays confined

    def test_dev_server_serves_the_embedded_jev_folder(self):
        dashboard = Path(__file__).resolve().parent.parent / 'dashboard'
        self.server.RequestHandlerClass = make_handler(self.api, directory=dashboard)
        status, headers, body = self.call('/dashboard/jev/index.html')
        self.assertEqual(status, 200)
        self.assertIn('text/html', {k.lower(): v for k, v in headers.items()}['content-type'])
        self.assertIn(b'<div id="root">', body)
        asset = [part for part in body.decode().split('"') if part.startswith('./assets/')][0][2:]
        self.assertEqual(self.call('/dashboard/jev/' + asset)[0], 200)
        csp = {k.lower(): v for k, v in headers.items()}['content-security-policy']
        self.assertIn("frame-ancestors 'self'", csp)
        self.assertNotIn("frame-ancestors 'none'", csp)
        self.assertIn("frame-ancestors 'self'", {k.lower(): v for k, v in self.call('/dashboard/jev/' + asset)[1].items()}['content-security-policy'])
        for other in ('/dashboard/index.html', '/dashboard/jev/x.map', '/dashboard/jevx/index.html', '/dashboard/jev/../index.html'):
            other_csp = {k.lower(): v for k, v in self.call(other)[1].items()}['content-security-policy']
            self.assertIn("frame-ancestors 'none'", other_csp, other)
        self.assertEqual(self.call('/dashboard/jev/x.map')[0], 404)
        self.assertEqual(self.call('/dashboard/jev/../../backend/server.py')[0], 404)

    def test_refuses_cross_origin_writes(self):
        for headers in ({'Origin': 'https://evil.example', 'Content-Type': 'application/json'}, {'Content-Type': 'application/json'}):
            self.assertEqual(self.call('/api/workflow/reset-audit', 'POST', b'', headers)[0], 403)
            self.assertEqual(self.call('/api/workflow/execute-step', 'POST', b'{}', headers)[0], 403)
        self.assertEqual(self.call('/api/workflow/execute-step', 'OPTIONS')[0], 405)
        self.assertFalse(self.api.audit_file.exists())

    def test_refusal_with_unread_body_arrives_as_http_status(self):
        body = b'{"agent": "' + b'x' * 60000 + b'"}'
        for _ in range(10):
            self.assertEqual(self.call('/api/workflow/execute-step', 'POST', body, {'Origin': 'https://evil.example', 'Content-Type': 'application/json'})[0], 403)


if __name__ == '__main__':
    unittest.main()
