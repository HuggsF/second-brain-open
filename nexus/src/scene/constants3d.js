/**
 * constants3d.js — Shared spatial and visual constants for the 3D isometric scene.
 * All positions are [x, y, z] in Three.js world space (Y-up).
 * Room sizes are [width, depth] on the XZ plane.
 */

// ─── Camera ────────────────────────────────────────────────────────────────
export const ISO_CAMERA_POSITION = [100, 100, 100];
export const ISO_CAMERA_ZOOM = 40;
export const ISO_CAMERA_NEAR = -500;
export const ISO_CAMERA_FAR = 1000;

// ─── Room layout (XZ positions, Y=0 for floor) ─────────────────────────────
export const ROOM_CONFIGS = [
  {
    id: 'research',
    label: 'Investigação',
    position: [-5.5, 0, -3],
    size: [5, 3],
    agentId: 'researcher',   // matches simulation.mjs AGENTS id
    colorKey: 'cyan',
  },
  {
    id: 'development',
    label: 'Desenvolvimento',
    position: [0, 0, -3],
    size: [5, 3],
    agentId: 'coder',
    colorKey: 'green',
  },
  {
    id: 'writing',
    label: 'Redação',
    position: [5.5, 0, -3],
    size: [5, 3],
    agentId: 'writer',
    colorKey: 'violet',
  },
  {
    id: 'meeting',
    label: 'Revisão',
    position: [-2.5, 0, 3],
    size: [5, 3],
    agentId: 'reviewer',
    colorKey: 'amber',
  },
  {
    id: 'orchestrator',
    label: 'Orquestração',
    position: [2.5, 0, 3],
    size: [5, 3],
    agentId: 'manager',
    colorKey: 'magenta',
  },
];

// Walkway (central corridor between north and south rooms)
export const WALKWAY_POSITION = [0, 0, 0];
export const WALKWAY_SIZE = [16, 1.5];

// ─── Agent definitions ──────────────────────────────────────────────────────
export const AGENT_CONFIGS = {
  manager:    { label: 'Maia', role: 'Orquestradora', color: '#ff007f', roomId: 'orchestrator' },
  researcher: { label: 'Noah', role: 'Pesquisador',   color: '#00f0ff', roomId: 'research' },
  coder:      { label: 'Theo', role: 'Dev',           color: '#39ff14', roomId: 'development' },
  writer:     { label: 'Lia',  role: 'Escritora',     color: '#a78bfa', roomId: 'writing' },
  reviewer:   { label: 'Eva',  role: 'Revisora',      color: '#ffe600', roomId: 'meeting' },
};


// ─── Status → emissive color mapping ───────────────────────────────────────
export const STATUS_EMISSIVE = {
  idle:            '#000000',
  working:         '#39ff14',
  thinking:        '#a78bfa',
  waitingApproval: '#ffe600',
  done:            '#00f0ff',
};

// Room accent colors (neon emissive for floor/walls)
export const ROOM_ACCENT = {
  cyan:    '#00f0ff',
  green:   '#39ff14',
  violet:  '#a78bfa',
  amber:   '#ffe600',
  magenta: '#ff007f',
};

// ─── Desk geometry (relative offsets within room) ──────────────────────────
export const DESK_SIZE    = [1.2, 0.08, 0.7];   // [w, h, d]
export const DESK_Y       = 0.5;
export const MONITOR_SIZE = [0.9, 0.55, 0.04];
export const MONITOR_Y    = DESK_Y + 0.04 / 2 + 0.55 / 2 + 0.02;
export const CHAIR_SIZE   = [0.5, 0.08, 0.5];
export const CHAIR_Y      = 0.35;

// ─── Agent avatar geometry ──────────────────────────────────────────────────
export const AVATAR_BODY_SIZE = [0.3, 0.55, 0.3];
export const AVATAR_HEAD_SIZE = [0.28, 0.28, 0.28];
export const AVATAR_BODY_Y    = 0.8;
export const AVATAR_HEAD_Y    = AVATAR_BODY_Y + 0.55 / 2 + 0.28 / 2 + 0.02;

// ─── Wall / floor geometry ──────────────────────────────────────────────────
export const FLOOR_Y     = 0;
export const FLOOR_H     = 0.04;
export const WALL_HEIGHT = 2.4;
export const WALL_THICK  = 0.08;

// ─── Animation ──────────────────────────────────────────────────────────────
export const BOB_AMPLITUDE = 0.04;   // thinking bob
export const BOB_SPEED     = 2.5;
export const PULSE_SPEED   = 3.0;    // working pulse
