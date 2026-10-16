import http.client
import json
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest import mock

from backend.server import handler_for
from backend.store import Store
from core import events
import asyncio
from core import broker
from core.tools import IMPLEMENTATIONS


def read_sse_message(res, max_lines=10):
    """Read lines until empty line (end of SSE event) or limit reached."""
    lines = []
    for _ in range(max_lines):
        line = res.readline()
        if not line:
            break
        text = line.decode('utf-8').rstrip('\r\n')
        if not text and lines:
            break
        if text:
            lines.append(text)
    return lines


def parse_sse_event(lines):
    """Parse SSE raw lines into structured dict."""
    event_id = None
    data_parts = []
    is_comment = False
    for line in lines:
        if line.startswith(':'):
            is_comment = True
        elif line.startswith('id:'):
            event_id = line[3:]
        elif line.startswith('data:'):
            data_parts.append(line[5:])
    data_str = '\n'.join(data_parts)
    data = None
    if data_str:
        try:
            data = json.loads(data_str)
        except Exception:
            data = data_str
    return {'id': event_id, 'data': data, 'is_comment': is_comment, 'raw': lines}


def read_next_event(res, max_attempts=5):
    """Read next SSE event ignoring keepalive comments."""
    for _ in range(max_attempts):
        lines = read_sse_message(res)
        parsed = parse_sse_event(lines)
        if not parsed['is_comment'] and parsed['data'] is not None:
            return parsed
    return None


class _QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass


