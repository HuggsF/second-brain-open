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
import re
import sys

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.workflow_api import MAX_BODY_BYTES, WorkflowApi  # noqa: E402

STATIC_SUFFIXES = {'.html', '.css', '.js', '.json', '.svg', '.jpg', '.png', '.webp', '.md'}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")


# ── Playbooks API ─────────────────────────────────────────────────────────────

def _parse_frontmatter(text):
    """Extract YAML-like frontmatter dict from a markdown file."""
    meta = {}
    if not text.startswith('---'):
        return meta
    end = text.find('\n---', 3)
    if end == -1:
        return meta
    for line in text[3:end].splitlines():
        if ':' not in line:
            continue
        key, _, val = line.partition(':')
        key, val = key.strip(), val.strip()
        if val.startswith('[') and val.endswith(']'):
            val = [v.strip().strip("'\"") for v in val[1:-1].split(',') if v.strip()]
        meta[key] = val
    return meta


class PlaybooksApi:
    """Serves vault/playbooks/*.md as a simple REST API."""

    def __init__(self, vault_dir: Path):
        self.playbooks_dir = vault_dir / 'playbooks'
        self.root = vault_dir.parent  # project root (parent of vault/)

    def _all_playbooks(self):
        """Return sorted list of playbook metadata dicts."""
        if not self.playbooks_dir.is_dir():
            return []
        results = []
        for f in sorted(self.playbooks_dir.glob('*.md')):
            try:
                text = f.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            meta = _parse_frontmatter(text)
            pb_id = meta.get('id') or f.stem.split('-')[0].upper() + '-' + f.stem.split('-')[1] if '-' in f.stem else f.stem
            results.append({
                'id': meta.get('id', f.stem),
                'title': meta.get('title', f.stem),
                'status': meta.get('status', 'draft'),
                'validates': meta.get('validates', []),
                'environment': meta.get('environment', ''),
                'targets': meta.get('targets', []),
                'filename': f.name,
            })
        return results

    # ── JEV helpers ───────────────────────────────────────────────────────────

    def _executions(self, playbook_id=None):
        """Read executions from seed-executions.json + evidence.db SQLite."""
        results = []
        # 1. Seed JSON
        seed_path = self.root / 'evidence' / 'seed-executions.json'
        if seed_path.exists():
            try:
                for entry in json.loads(seed_path.read_text(encoding='utf-8')):
                    if not playbook_id or entry.get('playbook_id') == playbook_id:
                        results.append({**entry, '_origin': 'seed'})
            except Exception:
                pass
        # 2. SQLite evidence.db
        db_path = self.root / '.runtime' / 'evidence.db'
        if db_path.exists():
            try:
                import sqlite3 as _sq
                with _sq.connect(str(db_path)) as conn:
                    conn.row_factory = _sq.Row
                    if playbook_id:
                        rows = conn.execute(
                            'SELECT * FROM executions WHERE playbook_id=? ORDER BY ts DESC LIMIT 50',
                            (playbook_id,),
                        )
                    else:
                        rows = conn.execute(
                            'SELECT * FROM executions ORDER BY ts DESC LIMIT 200'
                        )
                    results.extend([{**dict(r), '_origin': 'db'} for r in rows])
            except Exception:
                pass
        # Deduplicate by import_key (seed entries already in the DB)
        seen = set()
        unique = []
        for item in results:
            key = item.get('import_key') or id(item)
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

    def _record_execution(self, body_bytes):
        """Write a new execution to evidence.db via raw SQL."""
        try:
            payload = json.loads(body_bytes.decode('utf-8'))
        except Exception:
            return 400, {'error': 'INVALID_JSON'}
        required = ('playbook_id', 'result', 'environment', 'summary')
        for field in required:
            if not payload.get(field):
                return 400, {'error': 'MISSING_FIELD', 'field': field}
        valid_results = ('pass', 'fail', 'error', 'skipped')
        valid_envs = ('hml', 'production', 'local')
        if payload['result'] not in valid_results:
            return 400, {'error': 'INVALID_RESULT', 'valid': list(valid_results)}
        if payload['environment'] not in valid_envs:
            return 400, {'error': 'INVALID_ENVIRONMENT', 'valid': list(valid_envs)}
        db_path = self.root / '.runtime' / 'evidence.db'
        if not db_path.exists():
            return 503, {'error': 'DB_NOT_FOUND'}
        try:
            import sqlite3 as _sq
            import datetime as _dt
            ts = _dt.datetime.now().astimezone().isoformat()
            with _sq.connect(str(db_path)) as conn:
                conn.execute(
                    """INSERT INTO executions
                       (playbook_id, ts, result, environment, evidence_ref, summary,
                        trace_id, task_label, source, recorded_by)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        payload['playbook_id'], ts, payload['result'],
                        payload['environment'], payload.get('evidence_ref', ''),
                        payload['summary'], payload.get('trace_id', ''),
                        payload.get('task_label', ''), payload.get('source', 'dashboard'),
                        payload.get('recorded_by', 'user'),
                    ),
                )
                row_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            return 201, {'id': row_id, 'ts': ts, 'status': 'recorded'}
        except Exception as exc:
            return 500, {'error': 'DB_WRITE_FAILED', 'detail': str(exc)}

    # ── Routing ───────────────────────────────────────────────────────────────

    def handle(self, path, method='GET', body=b''):
        """Return (status, payload) or None if path doesn't match."""
        # POST /api/playbooks/executions — register a new execution
        if method == 'POST' and path == '/api/playbooks/executions':
            return self._record_execution(body)

        # GET /api/playbooks/ — list all playbooks
        if path == '/api/playbooks/' or path == '/api/playbooks':
            return 200, {'playbooks': self._all_playbooks()}

        # GET /api/playbooks/executions — all executions (JEV global view)
        if path == '/api/playbooks/executions':
            return 200, {'executions': self._executions()}

        # GET /api/playbooks/{id}/executions — executions for one playbook
        m_exec = re.match(r'^/api/playbooks/([A-Za-z0-9_\-\.]+)/executions$', path)
        if m_exec:
            pb_id = unquote(m_exec.group(1))
            return 200, {'executions': self._executions(pb_id)}

        # GET /api/playbooks/{id} — single playbook content
        m = re.match(r'^/api/playbooks/([A-Za-z0-9_\-\.]+)$', path)
        if m:
            pb_id = unquote(m.group(1))
            if not self.playbooks_dir.is_dir():
                return 404, {'error': 'VAULT_NOT_FOUND'}
            # Find by id frontmatter or by filename prefix
            for f in sorted(self.playbooks_dir.glob('*.md')):
                try:
                    text = f.read_text(encoding='utf-8', errors='replace')
                except OSError:
                    continue
                meta = _parse_frontmatter(text)
                fid = meta.get('id', f.stem)
                if fid.upper() == pb_id.upper() or f.stem.upper().startswith(pb_id.upper()):
                    return 200, {
                        'id': fid,
                        'filename': f.name,
                        'content': text,
                        'meta': meta,
                    }
            return 404, {'error': 'NOT_FOUND', 'id': pb_id}

        return None


def make_handler(api, playbooks_api=None, directory=None):
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
                # Try playbooks API first (handles executions routes too)
                if playbooks_api and path.startswith('/api/playbooks'):
                    result = playbooks_api.handle(path, method='GET', body=b'')
                    if result is not None:
                        status, payload = result
                        return self.send_json(status, payload)
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
    pb_api = PlaybooksApi(PROJECT_ROOT / 'vault')
    pb_count = len(pb_api._all_playbooks())
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(api, pb_api, ROOT))
    server.daemon_threads = True
    print(f'Dashboard & Workflow API running: http://127.0.0.1:{args.port}/', flush=True)
    print(f'Server PID: {os.getpid()} | Audit log: {api.audit_file} | Playbooks: {pb_count}', flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
