/**
 * Room3D.jsx — Single isometric room with floor, walls, desk furniture,
 * a status point-light, an HTML room label and an optional speech bubble.
 *
 * Props:
 *   config       — room config from ROOM_CONFIGS
 *   agentStatus  — 'idle' | 'working' | 'thinking' | 'waitingApproval' | 'done'
 *   bubble       — { text, variant } | null
 *   selectedId   — currently selected agentId
 *   onSelect     — (agentId) => void
 *   overlayRef   — React ref to the DOM element used as Html portal
 */

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';

import Agent3D from './Agent3D.jsx';
import {
  FLOOR_H,
  WALL_HEIGHT,
  WALL_THICK,
  DESK_SIZE,
  DESK_Y,
  MONITOR_SIZE,
  MONITOR_Y,
  CHAIR_SIZE,
  CHAIR_Y,
  AVATAR_HEAD_Y,
  STATUS_EMISSIVE,
  ROOM_ACCENT,
  AGENT_CONFIGS,
} from './constants3d.js';

// ─── Shared geometries (created once, reused across all rooms) ────────────────
const floorGeo   = new THREE.BoxGeometry(1, FLOOR_H, 1);
const wallHGeo   = new THREE.BoxGeometry(1, WALL_HEIGHT, WALL_THICK);
const wallVGeo   = new THREE.BoxGeometry(WALL_THICK, WALL_HEIGHT, 1);
const deskGeo    = new THREE.BoxGeometry(...DESK_SIZE);
const monitorGeo = new THREE.BoxGeometry(...MONITOR_SIZE);
const chairGeo   = new THREE.BoxGeometry(...CHAIR_SIZE);

// ─── Status-driven room light ─────────────────────────────────────────────────
function RoomLight({ status, colorKey }) {
  const lightRef = useRef();
  const accentColor = ROOM_ACCENT[colorKey] ?? '#ffffff';
  const emissiveHex = STATUS_EMISSIVE[status] ?? '#000000';
  const isActive    = status !== 'idle';

  useFrame(({ clock }) => {
    if (!lightRef.current) return;
    const t = clock.elapsedTime;
    if (status === 'working') {
      lightRef.current.intensity = (Math.sin(t * 3) * 0.5 + 0.5) * 0.8 + 0.3;
    } else if (status === 'thinking') {
      lightRef.current.intensity = 0.6;
    } else if (status === 'waitingApproval') {
      lightRef.current.intensity = Math.sin(t * 6) > 0 ? 1.2 : 0.2;
    } else if (status === 'done') {
      lightRef.current.intensity = 1.0;
    } else {
      lightRef.current.intensity = 0.1;
    }
  });

  return (
    <pointLight
      ref={lightRef}
      color={isActive ? emissiveHex : accentColor}
      intensity={0.1}
      distance={5}
      decay={2}
      position={[0, WALL_HEIGHT * 0.8, 0]}
    />
  );
}

// ─── Desk + monitor + chair ───────────────────────────────────────────────────
function Furniture({ accent }) {
  return (
    <group>
      <mesh geometry={deskGeo} position={[0, DESK_Y, -0.2]} castShadow receiveShadow>
        <meshStandardMaterial color="#1a1a2e" emissive={accent} emissiveIntensity={0.08} roughness={0.5} metalness={0.8} />
      </mesh>
      <mesh geometry={monitorGeo} position={[0, MONITOR_Y, -0.4]} castShadow>
        <meshStandardMaterial color="#050510" emissive={accent} emissiveIntensity={0.6} roughness={0.1} metalness={0.9} />
      </mesh>
      <mesh geometry={chairGeo} position={[0, CHAIR_Y, 0.3]} castShadow receiveShadow>
        <meshStandardMaterial color="#0d0b1a" emissive={accent} emissiveIntensity={0.04} roughness={0.7} metalness={0.4} />
      </mesh>
    </group>
  );
}

