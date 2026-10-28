import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.server import handler_for
from backend.store import Store


def fake_result(n=2, content_size=900):
    citations = [
        {'document': f'systems/doc{i}.md', 'section': f'Secao {i}', 'line_start': 1 + i, 'line_end': 9 + i,
         'sha256': 'a' * 64, 'score': 0.9 - i * 0.1, 'stale': False}
        for i in range(n)
    ]
    sources = [{'content': 'c' * content_size, 'document': c['document']} for c in citations]
    return {'citations': citations, 'gaps': [], 'index_version': 'v-test', 'sources': sources}


class RetrievalsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'brain.db')
        self.retriever = mock.Mock()
        self.retriever.query.return_value = fake_result()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.store, Path(self.tmp.name), 0, retriever=self.retriever))
        self.port = self.server.server_port
        self.server.RequestHandlerClass = handler_for(self.store, Path(self.tmp.name), self.port, retriever=self.retriever)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.port}'
        self.cookie = 'brain_session=' + self.store.issue('session', 60)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def send(self, method, path, raw=None, headers=None):
        request = Request(self.origin + path, data=raw, method=method, headers=headers or {})
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            try:
                return exc.code, json.load(exc)
            finally:
                exc.close()

    def post(self, payload, path='/v1/retrievals', raw=None, headers=None):
        base = {'Content-Type': 'application/json', 'Origin': self.origin, 'Cookie': self.cookie}
        base.update(headers or {})
        data = raw if raw is not None else json.dumps(payload).encode()
        return self.send('POST', path, data, base)

    def get(self, path):
        return self.send('GET', path, None, {'Cookie': self.cookie})[1]

    def test_ok(self):  # CA-09
        status, body = self.post({'query': 'emissão', 'limit': 3})
        self.assertEqual(status, 200)
        self.assertTrue({'schema_version', 'space_id', 'request_id', 'mode', 'citations', 'gaps', 'index_version', 'timings_ms'} <= set(body))
        self.assertEqual((body['mode'], body['space_id'], body['index_version']), ('vector', 'kiosk', 'v-test'))
        self.assertEqual(body['query'], 'emissão')
        self.assertIsInstance(body['timings_ms']['retrieval'], int)
        self.assertEqual(len(body['citations']), 2)
        self.assertTrue(all(len(c['excerpt']) == 400 and 'content' not in c and 'payload' not in c for c in body['citations']))
        self.assertEqual(body['citations'][0]['document'], 'systems/doc0.md')
        self.retriever.query.assert_called_once_with('emissão', limit=3, category=None, include_content=True)

    def test_defaults_strip_and_category(self):
        status, body = self.post({'query': '  oi  ', 'category': 'systems'})
        self.assertEqual((status, body['query']), (200, 'oi'))
        self.retriever.query.assert_called_once_with('oi', limit=5, category='systems', include_content=True)
        self.retriever.query.reset_mock()
        self.assertEqual(self.post({'query': 'oi', 'category': None})[0], 200)

    def test_short_content_excerpt(self):
        self.retriever.query.return_value = fake_result(1, 10)
        self.assertEqual(self.post({'query': 'x'})[1]['citations'][0]['excerpt'], 'c' * 10)

    def test_invalid_query(self):  # Review Focus 4
        for q in ['   ', 7, None, 'x' * 501, '', ['a']]:
            status, body = self.post({'query': q})
            self.assertEqual((status, body['error']), (400, 'INVALID_QUERY'), q)
        self.assertEqual(self.post({})[1]['error'], 'INVALID_QUERY')
        self.assertEqual(self.post({'query': 'x' * 500})[0], 200)
        self.retriever.query.reset_mock()
        self.post({'query': 7})
        self.retriever.query.assert_not_called()

    def test_invalid_limit(self):
        for limit in [0, 11, -1, 'a', 2.5, True, None]:
            status, body = self.post({'query': 'x', 'limit': limit})
            self.assertEqual((status, body['error']), (400, 'INVALID_LIMIT'), limit)
        self.assertEqual(self.post({'query': 'x', 'limit': 10})[0], 200)
        self.assertEqual(self.post({'query': 'x', 'limit': 1})[0], 200)
        self.retriever.query.reset_mock()
        self.post({'query': 'x', 'limit': 0})
        self.retriever.query.assert_not_called()

    def test_invalid_json_and_category(self):
        for raw in [b'{', b'[]', b'"x"', b'']:
            status, body = self.post(None, raw=raw)
            self.assertEqual((status, body['error']), (400, 'INVALID_JSON'), raw)
        for category in [5, ['a'], {'a': 1}]:
            status, body = self.post({'query': 'x', 'category': category})
            self.assertEqual((status, body['error']), (400, 'INVALID_JSON'), category)
        self.retriever.query.assert_not_called()

    def test_content_type_required(self):
        for headers in [{'Content-Type': 'text/plain'}, {'Content-Type': 'application/x-www-form-urlencoded'}]:
            status, body = self.post({'query': 'x'}, headers=headers)
            self.assertEqual((status, body['error']), (415, 'JSON_REQUIRED'))
        self.assertEqual(self.post({'query': 'x'}, headers={'Content-Type': 'application/json; charset=utf-8'})[0], 200)
        self.retriever.query.assert_called_once()

    def test_auth_origin_and_space(self):
        request = lambda headers, path='/v1/retrievals': self.send('POST', path, b'{"query":"x"}', headers)
        json_headers = {'Content-Type': 'application/json', 'Origin': self.origin}
        status, body = request(json_headers)
        self.assertEqual((status, body['error']), (401, 'AUTH_REQUIRED'))
        status, body = request({**json_headers, 'Cookie': 'brain_session=invalido'})
        self.assertEqual((status, body['error']), (401, 'AUTH_REQUIRED'))
        status, body = request({**json_headers, 'Cookie': self.cookie, 'Origin': 'https://evil.example'})
        self.assertEqual((status, body['error']), (403, 'ORIGIN_DENIED'))
        no_origin = {'Content-Type': 'application/json', 'Cookie': self.cookie}
        self.assertEqual(request(no_origin)[1]['error'], 'ORIGIN_DENIED')
        status, body = request({**json_headers, 'Cookie': self.cookie, 'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual((status, body['error']), (403, 'ORIGIN_DENIED'))
        status, body = request({**json_headers, 'Cookie': self.cookie}, '/v1/retrievals?space=outro')
        self.assertEqual((status, body['error']), (403, 'SPACE_DENIED'))
        self.assertEqual(request({**json_headers, 'Cookie': self.cookie}, '/v1/retrievals?space=kiosk')[0], 200)
        self.retriever.query.assert_called_once()

    def test_envelope_space_comes_from_settings(self):  # revisao final: sem 'kiosk' fixo
        from config import settings
        with mock.patch.object(settings, 'space_id', 'acme'):
            status, body = self.post({'query': 'x'}, path='/v1/retrievals?space=acme')
            self.assertEqual((status, body['space_id']), (200, 'acme'))
            status, body = self.post({'query': 'x'})
            self.assertEqual((status, body['space_id']), (200, 'acme'))
            status, body = self.post({'query': 'x'}, path='/v1/retrievals?space=kiosk')
            self.assertEqual((status, body['error']), (403, 'SPACE_DENIED'))
            self.assertEqual(self.get('/v1/capabilities?space=acme')['space_id'], 'acme')
        self.assertEqual(self.retriever.query.call_count, 2)

    def test_unavailable_hides_exception(self):  # INV-N07
        self.retriever.query.side_effect = RuntimeError('C:\\segredo\\qdrant down')
        with mock.patch('sys.stderr'):
            status, body = self.post({'query': 'x'})
        self.assertEqual((status, body['error']), (503, 'RETRIEVAL_UNAVAILABLE'))
        self.assertNotIn('segredo', json.dumps(body))
        self.assertNotIn('qdrant', json.dumps(body))

    def test_unencodable_query_is_400_before_retriever(self):
        status, body = self.post(None, raw=b'{"query":"\\ud800"}')
        self.assertEqual((status, body['error']), (400, 'INVALID_QUERY'))
        self.retriever.query.assert_not_called()

    def test_unserializable_result_is_typed_503(self):
        for bad in [object(), '\ud800']:
            self.retriever.query.return_value = {**fake_result(), 'index_version': bad}
            with mock.patch('sys.stderr'):
                status, body = self.post({'query': 'x'})
            self.assertEqual((status, body['error']), (503, 'RETRIEVAL_UNAVAILABLE'))

    def test_misaligned_sources_is_typed_503(self):
        result = fake_result(2)
        result['sources'] = result['sources'][:1]
        self.retriever.query.return_value = result
        with mock.patch('sys.stderr'):
            status, body = self.post({'query': 'x'})
        self.assertEqual((status, body['error']), (503, 'RETRIEVAL_UNAVAILABLE'))

    def test_failure_detail_goes_to_log_not_response(self):
        self.retriever.query.side_effect = RuntimeError('C:\\segredo\\boom')
        with mock.patch('sys.stderr') as stderr:
            status, body = self.post({'query': 'x'})
        self.assertEqual(status, 503)
        self.assertNotIn('segredo', json.dumps(body))
        logged = ''.join(call.args[0] for call in stderr.write.call_args_list if call.args)
        self.assertIn('RuntimeError', logged)

    def test_lazy_construction_failure_is_503(self):
        handler = handler_for(self.store, Path(self.tmp.name), self.port)
        self.server.RequestHandlerClass = handler
        with mock.patch('core.retriever.BrainRetriever', side_effect=RuntimeError('C:\\segredo\\boom')), mock.patch('sys.stderr'):
            status, body = self.post({'query': 'x'})
        self.assertEqual((status, body['error']), (503, 'RETRIEVAL_UNAVAILABLE'))
        self.assertNotIn('segredo', json.dumps(body))

    def test_lazy_construction_happens_once(self):
        self.server.RequestHandlerClass = handler_for(self.store, Path(self.tmp.name), self.port)
        with mock.patch('core.retriever.BrainRetriever', return_value=self.retriever) as factory:
            self.assertEqual(self.post({'query': 'x'})[0], 200)
            self.assertEqual(self.post({'query': 'y'})[0], 200)
        factory.assert_called_once_with()

    def test_other_post_paths_still_read_only(self):
        self.assertEqual(self.post({'query': 'x'}, path='/v1/outro')[1]['error'], 'READ_ONLY_API')

    def test_capabilities_semantic_retrieval_true(self):
        self.assertTrue(self.get('/v1/capabilities')['semantic_retrieval'])


if __name__ == '__main__':
    unittest.main()
