/**
 * contract-entities.test.mjs — Contract test between constants3d.js and nexus-entities.json
 *
 * Verifies that the Nexus frontend constants (constants3d.js) are consistent with
 * the canonical Python domain entities (core/domain/nexus/entities.py), which are
 * exported to nexus/src/generated/nexus-entities.json by scripts/generate_nexus_entities.py.
 *
 * Run: node --test nexus/tests/contract-entities.test.mjs
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..', '..');

// Load the canonical JSON (generated from Python entities.py)
const canonicalPath = join(ROOT, 'nexus', 'src', 'generated', 'nexus-entities.json');
const canonical = JSON.parse(readFileSync(canonicalPath, 'utf-8'));

// Dynamically import constants3d.js (ES module)
const { ROOM_CONFIGS, AGENT_CONFIGS, STATUS_EMISSIVE } = await import('../src/scene/constants3d.js');

// ── Canonical sets ───────────────────────────────────────────────────────────
const CANONICAL_ROLES = new Set(canonical.ALLOWED_ROLES);
const CANONICAL_ROOMS = Object.fromEntries(canonical.ROOMS.map(r => [r.id, r]));
const CANONICAL_STATUSES = new Set(canonical.AGENT_STATUSES);

// ── Tests: AGENT_CONFIGS ─────────────────────────────────────────────────────

test('AGENT_CONFIGS has all canonical roles', () => {
  for (const role of CANONICAL_ROLES) {
    assert.ok(
      role in AGENT_CONFIGS,
      `AGENT_CONFIGS missing role '${role}' (defined in entities.py)`
    );
  }
});

test('AGENT_CONFIGS has no extra roles', () => {
  for (const role of Object.keys(AGENT_CONFIGS)) {
    assert.ok(
      CANONICAL_ROLES.has(role),
      `AGENT_CONFIGS has undeclared role '${role}' (not in entities.py)`
    );
  }
});

test('AGENT_CONFIGS colors match entities.py', () => {
  for (const [role, data] of Object.entries(canonical.AGENT_ROLES)) {
    const jsAgent = AGENT_CONFIGS[role];
    if (!jsAgent) continue;
    assert.equal(
      jsAgent.color?.toLowerCase(),
      data.color.toLowerCase(),
      `Color mismatch for role '${role}': JS=${jsAgent.color}, Python=${data.color}`
    );
  }
});

test('AGENT_CONFIGS roomId matches entities.py room', () => {
  for (const [role, data] of Object.entries(canonical.AGENT_ROLES)) {
    const jsAgent = AGENT_CONFIGS[role];
    if (!jsAgent) continue;
    // roomId in JS == room in entities.py
    assert.equal(
      jsAgent.roomId,
      data.room,
      `roomId mismatch for role '${role}': JS roomId=${jsAgent.roomId}, Python room=${data.room}`
    );
  }
});

test('AGENT_CONFIGS names match entities.py', () => {
  for (const [role, data] of Object.entries(canonical.AGENT_ROLES)) {
    const jsAgent = AGENT_CONFIGS[role];
    if (!jsAgent) continue;
    // In constants3d.js: label = agent name ("Maia"), role = functional label ("Orquestradora")
    // In entities.py: name = "Maia", label = "Orquestradora"
    assert.equal(
      jsAgent.label,
      data.name,
      `label (name) mismatch for role '${role}': JS label=${jsAgent.label}, Python name=${data.name}`
    );
    assert.equal(
      jsAgent.role,
      data.agentLabel,  // functional label from generated JSON
      `role (agentLabel) mismatch for '${role}': JS role=${jsAgent.role}, Python agentLabel=${data.agentLabel}`
    );
  }
});

// ── Tests: ROOM_CONFIGS ──────────────────────────────────────────────────────

test('ROOM_CONFIGS has all canonical rooms', () => {
  const jsRoomIds = new Set(ROOM_CONFIGS.map(r => r.id));
  for (const roomId of Object.keys(CANONICAL_ROOMS)) {
    assert.ok(
      jsRoomIds.has(roomId),
      `ROOM_CONFIGS missing room '${roomId}' (defined in entities.py)`
    );
  }
});

test('ROOM_CONFIGS has no extra rooms', () => {
  const canonicalRoomIds = new Set(Object.keys(CANONICAL_ROOMS));
  for (const room of ROOM_CONFIGS) {
    assert.ok(
      canonicalRoomIds.has(room.id),
      `ROOM_CONFIGS has undeclared room '${room.id}' (not in entities.py)`
    );
  }
});

test('ROOM_CONFIGS positions match entities.py', () => {
  for (const jsRoom of ROOM_CONFIGS) {
    const canonical_room = CANONICAL_ROOMS[jsRoom.id];
    if (!canonical_room) continue;
    // positions must match exactly [x, y, z]
    assert.deepEqual(
      jsRoom.position,
      canonical_room.position,
      `Position mismatch for room '${jsRoom.id}': JS=${JSON.stringify(jsRoom.position)}, Python=${JSON.stringify(canonical_room.position)}`
    );
  }
});

test('ROOM_CONFIGS sizes (XZ) match entities.py', () => {
  for (const jsRoom of ROOM_CONFIGS) {
    const canonical_room = CANONICAL_ROOMS[jsRoom.id];
    if (!canonical_room) continue;
    // constants3d.js uses [width, depth] (XZ plane)
    // canonical JSON provides size (XZ) and size3d (full)
    assert.deepEqual(
      jsRoom.size,
      canonical_room.size,
      `Size mismatch for room '${jsRoom.id}': JS=[${jsRoom.size}], Python=[${canonical_room.size}]`
    );
  }
});

test('ROOM_CONFIGS colorKeys match entities.py', () => {
  for (const jsRoom of ROOM_CONFIGS) {
    const canonical_room = CANONICAL_ROOMS[jsRoom.id];
    if (!canonical_room) continue;
    assert.equal(
      jsRoom.colorKey,
      canonical_room.colorKey,
      `colorKey mismatch for room '${jsRoom.id}': JS=${jsRoom.colorKey}, Python=${canonical_room.colorKey}`
    );
  }
});

test('ROOM_CONFIGS agentId matches AGENT_CONFIGS roomId', () => {
  for (const jsRoom of ROOM_CONFIGS) {
    // Find agent whose roomId matches this room
    const agentEntry = Object.entries(AGENT_CONFIGS).find(([, a]) => a.roomId === jsRoom.id);
    if (jsRoom.agentId) {
      assert.ok(agentEntry, `Room '${jsRoom.id}' has agentId='${jsRoom.agentId}' but no agent has roomId='${jsRoom.id}'`);
      const [agentId] = agentEntry;
      assert.equal(jsRoom.agentId, agentId, `Room '${jsRoom.id}' agentId mismatch: JS=${jsRoom.agentId}, expected=${agentId}`);
    }
  }
});

// ── Tests: STATUS_EMISSIVE ───────────────────────────────────────────────────

test('STATUS_EMISSIVE covers all AGENT_STATUSES', () => {
  for (const status of CANONICAL_STATUSES) {
    assert.ok(
      status in STATUS_EMISSIVE,
      `STATUS_EMISSIVE missing status '${status}' (defined in entities.py AGENT_STATUSES)`
    );
  }
});

test('STATUS_EMISSIVE colors are valid hex', () => {
  const hexPattern = /^#[0-9a-fA-F]{6}$/;
  for (const [status, color] of Object.entries(STATUS_EMISSIVE)) {
    assert.match(
      color,
      hexPattern,
      `STATUS_EMISSIVE['${status}'] = '${color}' is not a valid #RRGGBB color`
    );
  }
});
