"""Testes unitários para core/domain/nexus/entities.py.

Verifica invariantes da fonte de verdade do domínio Nexus:
- ALLOWED_ROLES ⊆ AGENT_ROLES
- AUTO_TOOLS ⊆ ALLOWED_TOOLS
- Consistência interna entre TOOL_REGISTRY e ALLOWED_TOOLS
- ROOMS corresponde a AGENT_ROLES.room
"""
import unittest

from core.domain.nexus.entities import (
    AGENT_ROLES,
    AGENT_STATUSES,
    ALLOWED_ROLES,
    ALLOWED_TOOLS,
    AUTO_TOOLS,
    HANDOFF_TYPES,
    MISSION_EVENT_FIELDS,
    MISSION_STATUSES,
    ROOMS,
    TOOL_REGISTRY,
)


class TestAgentRoles(unittest.TestCase):
    def test_allowed_roles_matches_agent_roles_keys(self):
        self.assertEqual(ALLOWED_ROLES, frozenset(AGENT_ROLES.keys()))

    def test_all_canonical_roles_present(self):
        for role in ('manager', 'researcher', 'coder', 'writer', 'reviewer'):
            self.assertIn(role, ALLOWED_ROLES, f"Role '{role}' missing from ALLOWED_ROLES")

    def test_each_role_has_required_fields(self):
        required = {'label', 'name', 'color', 'room'}
        for role, data in AGENT_ROLES.items():
            missing = required - set(data.keys())
            self.assertEqual(missing, set(), f"Role '{role}' missing fields: {missing}")

    def test_each_role_room_exists_in_rooms(self):
        for role, data in AGENT_ROLES.items():
            room = data.get('room')
            self.assertIn(room, ROOMS, f"Role '{role}' references unknown room '{room}'")

    def test_colors_are_hex(self):
        import re
        for role, data in AGENT_ROLES.items():
            self.assertRegex(data['color'], r'^#[0-9a-fA-F]{6}$',
                             f"Role '{role}' color '{data['color']}' is not a valid hex color")


class TestRooms(unittest.TestCase):
    def test_all_canonical_rooms_present(self):
        for room in ('orchestrator', 'research', 'development', 'writing', 'meeting'):
            self.assertIn(room, ROOMS, f"Room '{room}' missing from ROOMS")

    def test_each_room_has_required_fields(self):
        required = {'label', 'position', 'size', 'colorKey'}
        for room, data in ROOMS.items():
            missing = required - set(data.keys())
            self.assertEqual(missing, set(), f"Room '{room}' missing fields: {missing}")

    def test_position_is_3d(self):
        for room, data in ROOMS.items():
            self.assertEqual(len(data['position']), 3,
                             f"Room '{room}' position must be [x, y, z]")

    def test_size_is_3d(self):
        for room, data in ROOMS.items():
            self.assertEqual(len(data['size']), 3,
                             f"Room '{room}' size must be [w, h, d]")


class TestToolRegistry(unittest.TestCase):
    def test_tool_registry_covers_all_roles(self):
        for role in ALLOWED_ROLES:
            self.assertIn(role, TOOL_REGISTRY, f"Role '{role}' missing from TOOL_REGISTRY")

    def test_allowed_tools_is_union_of_registry(self):
        expected = frozenset(t for tools in TOOL_REGISTRY.values() for t in tools)
        self.assertEqual(ALLOWED_TOOLS, expected)

    def test_auto_tools_subset_of_allowed_tools(self):
        extra = AUTO_TOOLS - ALLOWED_TOOLS
        self.assertEqual(extra, frozenset(),
                         f"AUTO_TOOLS contains tools not in ALLOWED_TOOLS: {extra}")

    def test_auto_tools_are_all_read_only(self):
        """AUTO_TOOLS must not include write/mutation tools."""
        mutation_tools = {'write_doc', 'run_tests', 'validate_plan', 'run_safe_command'}
        overlap = AUTO_TOOLS & mutation_tools
        self.assertEqual(overlap, frozenset(),
                         f"AUTO_TOOLS should not include mutation tools: {overlap}")

    def test_no_empty_tool_names(self):
        for tool in ALLOWED_TOOLS:
            self.assertTrue(tool.strip(), "Tool names must not be empty strings")

    def test_tools_use_snake_case(self):
        import re
        for tool in ALLOWED_TOOLS:
            self.assertRegex(tool, r'^[a-z][a-z0-9_]*$',
                             f"Tool '{tool}' does not follow snake_case naming")


class TestAgentStatuses(unittest.TestCase):
    def test_all_canonical_statuses_present(self):
        for status in ('idle', 'working', 'thinking', 'waitingApproval', 'done'):
            self.assertIn(status, AGENT_STATUSES)


class TestHandoffTypes(unittest.TestCase):
    def test_all_canonical_handoff_types_present(self):
        for ht in ('context_share', 'handoff_review', 'celebration', 'approval'):
            self.assertIn(ht, HANDOFF_TYPES)


class TestMissionDomain(unittest.TestCase):
    def test_mission_statuses_complete(self):
        for status in ('pending', 'running', 'awaiting_approval', 'completed', 'failed', 'cancelled'):
            self.assertIn(status, MISSION_STATUSES)

    def test_mission_event_fields_complete(self):
        for field in ('missionId', 'agentId', 'type', 'sequence', 'timestamp', 'payload'):
            self.assertIn(field, MISSION_EVENT_FIELDS)


class TestEntitiesAreFrozen(unittest.TestCase):
    """Exported sets and frozensets must be immutable (no accidental mutation in tests)."""

    def test_allowed_roles_is_frozenset(self):
        self.assertIsInstance(ALLOWED_ROLES, frozenset)

    def test_allowed_tools_is_frozenset(self):
        self.assertIsInstance(ALLOWED_TOOLS, frozenset)

    def test_auto_tools_is_frozenset(self):
        self.assertIsInstance(AUTO_TOOLS, frozenset)

    def test_agent_statuses_is_frozenset(self):
        self.assertIsInstance(AGENT_STATUSES, frozenset)

    def test_handoff_types_is_frozenset(self):
        self.assertIsInstance(HANDOFF_TYPES, frozenset)

    def test_mission_statuses_is_frozenset(self):
        self.assertIsInstance(MISSION_STATUSES, frozenset)


if __name__ == '__main__':
    unittest.main()
