"""Guarda: a lista de comandos de inspeção existe só em core/policy/commands.py."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LITERAL = re.compile(r"""["'](journalctl|systemctl)["']""")


def _sources():
    for sub in ("backend", "core", "mcp_servers", "scripts"):
        for path in (ROOT / sub).rglob("*.py"):
            if path.is_relative_to(ROOT / "core" / "policy"):
                continue
            yield path
    yield ROOT / "cli.py"


def test_no_command_allowlist_outside_policy():
    offenders = [str(p.relative_to(ROOT)) for p in _sources()
                 if LITERAL.search(p.read_text(encoding="utf-8", errors="replace"))]
    assert offenders == []


def test_find_write_action_list_only_in_policy():
    offenders = [str(p.relative_to(ROOT)) for p in _sources()
                 if "-execdir" in p.read_text(encoding="utf-8", errors="replace")]
    assert offenders == []
