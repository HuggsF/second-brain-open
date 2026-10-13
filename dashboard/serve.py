"""Serve the dashboard and the Workflow Studio API on loopback, without a session.

For local development only. The BFF (python -m backend.server) serves the same dashboard and the
same /api/workflow/* routes behind a session, plus /v1/* for observability.
"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.workflow_api import MAX_BODY_BYTES, WorkflowApi  # noqa: E402

STATIC_SUFFIXES = {'.html', '.css', '.js', '.json', '.svg', '.jpg', '.png', '.webp', '.md'}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")


def make_handler(api, directory=None):
    static_root = Path(directory) if directory else api.root / 'dashboard'

    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_root), **kwargs)

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', CSP)
            super().end_headers()

        def send_json(self, status, payload, headers=None):
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_json(405, {'error': 'METHOD_NOT_ALLOWED'})

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path.startswith('/api/'):
                result = api.handle('GET', path, b'')
                return self.send_json(*result) if result else self.send_json(404, {'error': 'NOT_FOUND'})
            return super().do_GET()

        def do_POST(self):
            # No CORS: only the page served from this same origin may write the audit log.
            host = self.headers.get('Host', '')
            if not host or self.headers.get('Origin') not in (f'http://{host}',) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.send_json(403, {'error': 'ORIGIN_DENIED'})
            path = unquote(urlparse(self.path).path)
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self.send_json(400, {'error': 'INVALID_LENGTH'})
            if length > MAX_BODY_BYTES:
                return self.send_json(413, {'error': 'BODY_TOO_LARGE'})
            body = self.rfile.read(length) if length > 0 else b''
            if path == '/api/workflow/execute-step' and self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                return self.send_json(415, {'error': 'JSON_REQUIRED'})
            result = api.handle('POST', path, body)
            return self.send_json(*result) if result else self.send_json(404, {'error': 'NOT_FOUND'})

        def send_head(self):
            path = unquote(urlparse(self.path).path)
            if path.startswith('/dashboard/'):
                path = path[len('/dashboard'):]
            if path == '/':
                path = '/index.html'
            target = (static_root / path.lstrip('/')).resolve()
            if not target.is_relative_to(static_root.resolve()) or not target.is_file() or target.suffix.lower() not in STATIC_SUFFIXES:
                self.send_error(404)
                return None
            self.path = path
            return super().send_head()

        def guess_type(self, path):
            if str(path).endswith('.md'):
                return 'text/plain; charset=utf-8'
            return super().guess_type(path)

    return DashboardHandler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8847)
    args = parser.parse_args()
    api = WorkflowApi(PROJECT_ROOT, port=args.port)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(api, ROOT))
    server.daemon_threads = True
    print(f'Dashboard & Workflow API running: http://127.0.0.1:{args.port}/', flush=True)
    print(f'Server PID: {os.getpid()} | Audit log: {api.audit_file}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
