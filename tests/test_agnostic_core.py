"""Gate de agnosticismo: o núcleo novo não nomeia a instância."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS = r"kiosk|touti|amavia|yes!\s*cosm|hub[\s_-]?log|bling|sults|holmes|srv[\s_-]?api|salesforce|\bsap\b|j&t"
SCOPES = ("core/protocol", "core/local_tasks", "profiles/example")
FILES = ("core/events.py", "mcp_servers/local_tasks_mcp.py")


class TestAgnosticCore(unittest.TestCase):
    def test_new_core_modules_do_not_name_the_instance(self):
        pattern = re.compile(TERMS, re.IGNORECASE)
        paths = [p for s in SCOPES if (ROOT / s).is_dir() for p in (ROOT / s).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        paths += [ROOT / f for f in FILES if (ROOT / f).is_file()]
        offenders = []
        for p in paths:
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                m = pattern.search(line)
                if m:
                    offenders.append(f"{p.relative_to(ROOT).as_posix()}:{n}: {m.group(0)}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
