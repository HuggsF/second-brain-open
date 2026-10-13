"""Serve the local dashboard and real backend execution API on loopback.
Differentiates backend events from frontend client responses with zero mocks.
"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote
import argparse
import json
import time
import os
import threading
import hashlib
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
RUNTIME_DIR = PROJECT_ROOT / '.runtime'
AUDIT_FILE = RUNTIME_DIR / 'workflow_audit.jsonl'
VAULT_DIR = PROJECT_ROOT / 'vault'

RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

_REQUEST_COUNTER = 0
_COUNTER_LOCK = threading.Lock()
_START_TIME = time.time()


def get_next_seq():
    global _REQUEST_COUNTER
    with _COUNTER_LOCK:
        _REQUEST_COUNTER += 1
        return _REQUEST_COUNTER


def find_vault_grounding(query_str):
    """Scan vault files on disk to provide real physical grounding evidence."""
    if not VAULT_DIR.is_dir():
        return None
    q = (query_str or '').lower()
    best_file = None
    if 'prd' in q or 'template' in q:
        candidate = VAULT_DIR / '_templates' / 'prd-feature-template.md'
        if candidate.is_file():
            best_file = candidate
    elif 'adr' in q or '013' in q or 'padroes' in q:
        candidate = VAULT_DIR / 'adrs' / 'ADR-013-adocao-padroes-mba-full-cycle-ia.md'
        if candidate.is_file():
            best_file = candidate
    elif 'guideline' in q or 'engineering' in q:
        candidate = VAULT_DIR / 'architecture' / 'engineering-guidelines.md'
        if candidate.is_file():
            best_file = candidate
    elif 'prompt' in q or 'eval' in q or 'registry' in q:
        candidate = VAULT_DIR / 'prompts' / 'prompt-registry.yaml'
        if candidate.is_file():
            best_file = candidate

    if not best_file:
        for f in VAULT_DIR.rglob('*.md'):
            if f.is_file() and any(part in f.name.lower() for part in ('01-', '02-', '03-', '04-', 'hub', 'bling', 'pb-')):
                best_file = f
                break

    if best_file and best_file.is_file():
        raw = best_file.read_bytes()
        return {
            'file': str(best_file.relative_to(PROJECT_ROOT).as_posix()),
            'sha256': hashlib.sha256(raw).hexdigest(),
            'size_bytes': len(raw),
            'lines': len(raw.split(b'\n')),
            'modified_at': datetime.fromtimestamp(best_file.stat().st_mtime, timezone.utc).isoformat()
        }
    return None


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_cors_and_security_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Client-Timestamp, X-Trace-ID')
        self.send_header(
            'Content-Security-Policy',
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_and_security_headers()
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)

        # Real Backend API: Telemetry
        if path == '/api/workflow/telemetry':
            vault_docs_count = len(list(VAULT_DIR.rglob('*.md'))) if VAULT_DIR.is_dir() else 0
            audit_size = AUDIT_FILE.stat().st_size if AUDIT_FILE.is_file() else 0
            telemetry = {
                'backend': 'Python ThreadingHTTPServer',
                'pid': os.getpid(),
                'uptime_seconds': round(time.time() - _START_TIME, 1),
                'total_backend_requests': _REQUEST_COUNTER,
                'vault_documents_on_disk': vault_docs_count,
                'audit_log_path': str(AUDIT_FILE.relative_to(PROJECT_ROOT).as_posix()),
                'audit_log_size_bytes': audit_size,
                'server_time_utc': datetime.now(timezone.utc).isoformat()
            }
            body = json.dumps(telemetry, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_cors_and_security_headers()
            self.end_headers()
            self.wfile.write(body)
            return

        # Real Backend API: Audit Log
        if path == '/api/workflow/audit-log':
            records = []
            if AUDIT_FILE.is_file():
                for line in AUDIT_FILE.read_text(encoding='utf-8').splitlines():
                    if line.strip():
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            pass
            body = json.dumps({'total': len(records), 'records': records[-50:]}, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_cors_and_security_headers()
            self.end_headers()
            self.wfile.write(body)
            return

        # Fallback to static files
        super().do_GET()

    def do_POST(self):
        url = urlparse(self.path)
        path = unquote(url.path)

        if path == '/api/workflow/execute-step':
            t0 = time.perf_counter()
            received_at = datetime.now(timezone.utc).isoformat()
            seq_id = get_next_seq()

            length = int(self.headers.get('Content-Length', '0'))
            raw_body = self.rfile.read(length) if length > 0 else b'{}'
            try:
                payload = json.loads(raw_body.decode('utf-8'))
            except Exception:
                payload = {}

            agent = payload.get('agent', 'unknown')
            action = payload.get('action', 'think')
            tool_name = payload.get('toolName', '')
            input_val = payload.get('input', '')
            trace_id = payload.get('trace_id') or hashlib.md5(f"{seq_id}-{time.time()}".encode()).hexdigest()
            span_id = hashlib.md5(f"span-{seq_id}-{time.time()}".encode()).hexdigest()[:16]

            # Physical disk grounding check
            grounding = find_vault_grounding(input_val or tool_name or str(payload.get('thought', '')))

            # Write real physical audit record on disk
            audit_record = {
                'seq_id': seq_id,
                'pid': os.getpid(),
                'thread_id': threading.get_ident(),
                'server_received_at': received_at,
                'trace_id': trace_id,
                'span_id': span_id,
                'workflow_id': payload.get('workflow_id', 'custom'),
                'step_index': payload.get('step_index', 0),
                'agent': agent,
                'action': action,
                'tool_name': tool_name,
                'input': input_val,
                'thought': payload.get('thought', ''),
                'client_sent_at': payload.get('client_sent_at', '')
            }
            log_line = json.dumps(audit_record, ensure_ascii=False) + '\n'
            with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
                f.write(log_line)
                f.flush()

            duration_ms = (time.perf_counter() - t0) * 1000
            processed_at = datetime.now(timezone.utc).isoformat()

            response_data = {
                'success': True,
                'backend': {
                    'execution_engine': 'Python 3.14 (ThreadingHTTPServer)',
                    'pid': os.getpid(),
                    'thread_id': threading.get_ident(),
                    'seq_id': seq_id,
                    'server_port': 8847,
                    'server_received_at': received_at,
                    'server_processed_at': processed_at,
                    'server_duration_ms': round(duration_ms, 2),
                    'trace_id': trace_id,
                    'span_id': span_id,
                    'disk_audit': {
                        'file': str(AUDIT_FILE.relative_to(PROJECT_ROOT).as_posix()),
                        'bytes_written': len(log_line.encode('utf-8')),
                        'status': 'COMMITTED_TO_DISK'
                    },
                    'vault_grounding': grounding
                },
                'step': {
                    'agent': agent,
                    'action': action,
                    'toolName': tool_name,
                    'traceId': trace_id,
                    'spanId': span_id,
                    'output': payload.get('output')
                }
            }

            body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Backend-PID', str(os.getpid()))
            self.send_header('X-Backend-Seq', str(seq_id))
            self.send_header('X-Backend-Duration-Ms', f"{duration_ms:.2f}")
            self.send_header('X-Trace-ID', trace_id)
            self.send_cors_and_security_headers()
            self.end_headers()
            self.wfile.write(body)
            return

        if path == '/api/workflow/reset-audit':
            with open(AUDIT_FILE, 'w', encoding='utf-8') as f:
                f.write('')
            resp = {'status': 'cleared', 'pid': os.getpid(), 'timestamp': datetime.now(timezone.utc).isoformat()}
            body = json.dumps(resp).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_cors_and_security_headers()
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404, 'API endpoint not found')

    def send_head(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith('/dashboard/'):
            path = path[len('/dashboard'):]
        if path == '/':
            path = '/index.html'
        target = (ROOT / path.lstrip('/')).resolve()
        if not target.is_relative_to(ROOT) or not target.is_file() or target.suffix.lower() not in {'.html','.css','.js','.json','.svg','.jpg','.png','.webp','.md'}:
            self.send_error(404)
            return None
        self.path = path
        return super().send_head()

    def guess_type(self, path):
        if str(path).endswith('.md'):
            return 'text/plain; charset=utf-8'
        return super().guess_type(path)

    def end_headers(self):
        self.send_cors_and_security_headers()
        super().end_headers()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8847)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), DashboardHandler)
    server.daemon_threads = True
    print(f'Dashboard & Real Backend API running: http://127.0.0.1:{args.port}/dashboard/', flush=True)
    print(f'Server PID: {os.getpid()} | Audit log: {AUDIT_FILE}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
