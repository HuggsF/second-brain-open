/**
 * TransferLine3D.jsx — Animated arc representing a handoff/transfer between agents.
 * Phase 1 STUB — renders a simple QuadraticBezierLine from drei.
 * Phase 2 will add a travelling packet dot along the arc.
 *
 * Props:
 *   transfers — array of { from: agentId, to: agentId, type: 'handoff'|'context_share' }
 */

import { useMemo } from 'react';
import { QuadraticBezierLine } from '@react-three/drei';
import { ROOM_CONFIGS, AGENT_CONFIGS } from './constants3d.js';

// Build a lookup from agentId → room world position
const agentPositionMap = {};
for (const room of ROOM_CONFIGS) {
  if (room.agentId) {
    agentPositionMap[room.agentId] = room.position; // [x, y, z]
  }
}

function TransferArc({ from, to, type }) {
  const startPos = agentPositionMap[from];
  const endPos   = agentPositionMap[to];

  const color = type === 'context_share' ? '#a78bfa' : '#00f0ff';

  const mid = useMemo(() => {
    if (!startPos || !endPos) return [0, 2, 0];
    return [
      (startPos[0] + endPos[0]) / 2,
      Math.max(startPos[1], endPos[1]) + 2.5,   // apex height
      (startPos[2] + endPos[2]) / 2,
    ];
  }, [startPos, endPos]);

  if (!startPos || !endPos) return null;

  return (
    <QuadraticBezierLine
      start={startPos}
      mid={mid}
      end={endPos}
      color={color}
      lineWidth={1.5}
      dashed={type === 'context_share'}
      dashScale={4}
      dashSize={0.3}
    />
  );
}

export default function TransferLine3D({ transfers = [] }) {
  if (!transfers || transfers.length === 0) return null;

  return (
    <group>
      {transfers.map((t, i) => (
        <TransferArc key={i} from={t.from} to={t.to} type={t.type} />
      ))}
    </group>
  );
}
