from core.domain.nexus.entities import ALLOWED_TOOLS, AUTO_TOOLS
from core.policy import TOOL_CLASSES, ToolClass
from core.tools import IMPLEMENTATIONS


def test_registry_matches_implementations():
    assert ALLOWED_TOOLS == set(IMPLEMENTATIONS)
    safe = {ToolClass.READ, ToolClass.WRITE_LOCAL}
    assert AUTO_TOOLS == {t for t in ALLOWED_TOOLS if TOOL_CLASSES[t] in safe}
    assert "run_safe_command" not in AUTO_TOOLS
    assert set(IMPLEMENTATIONS) == set(TOOL_CLASSES) - {"record_test_execution"}
