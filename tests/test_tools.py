import asyncio
import builtins
import sys

from core import tools


def test_get_rule_evidence_returns_rule_state():
    result = asyncio.run(tools.get_rule_evidence("RULE-001"))
    assert result["tool"] == "get_rule_evidence"
    assert result["found"] is True
    assert result["rule_id"] == "RULE-001"
    assert isinstance(result["state"], str)
    assert isinstance(result["playbooks"], list)


def test_get_rule_evidence_unknown_rule():
    result = asyncio.run(tools.get_rule_evidence("RULE-999999"))
    assert result == {"tool": "get_rule_evidence", "found": False, "rule_id": "RULE-999999"}


def test_run_safe_command_without_ssh_module(monkeypatch):
    monkeypatch.delitem(sys.modules, "mcp_servers.srv_api_gateway_mcp", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("mcp_servers.srv_api_gateway_mcp"):
            raise ImportError("paramiko ausente")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = asyncio.run(tools.run_safe_command("uptime"))
    assert result["tool"] == "run_safe_command"
    assert result["success"] is False
    assert result["error"] == "SSH indisponível: ImportError"
    assert "paramiko" not in result["error"]


def test_run_safe_command_uses_exec_command(monkeypatch):
    import types
    fake = types.ModuleType("mcp_servers.srv_api_gateway_mcp")
    fake._exec_command = lambda cmd: {"success": True, "exit_code": 0, "stdout": "up", "stderr": ""}
    monkeypatch.setitem(sys.modules, "mcp_servers.srv_api_gateway_mcp", fake)
    result = asyncio.run(tools.run_safe_command("uptime"))
    assert result == {"tool": "run_safe_command", "command": "uptime", "success": True,
                      "exit_code": 0, "stdout": "up", "stderr": ""}


def test_list_rules_error_keeps_only_class_name(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("token=abc123")
    monkeypatch.setattr(tools.evidence, "load_definitions", boom)
    result = asyncio.run(tools.list_rules_with_evidence())
    assert result["error"] == "RuntimeError"
