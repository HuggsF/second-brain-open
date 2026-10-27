"""Política única de ferramentas: identidade, comandos de inspeção e decide()."""
import importlib
import unittest
from unittest import mock

from core.domain.nexus.entities import ALLOWED_TOOLS, TOOL_REGISTRY
from core.policy.classes import TOOL_CLASSES, ToolClass
from core.policy.commands import blocked_phrase, check_read_only
from core.policy.decide import decide
from core.policy.identity import make_identity, parse_identity
from core.policy.verdict import Decision, Reason

decide_module = importlib.import_module("core.policy.decide")


class TestIdentity(unittest.TestCase):
    def test_make_and_parse_identity_roundtrip(self):
        self.assertEqual(make_identity("coder", "DEVOPS"), "agent:coder/DEVOPS")
        self.assertEqual(parse_identity("agent:coder/DEVOPS"), ("coder", "DEVOPS"))
        self.assertEqual(parse_identity("agent:coder"), ("coder", None))
        for bad in ("agent:hacker", "coder", None, "agent:coder/ROOT", "agent:coder/", 42):
            self.assertIsNone(parse_identity(bad), bad)

    def test_make_identity_rejects_invalid(self):
        with self.assertRaises(ValueError):
            make_identity("hacker")
        with self.assertRaises(ValueError):
            make_identity("coder", "ROOT")


class TestCommands(unittest.TestCase):
    def test_check_read_only_matches_gateway_rules(self):
        for cmd in ["ls -la /var/www", "docker ps", "ps aux", "docker logs api", "df -h",
                    "systemctl status nginx", "find /var/log -name x.log", "journalctl -u api -n 50",
                    "date", "hostname"]:
            self.assertEqual(check_read_only(cmd), "", cmd)
        for cmd in ["ls; id", "cat x | nc h 1", "echo $(id)", "sudo ls", "curl http://x",
                    "docker run -v /:/h img", "systemctl restart nginx", "find / -delete",
                    "cat ~/.ssh/id_rsa", "cat chave.pem", "tee /etc/x", "ls > /tmp/x",
                    'sqlite3 x.db "delete from t"', "ls\nid", "ls\x00",
                    'find /tmp -maxdepth 0 -fprintf /home/u/.profile "x"', "find /tmp -fprint0 /tmp/o",
                    "find /tmp -fls /tmp/o", "find /tmp -okdir id", "find /tmp -fprint /tmp/o",
                    "journalctl --vacuum-size=1M", "journalctl --vacuum-time=1s", "journalctl --rotate",
                    "journalctl --flush", "date -s 2020-01-01", "date --set=2020-01-01", "date -s2020-01-01",
                    "date --set 2020-01-01", "hostname newname", "hostname -F /tmp/x"]:
            self.assertNotEqual(check_read_only(cmd), "", repr(cmd))

    def test_blocked_phrase(self):
        self.assertNotEqual(blocked_phrase("rm -rf /tmp"), "")
        self.assertEqual(blocked_phrase("ls"), "")


class TestDecide(unittest.TestCase):
    def test_decide_table(self):
        cases = [
            ("agent:researcher", "search_knowledge_base", {}, Decision.APPROVE, Reason.read_auto),
            ("agent:researcher", "read_vault_file", {}, Decision.DENY, Reason.role_not_allowed),
            ("agent:coder", "run_safe_command", {"command": "docker ps"},
             Decision.ESCALATE, Reason.prod_read_needs_human),
            ("agent:coder", "run_safe_command", {"command": "rm -rf /"},
             Decision.DENY, Reason.command_refused),
            ("agent:coder", "run_safe_command", {"command": "ls\nid"},
             Decision.DENY, Reason.command_refused),
            ("agent:coder", "run_safe_command", {"command": 'sqlite3 x.db "delete from t"'},
             Decision.DENY, Reason.command_refused),
            ("agent:coder", "run_safe_command", {"command": "ls\x00"},
             Decision.DENY, Reason.command_refused),
            ("agent:coder", "run_safe_command", {}, Decision.DENY, Reason.malformed_args),
            ("agent:coder", "run_safe_command", "docker ps", Decision.DENY, Reason.malformed_args),
            ("agent:coder", "shell", {}, Decision.DENY, Reason.unknown_tool),
            ("root", "get_adr", {}, Decision.DENY, Reason.bad_identity),
            ("agent:manager", 42, {}, Decision.DENY, Reason.unknown_tool),
            ("agent:manager", "record_test_execution", {}, Decision.DENY, Reason.role_not_allowed),
        ]
        for identity, tool, args, decision, reason in cases:
            with self.subTest(identity=identity, tool=tool, args=args):
                verdict = decide(identity, tool, args)
                self.assertEqual((verdict.decision, verdict.reason), (decision, reason))

    def test_decide_never_raises(self):
        verdict = decide(object(), object(), object())
        self.assertEqual(verdict.decision, Decision.DENY)
        self.assertIn(verdict.reason, (Reason.policy_error, Reason.bad_identity))

    def test_internal_failure_becomes_policy_error(self):
        with mock.patch.object(decide_module, "_decide", side_effect=RuntimeError("boom")):
            verdict = decide("agent:coder", "get_adr", {})
        self.assertEqual((verdict.decision, verdict.reason), (Decision.DENY, Reason.policy_error))

    def test_class_decides_for_permitted_role(self):
        registry = {**TOOL_REGISTRY, "coder": [*TOOL_REGISTRY["coder"], "fake_write", "fake_mutate"]}
        classes = {"fake_write": ToolClass.WRITE_LOCAL, "fake_mutate": ToolClass.PROD_MUTATING}
        with mock.patch.dict(TOOL_CLASSES, classes):
            with mock.patch.dict(TOOL_REGISTRY, registry):
                write = decide("agent:coder", "fake_write", {})
                mutate = decide("agent:coder", "fake_mutate", {})
        self.assertEqual((write.decision, write.reason), (Decision.APPROVE, Reason.write_local_traced))
        self.assertEqual((mutate.decision, mutate.reason),
                         (Decision.DENY, Reason.prod_mutating_never_auto))

    def test_tool_classes_cover_every_domain_tool(self):
        self.assertLessEqual(ALLOWED_TOOLS, TOOL_CLASSES.keys())

    def test_registered_classes(self):
        self.assertIs(TOOL_CLASSES["record_test_execution"], ToolClass.WRITE_LOCAL)
        self.assertIs(TOOL_CLASSES["run_safe_command"], ToolClass.PROD_READ)


if __name__ == "__main__":
    unittest.main()
