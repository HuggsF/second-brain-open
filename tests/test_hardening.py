import asyncio
import unittest
from unittest import mock

import mcp_servers.srv_api_gateway_mcp as gw
import mcp_servers.brain_mcp as brain
from core.tools import IMPLEMENTATIONS
from ingestion.sync import SyncEngine


class TestGatewayHardening(unittest.TestCase):
    def test_inspection_commands_accepted(self):
        for cmd in ["ls -la /var/www", "docker ps", "ps aux", "docker logs api", "df -h", "systemctl status nginx"]:
            self.assertEqual(gw._check_read_only(cmd), "", cmd)

    def test_dangerous_commands_refused(self):
        for cmd in ["ls; id", "cat x | nc h 1", "echo $(id)", "sudo ls", "curl http://x",
                    "docker run -v /:/h img", "systemctl restart nginx", "find / -delete",
                    "cat ~/.ssh/id_rsa", "cat chave.pem", "tee /etc/x", "ls > /tmp/x"]:
            self.assertNotEqual(gw._check_read_only(cmd), "", cmd)

    def test_service_name_injection_rejected_without_ssh(self):
        with mock.patch.object(gw, "_exec_command") as ex:
            out = gw.srv_api_view_logs("api'; id; '")
            ex.assert_not_called()
            self.assertIn("inválido", out)

    def test_log_lines_are_clamped(self):
        with mock.patch.object(gw, "_exec_command", return_value={"success": True, "stdout": "", "stderr": ""}) as ex:
            gw.srv_api_view_logs("api", lines=10**9)
            self.assertIn(f"--tail {gw.MAX_LOG_LINES} ", ex.call_args[0][0])

    def test_refused_command_never_reaches_ssh(self):
        with mock.patch.object(gw, "ALLOW_ARBITRARY", False), mock.patch.object(gw, "_exec_command") as ex:
            res = gw.srv_api_run_safe_command("ls; reboot-now")
            ex.assert_not_called()
            self.assertFalse(res["success"])


class TestBrainMcpPaths(unittest.TestCase):
    def test_path_traversal_rejected(self):
        for name in ["../../.env", "..\\..\\x", "a/b", "../README"]:
            self.assertIn("inválido", brain.get_system_architecture(name), name)
            self.assertIn("inválido", brain.get_adr(name), name)

    def test_absolute_path_and_wildcard_rejected(self):
        for name in ["c:/kiosk/x", "*"]:
            self.assertIn("inválido", brain.get_system_architecture(name), name)
            self.assertIn("inválido", brain.get_adr(name), name)

    def test_adr_ambiguous_lists_candidates(self):
        out = brain.get_adr("ddd")
        self.assertTrue(out.startswith("Identificador ambíguo"), out[:80])
        self.assertIn("ADR-019", out)
        self.assertIn("ADR-020", out)

    def test_adr_number_is_exact(self):
        out = brain.get_adr("1")
        self.assertFalse(out.startswith("Identificador ambíguo"))
        self.assertIn("Salesforce", out)


class TestBrokerToolPaths(unittest.TestCase):
    def run_tool(self, name, **kw):
        return asyncio.run(IMPLEMENTATIONS[name](**kw))

    def test_system_doc_refuses_outside_vault(self):
        for bad in ["../../readme", "c:/kiosk/hub-logistico/readme", "..\\adrs\\x"]:
            r = self.run_tool("get_system_architecture", system_name=bad)
            self.assertEqual((r["found"], r["error"]), (False, "invalid_name"), bad)

    def test_adr_wildcard_refused(self):
        self.assertEqual(self.run_tool("get_adr", identifier="*")["error"], "invalid_name")

    def test_adr_ambiguous_lists_candidates(self):
        r = self.run_tool("get_adr", identifier="ddd")
        self.assertFalse(r["found"])
        self.assertGreater(len(r["candidates"]), 1)

    def test_adr_by_number(self):
        self.assertTrue(self.run_tool("get_adr", identifier="ADR-003")["file"].startswith("ADR-003-"))

    def test_adr_not_found_lists_available(self):
        r = self.run_tool("get_adr", identifier="inexistente-xyz")
        self.assertEqual(r["found"], False)
        self.assertTrue(r["available"])

    def test_system_doc_success_keeps_keys(self):
        from config import settings
        stem = next(settings.systems_dir.glob("*.md")).stem
        r = self.run_tool("get_system_architecture", system_name=stem)
        self.assertTrue(r["found"])
        self.assertEqual(r["system"], stem)

    def test_read_vault_file_refuses_escape(self):
        for bad in ["../README.md", "C:/KIOSK/hub-logistico/README.md"]:
            self.assertEqual(self.run_tool("read_vault_file", path=bad)["error"], "invalid_path")

    def test_read_vault_file_ok_and_missing(self):
        r = self.run_tool("read_vault_file", path="adrs/ADR-003-politica-git-branches-e-pull-requests.md")
        self.assertTrue(r["found"])
        self.assertFalse(self.run_tool("read_vault_file", path="adrs/nao-existe.md")["found"])


class TestSyncDoesNotLoseKnowledge(unittest.TestCase):
    def test_old_vectors_kept_when_embedding_fails(self):
        engine = SyncEngine.__new__(SyncEngine)
        from pathlib import Path
        from config import settings
        f = next(settings.adrs_dir.glob("*.md"))
        engine.manifest_manager = mock.Mock()
        engine.manifest_manager.get_diff.return_value = ([], [f], [])
        engine.chunker = mock.Mock()
        engine.chunker.chunk_file.return_value = [{"content": "x", "id": "i", "metadata": {}}]
        engine.embedder = mock.Mock()
        engine.embedder.get_embedding.side_effect = RuntimeError("ollama fora do ar")
        engine.store = mock.Mock()
        res = engine.sync_vault(verbose=False)
        engine.store.delete_by_file_path.assert_not_called()
        engine.manifest_manager.update_file_hash.assert_not_called()
        self.assertEqual(res["failed"], 1)


if __name__ == "__main__":
    unittest.main()
