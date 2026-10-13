"""Testes unitários para core/domain/workflow/entities.py.

Verifica invariantes das entidades de domínio de workflow:
- Mission valida missionId como int positivo JS-safe
- Step valida agent e tool
- AgentEvent serializa corretamente para o wire format
- validate_mission_envelope valida envelopes WebSocket
"""
import time
import unittest

from core.domain.workflow.entities import (
    MAX_MISSION_ID,
    AgentEvent,
    EVENT_TYPES,
    Mission,
    Step,
    is_valid_mission_id,
    validate_mission_envelope,
)


class TestMissionId(unittest.TestCase):
    def test_positive_int_is_valid(self):
        self.assertTrue(is_valid_mission_id(1))
        self.assertTrue(is_valid_mission_id(42))
        self.assertTrue(is_valid_mission_id(MAX_MISSION_ID))

    def test_zero_is_invalid(self):
        self.assertFalse(is_valid_mission_id(0))

    def test_negative_is_invalid(self):
        self.assertFalse(is_valid_mission_id(-1))

    def test_exceeds_max_safe_integer_is_invalid(self):
        self.assertFalse(is_valid_mission_id(MAX_MISSION_ID + 1))

    def test_bool_is_invalid(self):
        self.assertFalse(is_valid_mission_id(True))
        self.assertFalse(is_valid_mission_id(False))

    def test_string_is_invalid(self):
        self.assertFalse(is_valid_mission_id("1"))

    def test_none_is_invalid(self):
        self.assertFalse(is_valid_mission_id(None))

    def test_float_is_invalid(self):
        self.assertFalse(is_valid_mission_id(1.0))


class TestStep(unittest.TestCase):
    def test_valid_step(self):
        s = Step(agent="researcher", tool="search_knowledge_base", input={"query": "test"}, bubble="Pesquisando...")
        self.assertEqual(s.agent, "researcher")
        self.assertFalse(s.requires_approval)

    def test_auto_tool_does_not_require_approval(self):
        s = Step(agent="coder", tool="get_system_architecture")
        self.assertFalse(s.requires_approval)

    def test_mutation_tool_requires_approval(self):
        s = Step(agent="coder", tool="run_tests")
        self.assertTrue(s.requires_approval)

    def test_invalid_agent_raises(self):
        with self.assertRaises(ValueError) as ctx:
            Step(agent="hacker", tool="search_knowledge_base")
        self.assertIn("ALLOWED_ROLES", str(ctx.exception))

    def test_empty_tool_raises(self):
        with self.assertRaises(ValueError):
            Step(agent="researcher", tool="")

    def test_step_is_hashable(self):
        """frozen=True means Steps can be put in sets."""
        s = Step(agent="researcher", tool="search_knowledge_base")
        self.assertIsInstance({s}, set)

    def test_all_canonical_roles_work(self):
        for role in ("manager", "researcher", "coder", "writer", "reviewer"):
            s = Step(agent=role, tool="search_knowledge_base")
            self.assertEqual(s.agent, role)


class TestMission(unittest.TestCase):
    def test_valid_mission(self):
        m = Mission(id=1, task="Diagnosticar fila de pedidos", status="pending")
        self.assertEqual(m.id, 1)
        self.assertEqual(m.status, "pending")

    def test_invalid_id_raises(self):
        with self.assertRaises(ValueError):
            Mission(id=0, task="test")

    def test_bool_id_raises(self):
        with self.assertRaises(ValueError):
            Mission(id=True, task="test")

    def test_empty_task_raises(self):
        with self.assertRaises(ValueError):
            Mission(id=1, task="")

    def test_whitespace_task_raises(self):
        with self.assertRaises(ValueError):
            Mission(id=1, task="   ")

    def test_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            Mission(id=1, task="test", status="unknown_status")

    def test_all_valid_statuses(self):
        for status in ("pending", "running", "awaiting_approval", "completed", "failed", "cancelled"):
            m = Mission(id=1, task="test", status=status)
            self.assertEqual(m.status, status)

    def test_steps_appended(self):
        m = Mission(id=1, task="test")
        step = Step(agent="researcher", tool="search_knowledge_base")
        m.steps.append(step)
        self.assertEqual(len(m.steps), 1)


