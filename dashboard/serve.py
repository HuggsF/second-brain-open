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
from config import settings  # noqa: E402
from core import evidence  # noqa: E402
from core.evidence_store import EvidenceStore, EvidenceStoreError  # noqa: E402

STATIC_SUFFIXES = {'.html', '.css', '.js', '.json', '.svg', '.jpg', '.png', '.webp', '.md'}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")


# ── Playbooks API ─────────────────────────────────────────────────────────────

class PlaybooksApi:
    """Serves vault/playbooks/*.md as a simple REST API.

    Uses core.evidence as the single source of truth for playbook definitions,
    and core.evidence_store.EvidenceStore for reading/writing execution records.
    This eliminates the local _parse_frontmatter duplicate (IC-3).
    """

    def __init__(self, vault_dir: Path):
        self.vault_dir = vault_dir
        self.root = vault_dir.parent  # project root (parent of vault/)
        self._defs_cache: object = None  # lazily loaded definitions

    def _load_defs(self):
        """Load or return cached playbook definitions from core.evidence."""
        if self._defs_cache is None:
            self._defs_cache = evidence.load_definitions(self.vault_dir)
        return self._defs_cache

    def _store(self) -> EvidenceStore:
        """Open the EvidenceStore (creates DB if needed)."""
        db_path = self.root / '.runtime' / 'evidence.db'
        return EvidenceStore(path=db_path)

    def _all_playbooks(self):
        """Return sorted list of playbook metadata dicts using core.evidence definitions."""
        defs = self._load_defs()
        results = []
        for pb in sorted(defs.playbooks.values(), key=lambda p: p.id):
            # Also append filename by finding the file in vault/playbooks/
            filename = Path(pb.path).name
            results.append({
                'id': pb.id,
                'title': pb.title,
                'status': pb.status,
                'validates': pb.validates,
                'environment': pb.environment,
                'targets': pb.targets,
                'filename': filename,
            })
        return results

    # ── JEV helpers ───────────────────────────────────────────────────────────

    def _executions(self, playbook_id=None):
        """Read executions from seed-executions.json + EvidenceStore."""
        results = []
        # 1. Seed JSON (historical executions imported at startup)
        seed_path = self.root / 'evidence' / 'seed-executions.json'
        if seed_path.exists():
            try:
                for entry in json.loads(seed_path.read_text(encoding='utf-8')):
                    if not playbook_id or entry.get('playbook_id') == playbook_id:
                        results.append({**entry, '_origin': 'seed'})
            except Exception:
                pass
        # 2. EvidenceStore (SQLite via domain layer — eliminates raw SQL, IC-3)
        try:
            store = self._store()
            if playbook_id:
                rows = store.latest(playbook_id, limit=50)
            else:
                # No direct "all" method — iterate over known playbook IDs
                defs = self._load_defs()
                rows = []
                for pb_id in sorted(defs.playbooks):
                    rows.extend(store.latest(pb_id, limit=20))
                # Sort all rows by ts descending, keep top 200
                rows = sorted(rows, key=lambda r: r.get('ts', ''), reverse=True)[:200]
            results.extend([{**r, '_origin': 'db'} for r in rows])
        except EvidenceStoreError:
            pass
        # Deduplicate by import_key (seed entries already in the DB)
        seen: set = set()
        unique = []
        for item in results:
            key = item.get('import_key') or id(item)
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

    def _record_execution(self, body_bytes: bytes):
        """Validate and write a new execution via core.evidence + EvidenceStore (IC-3)."""
        try:
            payload = json.loads(body_bytes.decode('utf-8'))
        except Exception:
            return 400, {'error': 'INVALID_JSON'}
        # Required fields check
        required = ('playbook_id', 'result', 'environment', 'summary')
        for field in required:
            if not payload.get(field):
                return 400, {'error': 'MISSING_FIELD', 'field': field}
        # Load definitions (fresh load to pick up any new playbooks added since startup)
        defs = self._load_defs()
        # Delegate validation to domain layer
        clean, error = evidence.validate_execution(
            defs,
            playbook_id=payload['playbook_id'],
            result=payload['result'],
            summary=payload['summary'],
            evidence_ref=payload.get('evidence_ref', ''),
            environment=payload['environment'],
        )
        if error:
            return 400, {'error': 'VALIDATION_FAILED', 'detail': error}
        # Write via EvidenceStore (domain layer — no raw SQL)
        try:
            store = self._store()
            row_id = store.record(
                playbook_id=payload['playbook_id'],
                result=payload['result'],
                environment=payload['environment'],
                evidence_ref=clean['evidence_ref'],
                summary=clean['summary'],
                trace_id=payload.get('trace_id') or None,
                task_label=payload.get('task_label') or None,
                source=payload.get('source', 'dashboard'),
                recorded_by=payload.get('recorded_by', 'user'),
            )
        except EvidenceStoreError as exc:
            return 503, {'error': 'DB_UNAVAILABLE', 'detail': str(exc)}
        if row_id is None:
            return 409, {'error': 'DUPLICATE_IMPORT_KEY'}
        # Invalidate definitions cache so next GET picks up any schema changes
        self._defs_cache = None
        from core import tracing
        return 201, {'id': row_id, 'ts': tracing.now_iso(), 'status': 'recorded'}

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
            pb_id = unquote(m.group(1)).upper()
            defs = self._load_defs()
            pb = defs.playbooks.get(pb_id)
            if pb is None:
                # Fallback: try prefix match
                for k, v in defs.playbooks.items():
                    if k.upper().startswith(pb_id):
                        pb = v
                        break
            if pb is None:
                return 404, {'error': 'NOT_FOUND', 'id': pb_id}
            # Read raw content for markdown rendering
            pb_path = self.vault_dir / pb.path
            try:
                content = pb_path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                content = ''
            return 200, {
                'id': pb.id,
                'filename': Path(pb.path).name,
                'content': content,
                'meta': {
                    'id': pb.id,
                    'title': pb.title,
                    'status': pb.status,
                    'validates': pb.validates,
                    'environment': pb.environment,
                    'targets': pb.targets,
                },
            }

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
