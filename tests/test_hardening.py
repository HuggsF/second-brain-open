import unittest
from unittest import mock

import mcp_servers.srv_api_gateway_mcp as gw
import mcp_servers.brain_mcp as brain
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
