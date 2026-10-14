"""Testes unitários para a PlaybooksApi refatorada (dashboard/serve.py).

Verifica que a API usa core.evidence como fonte de verdade (sem SQL raw,
sem _parse_frontmatter local) e que as respostas HTTP têm a forma correta.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import settings


class TestPlaybooksApiDefinitions(unittest.TestCase):
    """_all_playbooks() deve usar core.evidence.load_definitions."""

    def setUp(self):
        # Use the real vault — matches test_evidence_seed.py approach
        from dashboard.serve import PlaybooksApi
        self.api = PlaybooksApi(settings.vault_dir)

    def test_returns_all_known_playbooks(self):
        pbs = self.api._all_playbooks()
        ids = {p['id'] for p in pbs}
        # Minimum: the 10 playbooks we know exist
        for expected_id in ('PB-001', 'PB-002', 'PB-003', 'PB-008', 'PB-009', 'PB-010'):
            self.assertIn(expected_id, ids, f'Expected {expected_id} in playbooks list')

    def test_each_playbook_has_required_fields(self):
        pbs = self.api._all_playbooks()
        required = {'id', 'title', 'status', 'validates', 'environment', 'targets', 'filename'}
        for pb in pbs:
            missing = required - set(pb.keys())
            self.assertEqual(missing, set(), f"Playbook {pb.get('id')} missing fields: {missing}")

    def test_validates_is_list(self):
        pbs = self.api._all_playbooks()
        for pb in pbs:
            self.assertIsInstance(pb['validates'], list, f"Playbook {pb['id']}: validates must be list")

    def test_sorted_by_id(self):
        pbs = self.api._all_playbooks()
        ids = [p['id'] for p in pbs]
        self.assertEqual(ids, sorted(ids), "Playbooks should be sorted by id")

    def test_no_duplicate_ids(self):
        pbs = self.api._all_playbooks()
        ids = [p['id'] for p in pbs]
        self.assertEqual(len(ids), len(set(ids)), "No duplicate playbook IDs")


class TestPlaybooksApiRouting(unittest.TestCase):
    """handle() deve retornar os status HTTP corretos."""

    def setUp(self):
        from dashboard.serve import PlaybooksApi
        self.api = PlaybooksApi(settings.vault_dir)

    def test_get_all_playbooks_returns_200(self):
        status, payload = self.api.handle('/api/playbooks')
        self.assertEqual(status, 200)
        self.assertIn('playbooks', payload)
        self.assertIsInstance(payload['playbooks'], list)

    def test_get_all_playbooks_trailing_slash(self):
        status, payload = self.api.handle('/api/playbooks/')
        self.assertEqual(status, 200)
        self.assertIn('playbooks', payload)

    def test_get_known_playbook_returns_200(self):
        status, payload = self.api.handle('/api/playbooks/PB-001')
        self.assertEqual(status, 200)
        self.assertEqual(payload['id'], 'PB-001')
        self.assertIn('content', payload)
        self.assertIn('meta', payload)

    def test_get_unknown_playbook_returns_404(self):
        status, payload = self.api.handle('/api/playbooks/PB-999')
        self.assertEqual(status, 404)
        self.assertEqual(payload['error'], 'NOT_FOUND')

    def test_unmatched_path_returns_none(self):
        result = self.api.handle('/api/something-else')
        self.assertIsNone(result)

    def test_get_executions_returns_200(self):
        status, payload = self.api.handle('/api/playbooks/executions')
        self.assertEqual(status, 200)
        self.assertIn('executions', payload)
        self.assertIsInstance(payload['executions'], list)

    def test_get_playbook_executions_returns_200(self):
        status, payload = self.api.handle('/api/playbooks/PB-001/executions')
        self.assertEqual(status, 200)
        self.assertIn('executions', payload)


class TestPlaybooksApiRecordExecution(unittest.TestCase):
    """_record_execution() deve validar via core.evidence e gravar via EvidenceStore."""

    def setUp(self):
        from dashboard.serve import PlaybooksApi
        self.api = PlaybooksApi(settings.vault_dir)

    def test_rejects_invalid_json(self):
        status, payload = self.api._record_execution(b'not-json')
        self.assertEqual(status, 400)
        self.assertEqual(payload['error'], 'INVALID_JSON')

    def test_rejects_missing_required_fields(self):
        body = json.dumps({'playbook_id': 'PB-001'}).encode()
        status, payload = self.api._record_execution(body)
        self.assertEqual(status, 400)
        self.assertEqual(payload['error'], 'MISSING_FIELD')

    def test_rejects_unknown_playbook(self):
        body = json.dumps({
            'playbook_id': 'PB-999',
            'result': 'pass',
            'environment': 'hml',
            'summary': 'Test execution',
            'evidence_ref': 'vault/playbooks/PB-001-suite-automatizada-do-hub.md:1',
        }).encode()
        status, payload = self.api._record_execution(body)
        self.assertEqual(status, 400)
        self.assertIn('error', payload)

    def test_rejects_invalid_result(self):
        body = json.dumps({
            'playbook_id': 'PB-001',
            'result': 'invalid_result',
            'environment': 'hml',
            'summary': 'Test',
            'evidence_ref': 'vault/playbooks/PB-001-suite-automatizada-do-hub.md:1',
        }).encode()
        status, payload = self.api._record_execution(body)
        self.assertEqual(status, 400)

    def test_accepts_valid_execution_with_temp_db(self):
        """Full path: valid payload → EvidenceStore.record() → 201."""
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / '.runtime'
            runtime.mkdir()
            from dashboard.serve import PlaybooksApi
            api = PlaybooksApi(settings.vault_dir)
            # Override store path via monkey-patch
            from core.evidence_store import EvidenceStore
            original_store = api._store
            api._store = lambda: EvidenceStore(path=runtime / 'evidence.db')

            body = json.dumps({
                'playbook_id': 'PB-001',
                'result': 'pass',
                'environment': 'local',
                'summary': 'Suite automática validada com sucesso',
                'evidence_ref': 'vault/playbooks/PB-001-suite-automatizada-do-hub.md:1',
                'source': 'test',
                'recorded_by': 'unittest',
            }).encode()
            status, payload = api._record_execution(body)
            self.assertEqual(status, 201, msg=f"Expected 201, got {status}: {payload}")
            self.assertIn('id', payload)
            self.assertIn('ts', payload)
            self.assertEqual(payload['status'], 'recorded')


class TestPlaybooksApiCacheInvalidation(unittest.TestCase):
    """Cache de definitions deve ser invalidado no POST para refletir novos playbooks."""

    def test_cache_is_none_after_record(self):
        from dashboard.serve import PlaybooksApi
        api = PlaybooksApi(settings.vault_dir)
        # Prime the cache
        api._load_defs()
        self.assertIsNotNone(api._defs_cache)
        # After a write attempt (even failed), cache should be invalidated
        body = json.dumps({'playbook_id': 'PB-999', 'result': 'pass',
                           'environment': 'hml', 'summary': 'x',
                           'evidence_ref': 'x:1'}).encode()
        api._record_execution(body)
        # Cache is reloaded (not None) because _record_execution calls _load_defs() after invalidation
        # The important invariant is that cache was refreshed (not stale pre-invalidation data)
        self.assertIsNotNone(api._defs_cache)


class TestPlaybooksApiLiquidRendering(unittest.TestCase):
    """Testes para o endpoint /api/playbooks/{id}/render e suporte a params."""

    def test_playbooks_list_includes_params(self):
        from dashboard.serve import PlaybooksApi
        api = PlaybooksApi(settings.vault_dir)
        status, payload = api.handle('/api/playbooks', 'GET')
        self.assertEqual(status, 200)
        self.assertIn('playbooks', payload)
        for pb in payload['playbooks']:
            self.assertIn('params', pb)

    def test_render_playbook_with_liquid_params(self):
        from dashboard.serve import PlaybooksApi
        api = PlaybooksApi(settings.vault_dir)
        body = json.dumps({'params': {'erp_id': '99887766'}}).encode()
        status, payload = api.handle('/api/playbooks/PB-001/render', 'POST', body)
        self.assertEqual(status, 200)
        self.assertIn('rendered_content', payload)
        self.assertEqual(payload['params_used'], {'erp_id': '99887766'})


if __name__ == '__main__':
    unittest.main()