// ─── Room ─────────────────────────────────────────────────────────────────────
export default function Room3D({
  config,
  agentStatus = 'idle',
  bubble = null,
  selectedId,
  onSelect,
  overlayRef,
}) {
  const { label, position, size, agentId, colorKey } = config;
  const [w, d] = size;

  const accent      = ROOM_ACCENT[colorKey] ?? '#00f0ff';
  const agentCfg    = AGENT_CONFIGS[agentId];
  const wallOpacity = 0.18;

  return (
    <group position={position}>
      {/* ── Floor ── */}
      <mesh geometry={floorGeo} scale={[w, 1, d]} position={[0, -FLOOR_H / 2, 0]} receiveShadow>
        <meshStandardMaterial color="#0d0b1a" emissive={accent} emissiveIntensity={0.06} roughness={0.8} metalness={0.2} />
      </mesh>

      {/* ── Walls (back + left + right; front open for iso view) ── */}
      <mesh geometry={wallHGeo} scale={[w, 1, 1]} position={[0, WALL_HEIGHT / 2, -d / 2]} receiveShadow>
        <meshStandardMaterial color="#12111a" emissive={accent} emissiveIntensity={0.04} roughness={0.9} transparent opacity={wallOpacity + 0.15} />
      </mesh>
      <mesh geometry={wallVGeo} scale={[1, 1, d]} position={[-w / 2, WALL_HEIGHT / 2, 0]} receiveShadow>
        <meshStandardMaterial color="#12111a" emissive={accent} emissiveIntensity={0.04} roughness={0.9} transparent opacity={wallOpacity} />
      </mesh>
      <mesh geometry={wallVGeo} scale={[1, 1, d]} position={[w / 2, WALL_HEIGHT / 2, 0]} receiveShadow>
        <meshStandardMaterial color="#12111a" emissive={accent} emissiveIntensity={0.04} roughness={0.9} transparent opacity={wallOpacity} />
      </mesh>

      {/* ── Neon accent strip on back edge ── */}
      <mesh position={[0, 0.001, -d / 2 + 0.04]}>
        <boxGeometry args={[w, 0.02, 0.04]} />
        <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={1.5} />
      </mesh>

      {/* ── Furniture ── */}
      <Furniture accent={accent} />

      {/* ── Status light ── */}
      <RoomLight status={agentStatus} colorKey={colorKey} />

      {/* ── Agent avatar ── */}
      {agentId && agentCfg && (
        <Agent3D
          agentId={agentId}
          agentConfig={agentCfg}
          status={agentStatus}
          selected={selectedId === agentId}
          onSelect={onSelect}
        />
      )}

      {/* ── Room label (HTML portal, no remote font download) ── */}
      <Html
        portal={overlayRef}
        position={[0, WALL_HEIGHT + 0.15, -d / 2 + 0.15]}
        center
        style={{ pointerEvents: 'none' }}
        zIndexRange={[5, 0]}
      >
        <span
          className="room-label-3d"
          style={{
            color: accent,
            fontFamily: 'Orbitron, monospace',
            fontSize: '10px',
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            textShadow: `0 0 8px ${accent}`,
            whiteSpace: 'nowrap',
          }}
        >
          {label}
        </span>
      </Html>

      {/* ── Speech bubble (HTML portal, max 15 globally) ── */}
      {bubble?.text && (
        <Html
          portal={overlayRef}
          position={[0, AVATAR_HEAD_Y + 0.45, 0]}
          center
          distanceFactor={6}
          style={{ pointerEvents: 'none' }}
          zIndexRange={[10, 0]}
          occlude={false}
        >
          <div
            className={`speech-bubble bubble-${bubble.variant ?? 'default'}`}
            style={{ maxWidth: '160px', fontSize: '11px' }}
          >
            {bubble.text}
          </div>
        </Html>
      )}
    </group>
  );
}
