"""Playbooks and rules REST API, shared by the dev dashboard server and the BFF."""
from pathlib import Path
from urllib.parse import unquote
import json
import re

from core import evidence
from core.evidence_store import EvidenceStore, EvidenceStoreError


DB_UNAVAILABLE_DETAIL = 'evidence database unavailable'


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
                'kind': pb.kind,
                'ttl_hours': pb.ttl_hours,
                'targets': pb.targets,
                'params': getattr(pb, 'params', []),
                'filename': filename,
            })
        return results

    def rules(self):
        """One row per rule with its test light (fresh definitions; may raise EvidenceStoreError)."""
        return evidence.list_rules(evidence.load_definitions(self.vault_dir), self._store())

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
        if not isinstance(payload, dict):
            return 400, {'error': 'INVALID_JSON'}
        # Required fields check
        required = ('playbook_id', 'result', 'environment', 'summary')
        for field in required:
            if not payload.get(field):
                return 400, {'error': 'MISSING_FIELD', 'field': field}
        for field in ('trace_id', 'task_label', 'source', 'recorded_by'):
            if payload.get(field) is not None and not isinstance(payload[field], str):
                return 400, {'error': 'VALIDATION_FAILED', 'detail': f'{field} must be text'}
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
            commit_sha=payload.get('commit_sha'),
            run_id=payload.get('run_id'),
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
                source=payload.get('source') or 'dashboard',
                recorded_by=payload.get('recorded_by') or 'user',
                commit_sha=clean['commit_sha'],
                run_id=clean['run_id'],
            )
        except EvidenceStoreError as exc:
            return 503, {'error': 'DB_UNAVAILABLE', 'detail': DB_UNAVAILABLE_DETAIL}
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

        # GET /api/rules — every rule with its test light
        if method == 'GET' and path == '/api/rules':
            try:
                return 200, {'rules': self.rules()}
            except EvidenceStoreError as exc:
                return 503, {'error': 'DB_UNAVAILABLE', 'detail': DB_UNAVAILABLE_DETAIL}

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
                    'kind': pb.kind,
                    'ttl_hours': pb.ttl_hours,
                    'targets': pb.targets,
                    'params': getattr(pb, 'params', []),
                },
            }

        # POST /api/playbooks/{id}/render — render playbook markdown with liquid params
        m_render = re.match(r'^/api/playbooks/([A-Za-z0-9_\-\.]+)/render$', path)
        if method == 'POST' and m_render:
            pb_id = unquote(m_render.group(1)).upper()
            defs = self._load_defs()
            pb = defs.playbooks.get(pb_id)
            if pb is None:
                for k, v in defs.playbooks.items():
                    if k.upper().startswith(pb_id):
                        pb = v
                        break
            if pb is None:
                return 404, {'error': 'NOT_FOUND', 'id': pb_id}
            try:
                payload = json.loads(body.decode('utf-8')) if body else {}
            except Exception:
                return 400, {'error': 'INVALID_JSON'}
            if not isinstance(payload, dict):
                return 400, {'error': 'INVALID_JSON'}
            params = payload.get('params', {})
            pb_path = self.vault_dir / pb.path
            try:
                raw_content = pb_path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                raw_content = ''
            from core import liquid
            rendered = liquid.render_liquid(raw_content, params)
            return 200, {
                'id': pb.id,
                'rendered_content': rendered,
                'params_used': params,
            }

        return None
