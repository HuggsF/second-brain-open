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
from config import settings  # noqa: E402
from backend.playbooks_api import PlaybooksApi  # noqa: E402,F401
from backend.workforce_api import WorkforceApi  # noqa: E402
from core.analytics_etl import get_emission_trends, get_error_analysis, get_throughput_analysis, get_logistics_health  # noqa: E402
from core.operational_rules import list_rules as list_operational_rules  # noqa: E402

STATIC_SUFFIXES = {'.html', '.css', '.js', '.json', '.svg', '.jpg', '.png', '.webp', '.md'}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
CSP_FRAMEABLE = CSP.replace("frame-ancestors 'none'", "frame-ancestors 'self'")


def make_handler(api, playbooks_api=None, workforce_api=None, directory=None):
    static_root = Path(directory) if directory else api.root / 'dashboard'

    class DashboardHandler(SimpleHTTPRequestHandler):
        frameable = False  # only files under dashboard/jev/ may be framed (by the dashboard itself)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_root), **kwargs)

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', CSP_FRAMEABLE if self.frameable else CSP)
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
                # Try playbooks API first (handles executions routes too)
                if playbooks_api and (path.startswith('/api/playbooks') or path == '/api/rules'):
                    result = playbooks_api.handle(path, method='GET', body=b'')
                    if result is not None:
                        status, payload = result
                        return self.send_json(status, payload)
                # Workforce API
                if workforce_api and path.startswith('/api/workforce/'):
                    result = workforce_api.handle('GET', path, b'')
                    if result is not None:
                        return self.send_json(*result)
                # Operational rules API
                if path == '/api/operational-rules':
                    return self._handle_operational_rules()
                # Analytics API
                if path.startswith('/api/analytics/'):
                    return self._handle_analytics(path)
                # Fall through to workflow API
                result = api.handle('GET', path, b'')
                return self.send_json(*result) if result else self.send_json(404, {'error': 'NOT_FOUND'})
            return super().do_GET()

        def do_POST(self):
            # Read the (bounded) body before any refusal: closing a socket with unread data makes
            # Windows reset it, and the client sees a network error instead of the status.
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                self.close_connection = True
                return self.send_json(400 if length < 0 else 413, {'error': 'INVALID_LENGTH' if length < 0 else 'BODY_TOO_LARGE'})
            body = self.rfile.read(length) if length > 0 else b''
            # No CORS: only the page served from this same origin may write the audit log.
            host = self.headers.get('Host', '')
            if not host or self.headers.get('Origin') not in (f'http://{host}',) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.send_json(403, {'error': 'ORIGIN_DENIED'})
            path = unquote(urlparse(self.path).path)
            # Playbooks POST (record execution) — no JSON content-type enforcement needed
            if playbooks_api and path.startswith('/api/playbooks'):
                result = playbooks_api.handle(path, method='POST', body=body)
                if result is not None:
                    status, payload = result
                    return self.send_json(status, payload)
            # Workforce API POST (refine demand via LLM)
            if workforce_api and path.startswith('/api/workforce/'):
                result = workforce_api.handle('POST', path, body)
                if result is not None:
                    return self.send_json(*result)
            if path == '/api/workflow/execute-step' and self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                return self.send_json(415, {'error': 'JSON_REQUIRED'})
            result = api.handle('POST', path, body)
            return self.send_json(*result) if result else self.send_json(404, {'error': 'NOT_FOUND'})

        def _handle_operational_rules(self):
            from urllib.parse import parse_qs
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            category = params.get('category', [None])[0]
            try:
                rules = list_operational_rules(category)
                return self.send_json(200, rules)
            except Exception as exc:
                return self.send_json(500, {'error': str(exc)})

        def _handle_analytics(self, path):
            from urllib.parse import parse_qs
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            endpoint = path.replace('/api/analytics/', '', 1)
            try:
                if endpoint.startswith('emission-trends'):
                    days = int(params.get('days', ['30'])[0])
                    return self.send_json(200, get_emission_trends(days))
                elif endpoint.startswith('error-analysis'):
                    days = int(params.get('days', ['14'])[0])
                    return self.send_json(200, get_error_analysis(days))
                elif endpoint.startswith('throughput'):
                    days = int(params.get('days', ['7'])[0])
                    return self.send_json(200, get_throughput_analysis(days))
                elif endpoint.startswith('logistics-health'):
                    days = int(params.get('days', ['14'])[0])
                    return self.send_json(200, get_logistics_health(days))
                else:
                    return self.send_json(404, {'error': 'ANALYTICS_ENDPOINT_NOT_FOUND'})
            except Exception as exc:
                return self.send_json(500, {'error': str(exc)})

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
            self.frameable = target.is_relative_to((static_root / 'jev').resolve())
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
    pb_api = PlaybooksApi(PROJECT_ROOT / 'vault')
    pb_count = len(pb_api._all_playbooks())
    wf_api = WorkforceApi(
        PROJECT_ROOT,
        ollama_url=settings.ollama_url,
        chat_model=settings.chat_model,
        qdrant_url=settings.qdrant_url,
        qdrant_collection=settings.qdrant_collection,
        embedding_model=settings.embedding_model,
    )
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(api, pb_api, wf_api, ROOT))
    server.daemon_threads = True
    print(f'Dashboard & Workflow API running: http://127.0.0.1:{args.port}/', flush=True)
    print(f'Server PID: {os.getpid()} | Audit log: {api.audit_file} | Playbooks: {pb_count}', flush=True)
    print(f'Workforce LLM: {settings.chat_model} @ {settings.ollama_url} | RAG: {settings.qdrant_collection} @ {settings.qdrant_url}', flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