class TestSSEEvents(unittest.TestCase):
    server = None
    thread = None
    store = None
    token = None
    port = None
    base_url = None
    tmp_dir = None

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(cls.tmp_dir.name) / 'brain.db'
        cls.store = Store(db_path)
        cls.token = cls.store.issue('session', 3600)
        dashboard = Path(__file__).resolve().parent.parent / 'dashboard'

        cls.server = _QuietServer(('127.0.0.1', 0), None)
        cls.port = cls.server.server_port
        cls.server.RequestHandlerClass = handler_for(cls.store, dashboard, cls.port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f'http://127.0.0.1:{cls.port}'

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
        if cls.tmp_dir:
            cls.tmp_dir.cleanup()
        if hasattr(events, 'SSE_SUBSCRIBERS'):
            with getattr(events, '_sub_lock', threading.Lock()):
                events.SSE_SUBSCRIBERS.clear()

    def tearDown(self):
        if hasattr(events, 'SSE_SUBSCRIBERS'):
            with getattr(events, '_sub_lock', threading.Lock()):
                events.SSE_SUBSCRIBERS.clear()

    def test_sse_without_session_returns_401(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request('GET', '/v1/events')
            res = conn.getresponse()
            self.assertEqual(res.status, 401)
            body = json.loads(res.read().decode('utf-8'))
            self.assertEqual(body.get('error'), 'AUTH_REQUIRED')
        finally:
            conn.close()

    def test_sse_with_session_returns_200(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request('GET', '/v1/events', headers={'Cookie': f'brain_session={self.token}'})
            res = conn.getresponse()
            self.assertEqual(res.status, 200)
            self.assertIn('text/event-stream', res.getheader('Content-Type', ''))
            self.assertEqual(res.getheader('Cache-Control'), 'no-cache')
            self.assertEqual(res.getheader('Connection'), 'keep-alive')
            self.assertEqual(res.getheader('X-Accel-Buffering'), 'no')
        finally:
            conn.close()

    def test_subscribe_and_unsubscribe_lifecycle(self):
        q = events.subscribe()
        self.assertIn(q, events.SSE_SUBSCRIBERS)
        events.unsubscribe(q)
        self.assertNotIn(q, events.SSE_SUBSCRIBERS)

    def test_sse_fan_out_to_multiple_subscribers(self):
        conn1 = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn2 = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn1.request('GET', '/v1/events', headers={'Cookie': f'brain_session={self.token}'})
            res1 = conn1.getresponse()
            conn2.request('GET', '/v1/events', headers={'Cookie': f'brain_session={self.token}'})
            res2 = conn2.getresponse()

            self.assertEqual(res1.status, 200)
            self.assertEqual(res2.status, 200)

            test_event = {
                "id": "evt-fanout-1",
                "task": "classify",
                "payload": {
                    "text": "confidential data",
                    "labels": {"type": "adr", "team": "ops", "tag": "secret"},
                },
            }
            events.publish(test_event)

            parsed1 = read_next_event(res1)
            parsed2 = read_next_event(res2)

            self.assertIsNotNone(parsed1)
            self.assertIsNotNone(parsed2)
            self.assertEqual(parsed1['id'], 'evt-fanout-1')
            self.assertEqual(parsed2['id'], 'evt-fanout-1')
            self.assertNotIn('payload', parsed1['data'])
            self.assertNotIn('confidential data', json.dumps(parsed1['data']))
            self.assertEqual(parsed1['data']['labels'], {'type': 'adr', 'team': 'ops'})
            self.assertIn('payload_bytes', parsed1['data'])
        finally:
            conn1.close()
            conn2.close()

    def test_sse_keepalive_on_idle(self):
        with mock.patch('backend.server.SSE_KEEPALIVE_SECONDS', 0.2):
            conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
            try:
                conn.request('GET', '/v1/events', headers={'Cookie': f'brain_session={self.token}'})
                res = conn.getresponse()
                self.assertEqual(res.status, 200)
                lines = read_sse_message(res)
                parsed = parse_sse_event(lines)
                self.assertTrue(parsed['is_comment'])
                self.assertIn(': keepalive', lines)
            finally:
                conn.close()

    def test_sse_client_disconnect_cleans_up(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('GET', '/v1/events', headers={'Cookie': f'brain_session={self.token}'})
        res = conn.getresponse()
        self.assertEqual(res.status, 200)
        self.assertEqual(len(events.SSE_SUBSCRIBERS), 1)
        active_sub = next(iter(events.SSE_SUBSCRIBERS))

        # Close client socket with RST to simulate abrupt client disconnect
        sock = getattr(getattr(res, 'fp', None), 'raw', None)
        raw_sock = getattr(sock, '_sock', None)
        if raw_sock:
            raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            raw_sock.close()
        res.close()
        conn.close()

        # Send an event so server thread wakes up from sub.get(), writes, fails and triggers cleanup
        events.publish({"id": "wake-disconnect", "task": "test"})

        # Wait for server thread to detect disconnect and unsubscribe
        cleaned = False
        for _ in range(20):
            time.sleep(0.05)
            if active_sub not in events.SSE_SUBSCRIBERS:
                cleaned = True
                break
        self.assertTrue(cleaned, "Subscriber queue was not cleaned up after client disconnect")

    def test_events_publish_slow_subscriber_dropped(self):
        q = events.subscribe()
        try:
            for i in range(256):
                q.put_nowait({"id": str(i)})
            self.assertTrue(q.full())
            events.publish({"id": "overflow"})
            self.assertNotIn(q, events.SSE_SUBSCRIBERS)
        finally:
            events.unsubscribe(q)

    def test_broker_tool_start_published_to_sse(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request('GET', '/v1/events', headers={'Cookie': f'brain_session={self.token}'})
            res = conn.getresponse()
            self.assertEqual(res.status, 200)

            async def fake_adr(**kwargs):
                return {"adr": "ADR-001 content"}

            with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": fake_adr}):
                asyncio.run(broker.call("agent:researcher", "get_adr", {"identifier": "ADR-001"}))

            evt = read_next_event(res)
            self.assertIsNotNone(evt)
            data = evt['data']
            self.assertEqual(data.get('type'), 'tool.start')
            self.assertEqual(data.get('channel'), 'tool')
            self.assertEqual(data.get('tool_name'), 'get_adr')
            self.assertEqual(data.get('status'), 'start')
            self.assertIn('payload_bytes', data)
            self.assertNotIn('payload', data)
        finally:
            conn.close()

    def test_broker_tool_end_published_to_sse(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request('GET', '/v1/events', headers={'Cookie': f'brain_session={self.token}'})
            res = conn.getresponse()
            self.assertEqual(res.status, 200)

            async def fake_adr(**kwargs):
                return {"adr": "ADR-001 content"}

            with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": fake_adr}):
                asyncio.run(broker.call("agent:researcher", "get_adr", {"identifier": "ADR-001"}))

            # First event is start
            start_evt = read_next_event(res)
            self.assertEqual(start_evt['data'].get('type'), 'tool.start')

            # Second event is end
            end_evt = read_next_event(res)
            self.assertIsNotNone(end_evt)
            data = end_evt['data']
            self.assertEqual(data.get('type'), 'tool.end')
            self.assertEqual(data.get('channel'), 'tool')
            self.assertEqual(data.get('tool_name'), 'get_adr')
            self.assertEqual(data.get('status'), 'end')
            self.assertIn('duration_ms', data)
            self.assertIsInstance(data['duration_ms'], int)
            self.assertIn('payload_bytes', data)
            self.assertNotIn('payload', data)
        finally:
            conn.close()

    def test_broker_tool_denied_published_to_sse(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request('GET', '/v1/events', headers={'Cookie': f'brain_session={self.token}'})
            res = conn.getresponse()
            self.assertEqual(res.status, 200)

            asyncio.run(broker.call("agent:researcher", "read_vault_file", {}))

            evt = read_next_event(res)
            self.assertIsNotNone(evt)
            data = evt['data']
            self.assertEqual(data.get('type'), 'tool.denied')
            self.assertEqual(data.get('channel'), 'tool')
            self.assertEqual(data.get('tool_name'), 'read_vault_file')
            self.assertEqual(data.get('status'), 'denied')
            self.assertIn('reason', data)
            self.assertNotIn('payload', data)
        finally:
            conn.close()

    def test_broker_tool_timeout_published_to_sse(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request('GET', '/v1/events', headers={'Cookie': f'brain_session={self.token}'})
            res = conn.getresponse()
            self.assertEqual(res.status, 200)

            def fake_wait_for(fut, timeout=None):
                fut.close()
                raise asyncio.TimeoutError()

            with mock.patch("asyncio.wait_for", side_effect=fake_wait_for):
                asyncio.run(broker.call("agent:researcher", "get_adr", {"identifier": "A"}))

            # First event is start
            start_evt = read_next_event(res)
            self.assertEqual(start_evt['data'].get('type'), 'tool.start')

            # Second event is timeout
            timeout_evt = read_next_event(res)
            self.assertIsNotNone(timeout_evt)
            data = timeout_evt['data']
            self.assertEqual(data.get('type'), 'tool.timeout')
            self.assertEqual(data.get('channel'), 'tool')
            self.assertEqual(data.get('tool_name'), 'get_adr')
            self.assertEqual(data.get('status'), 'timeout')
            self.assertIn('duration_ms', data)
            self.assertNotIn('payload', data)
        finally:
            conn.close()

    def test_tool_events_are_redacted(self):
        q = events.subscribe()
        try:
            secret_token = "ghp_supersecret123456789012345"
            async def fake_tool(**kwargs):
                return {"result": "ok", "leaked": secret_token}

            with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": fake_tool}):
                asyncio.run(broker.call("agent:researcher", "get_adr", {"secret": secret_token}))

            evts = []
            while not q.empty():
                evts.append(q.get_nowait())

            self.assertGreaterEqual(len(evts), 2)
            for evt in evts:
                self.assertNotIn('payload', evt)
                self.assertIn('payload_bytes', evt)
                self.assertIsInstance(evt['payload_bytes'], int)
                serialized = json.dumps(evt)
                self.assertNotIn(secret_token, serialized)
        finally:
            events.unsubscribe(q)


if __name__ == '__main__':
    unittest.main()