class TestAgentEvent(unittest.TestCase):
    def _make_event(self, **overrides):
        defaults = dict(
            mission_id=1,
            agent_id="researcher",
            event_type="status_change",
            sequence=1,
            timestamp_ms=time.time() * 1000,
            payload={"status": "working"},
        )
        defaults.update(overrides)
        return AgentEvent(**defaults)

    def test_valid_event(self):
        evt = self._make_event()
        self.assertEqual(evt.mission_id, 1)
        self.assertEqual(evt.agent_id, "researcher")

    def test_invalid_mission_id_raises(self):
        with self.assertRaises(ValueError):
            self._make_event(mission_id=0)

    def test_invalid_agent_raises(self):
        with self.assertRaises(ValueError):
            self._make_event(agent_id="invalid_agent")

    def test_invalid_event_type_raises(self):
        with self.assertRaises(ValueError):
            self._make_event(event_type="unknown_event")

    def test_sequence_zero_raises(self):
        with self.assertRaises(ValueError):
            self._make_event(sequence=0)

    def test_to_dict_wire_format(self):
        evt = self._make_event(event_id="evt:1:abc")
        wire = evt.to_dict()
        self.assertEqual(wire["schemaVersion"], 1)
        self.assertEqual(wire["id"], "evt:1:abc")
        self.assertEqual(wire["missionId"], 1)
        self.assertEqual(wire["agentId"], "researcher")
        self.assertEqual(wire["type"], "status_change")
        self.assertEqual(wire["sequence"], 1)
        self.assertIn("timestamp", wire)
        self.assertIn("payload", wire)

    def test_to_dict_default_id(self):
        """When event_id is None, to_dict should generate a default id."""
        evt = self._make_event(event_id=None, sequence=5)
        wire = evt.to_dict()
        self.assertIn("1", wire["id"])  # contains mission_id
        self.assertIn("5", wire["id"])  # contains sequence

    def test_all_event_types_valid(self):
        for et in EVENT_TYPES:
            evt = self._make_event(event_type=et)
            self.assertEqual(evt.event_type, et)

    def test_event_is_hashable(self):
        """frozen=True means AgentEvents can be put in sets."""
        evt = self._make_event()
        self.assertIsInstance({evt}, set)


class TestValidateMissionEnvelope(unittest.TestCase):
    def test_valid_envelope(self):
        msg = {"mission": {"id": 1, "task": "Diagnosticar hub"}}
        self.assertIsNone(validate_mission_envelope(msg))

    def test_missing_mission_key(self):
        error = validate_mission_envelope({"type": "START"})
        self.assertIsNotNone(error)
        self.assertIn("mission", error)

    def test_mission_not_dict(self):
        error = validate_mission_envelope({"mission": "invalid"})
        self.assertIsNotNone(error)

    def test_invalid_mission_id(self):
        error = validate_mission_envelope({"mission": {"id": 0, "task": "test"}})
        self.assertIsNotNone(error)
        self.assertIn("mission.id", error)

    def test_bool_mission_id(self):
        error = validate_mission_envelope({"mission": {"id": True, "task": "test"}})
        self.assertIsNotNone(error)

    def test_empty_task(self):
        error = validate_mission_envelope({"mission": {"id": 1, "task": ""}})
        self.assertIsNotNone(error)
        self.assertIn("task", error)

    def test_task_too_long(self):
        error = validate_mission_envelope({"mission": {"id": 1, "task": "x" * 4001}})
        self.assertIsNotNone(error)
        self.assertIn("4000", error)

    def test_valid_large_mission_id(self):
        msg = {"mission": {"id": MAX_MISSION_ID, "task": "test"}}
        self.assertIsNone(validate_mission_envelope(msg))

    def test_exceeds_max_safe_integer(self):
        error = validate_mission_envelope({"mission": {"id": MAX_MISSION_ID + 1, "task": "test"}})
        self.assertIsNotNone(error)


if __name__ == '__main__':
    unittest.main()
