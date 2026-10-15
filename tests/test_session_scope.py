from core.memory.session_store import SessionMemoryStore, ScopePolicy, _CROSS_PERSONA_SAFE_FIELDS

def test_own_session_full_access():
    store = SessionMemoryStore()
    store.append("sess1", {"agent": "persona-a", "event": "call", "tool_args": {"secret": "123"}})
    view = store.get_scoped_view("sess1", "persona-a", ScopePolicy.FULL_ACCESS)
    assert len(view) == 1
    assert "tool_args" in view[0]  # dono tem acesso total

def test_cross_persona_filtered():
    store = SessionMemoryStore()
    store.append("sess1", {"agent": "persona-a", "event": "call", "tool_args": {"secret": "123"}, "status": "ok"})
    view = store.get_scoped_view("sess1", "persona-b", ScopePolicy.FULL_ACCESS)
    assert len(view) == 1
    assert "tool_args" not in view[0]  # cross-persona: campo sensível filtrado
    assert "event" in view[0]  # campo seguro preservado
    assert "status" in view[0]

def test_orchestrator_has_full_access():
    store = SessionMemoryStore()
    store.append("sess1", {"agent": "persona-a", "event": "call", "tool_args": {"secret": "123"}})
    view = store.get_scoped_view("sess1", "maia-orchestrator", ScopePolicy.FULL_ACCESS)
    assert "tool_args" in view[0]  # supervisor: acesso total

def test_manager_alias_has_full_access():
    store = SessionMemoryStore()
    store.append("sess1", {"agent": "persona-a", "event": "call", "tool_result": "data"})
    view = store.get_scoped_view("sess1", "manager", ScopePolicy.FULL_ACCESS)
    assert "tool_result" in view[0]  # alias do orchestrator

def test_scoped_summary_unchanged():
    store = SessionMemoryStore()
    store.append("sess1", {"agent": "persona-a", "event": "call", "tool_args": {"x": 1}, "summary": "ok"})
    view = store.get_scoped_view("sess1", "persona-b", ScopePolicy.SCOPED_SUMMARY)
    assert "tool_args" not in view[0]
    assert "summary" in view[0]
