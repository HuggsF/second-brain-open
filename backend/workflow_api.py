"""Workflow Studio API (/api/workflow/*) shared by the BFF and dashboard/serve.py.

Records each step the dashboard runs in an append-only JSONL audit file and grounds it in a vault
note on disk. It executes nothing: agent steps are scripted in the front-end.
"""
import hashlib
import json
import os
import platform
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_BODY_BYTES = 64 * 1024
GET_ROUTES = ('/api/workflow/telemetry', '/api/workflow/audit-log')
POST_ROUTES = ('/api/workflow/execute-step', '/api/workflow/reset-audit')
GROUNDING = (
    (('prd', 'template'), ('_templates', 'prd-feature-template.md')),
    (('adr', '013', 'padroes'), ('adrs', 'ADR-013-adocao-padroes-mba-full-cycle-ia.md')),
    (('guideline', 'engineering'), ('architecture', 'engineering-guidelines.md')),
    (('prompt', 'eval', 'registry'), ('prompts', 'prompt-registry.yaml')),
)


def _now():
    return datetime.now(timezone.utc).isoformat()


class WorkflowApi:
    def __init__(self, project_root, audit_file=None, port=None):
        self.root = Path(project_root)
        self.vault = self.root / 'vault'
        self.audit_file = Path(audit_file) if audit_file else self.root / '.runtime' / 'workflow_audit.jsonl'
        self.port = port
        self.started = time.time()
        self.requests = 0
        self.lock = threading.Lock()

    def handle(self, method, path, body):
        """Return (status, payload, headers) for a workflow route, or None when the path is not one."""
        if path not in GET_ROUTES + POST_ROUTES:
            return None
        if (method == 'GET') != (path in GET_ROUTES):
            return 405, {'error': 'METHOD_NOT_ALLOWED'}, {}
        if path == '/api/workflow/telemetry':
            return 200, self.telemetry(), {}
        if path == '/api/workflow/audit-log':
            return 200, self.audit_log(), {}
        if path == '/api/workflow/reset-audit':
            return 200, self.reset_audit(), {}
        if len(body) > MAX_BODY_BYTES:
            return 413, {'error': 'BODY_TOO_LARGE'}, {}
        try:
            payload = json.loads(body.decode('utf-8') or '{}')
        except (UnicodeDecodeError, ValueError):
            return 400, {'error': 'INVALID_JSON'}, {}
        if not isinstance(payload, dict):
            return 400, {'error': 'INVALID_JSON'}, {}
        return self.execute_step(payload)

    def grounding(self, query):
        """Pick a vault file that matches the step and return its on-disk identity."""
        if not self.vault.is_dir():
            return None
        q = (query or '').lower()
        best = next((self.vault.joinpath(*rel) for words, rel in GROUNDING if any(w in q for w in words)), None)
        if not best or not best.is_file():
            best = next((f for f in sorted(self.vault.rglob('*.md')) if f.is_file()), None)
        if not best:
            return None
        raw = best.read_bytes()
        return {
            'file': best.relative_to(self.root).as_posix(),
            'sha256': hashlib.sha256(raw).hexdigest(),
            'size_bytes': len(raw),
            'lines': len(raw.split(b'\n')),
            'modified_at': datetime.fromtimestamp(best.stat().st_mtime, timezone.utc).isoformat(),
        }

    def _audit_path(self):
        return self.audit_file.relative_to(self.root).as_posix() if self.audit_file.is_relative_to(self.root) else self.audit_file.name

    def telemetry(self):
        return {
            'backend': f'Python {platform.python_version()} (ThreadingHTTPServer)',
            'pid': os.getpid(),
            'server_port': self.port,
            'uptime_seconds': round(time.time() - self.started, 1),
            'total_backend_requests': self.requests,
            'vault_documents_on_disk': len(list(self.vault.rglob('*.md'))) if self.vault.is_dir() else 0,
            'audit_log_path': self._audit_path(),
            'audit_log_size_bytes': self.audit_file.stat().st_size if self.audit_file.is_file() else 0,
            'server_time_utc': _now(),
        }

    def audit_log(self):
        records = []
        if self.audit_file.is_file():
            for line in self.audit_file.read_text(encoding='utf-8').splitlines():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
        return {'total': len(records), 'records': records[-50:]}

    def reset_audit(self):
        with self.lock:
            if self.audit_file.is_file():
                self.audit_file.write_text('', encoding='utf-8')
        return {'status': 'cleared', 'pid': os.getpid(), 'timestamp': _now()}

    def execute_step(self, payload):
        t0 = time.perf_counter()
        received_at = _now()
        with self.lock:
            self.requests += 1
            seq_id = self.requests
        trace_id = str(payload.get('trace_id') or uuid.uuid4().hex)
        span_id = uuid.uuid4().hex[:16]
        tool_name, input_val = payload.get('toolName', ''), payload.get('input', '')
        grounding = self.grounding(str(input_val or tool_name or payload.get('thought', '')))
        record = {
            'seq_id': seq_id, 'pid': os.getpid(), 'thread_id': threading.get_ident(),
            'server_received_at': received_at, 'trace_id': trace_id, 'span_id': span_id,
            'workflow_id': payload.get('workflow_id', 'custom'), 'step_index': payload.get('step_index', 0),
            'agent': payload.get('agent', 'unknown'), 'action': payload.get('action', 'think'),
            'tool_name': tool_name, 'input': input_val, 'thought': payload.get('thought', ''),
            'client_sent_at': payload.get('client_sent_at', ''),
        }
        line = json.dumps(record, ensure_ascii=False) + '\n'
        with self.lock:
            self.audit_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.audit_file, 'a', encoding='utf-8') as f:
                f.write(line)
        duration_ms = (time.perf_counter() - t0) * 1000
        data = {
            'success': True,
            'backend': {
                'execution_engine': f'Python {platform.python_version()} (ThreadingHTTPServer)',
                'pid': os.getpid(), 'thread_id': threading.get_ident(), 'seq_id': seq_id,
                'server_port': self.port, 'server_received_at': received_at, 'server_processed_at': _now(),
                'server_duration_ms': round(duration_ms, 2), 'trace_id': trace_id, 'span_id': span_id,
                'disk_audit': {'file': self._audit_path(), 'bytes_written': len(line.encode('utf-8')), 'status': 'COMMITTED_TO_DISK'},
                'vault_grounding': grounding,
            },
            'step': {
                'agent': record['agent'], 'action': record['action'], 'toolName': tool_name,
                'traceId': trace_id, 'spanId': span_id, 'output': payload.get('output'),
            },
        }
        headers = {'X-Backend-PID': str(os.getpid()), 'X-Backend-Seq': str(seq_id), 'X-Backend-Duration-Ms': f'{duration_ms:.2f}', 'X-Trace-ID': trace_id}
        return 200, data, headers
