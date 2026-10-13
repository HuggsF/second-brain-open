/**
 * Room3D.jsx — Single isometric room with floor, walls, desk furniture,
 * a status point-light, SDF label, and an optional speech bubble (via drei <Html>).
 *
 * Props:
 *   config       — room config from ROOM_CONFIGS
 *   agentStatus  — 'idle' | 'working' | 'thinking' | 'waitingApproval' | 'done'
 *   bubble       — { text, variant } | null
 *   selectedId   — currently selected agentId
 *   onSelect     — (agentId) => void
 *   simulation   — full simulation state (for agent lookup)
 */

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Text, Html } from '@react-three/drei';
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
  STATUS_EMISSIVE,
  ROOM_ACCENT,
  AGENT_CONFIGS,
} from './constants3d.js';

// Shared geometries
const floorGeo   = new THREE.BoxGeometry(1, FLOOR_H, 1);   // scaled per room
const wallHGeo   = new THREE.BoxGeometry(1, WALL_HEIGHT, WALL_THICK); // horizontal wall
const wallVGeo   = new THREE.BoxGeometry(WALL_THICK, WALL_HEIGHT, 1); // vertical wall
const deskGeo    = new THREE.BoxGeometry(...DESK_SIZE);
const monitorGeo = new THREE.BoxGeometry(...MONITOR_SIZE);
const chairGeo   = new THREE.BoxGeometry(...CHAIR_SIZE);

function RoomLight({ status, colorKey }) {
  const lightRef = useRef();

  const accentColor  = ROOM_ACCENT[colorKey] ?? '#ffffff';
  const emissiveHex  = STATUS_EMISSIVE[status] ?? '#000000';
  const isActive     = status !== 'idle';

  useFrame((state) => {
    if (!lightRef.current) return;
    if (status === 'working') {
      const t = state.clock.elapsedTime;
      lightRef.current.intensity = (Math.sin(t * 3) * 0.5 + 0.5) * 0.8 + 0.3;
    } else if (status === 'thinking') {
      lightRef.current.intensity = 0.6;
    } else if (status === 'waitingApproval') {
      const t = state.clock.elapsedTime;
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

function Furniture({ roomColor }) {
  const accent = roomColor ?? '#00f0ff';
  return (
    <group>
      {/* Desk */}
      <mesh geometry={deskGeo} position={[0, DESK_Y, -0.2]} castShadow receiveShadow>
        <meshStandardMaterial color="#1a1a2e" emissive={accent} emissiveIntensity={0.08} roughness={0.5} metalness={0.8} />
      </mesh>

      {/* Monitor */}
      <mesh geometry={monitorGeo} position={[0, MONITOR_Y, -0.4]} castShadow>
        <meshStandardMaterial color="#050510" emissive={accent} emissiveIntensity={0.6} roughness={0.1} metalness={0.9} />
      </mesh>

      {/* Chair */}
      <mesh geometry={chairGeo} position={[0, CHAIR_Y, 0.3]} castShadow receiveShadow>
        <meshStandardMaterial color="#0d0b1a" emissive={accent} emissiveIntensity={0.04} roughness={0.7} metalness={0.4} />
      </mesh>
    </group>
  );
}

export default function Room3D({
  config,
  agentStatus = 'idle',
  bubble = null,
  selectedId,
  onSelect,
}) {
  const { id, label, position, size, agentId, colorKey } = config;
  const [w, d] = size;

  const accentColor  = ROOM_ACCENT[colorKey] ?? '#00f0ff';
  const agentCfg     = AGENT_CONFIGS[agentId];

  // Wall opacity — slight transparency so interior is visible from iso view
  const wallOpacity = 0.18;

  return (
    <group position={position}>
      {/* ── Floor ── */}
      <mesh
        geometry={floorGeo}
        scale={[w, 1, d]}
        position={[0, -FLOOR_H / 2, 0]}
        receiveShadow
      >
        <meshStandardMaterial
          color="#0d0b1a"
          emissive={accentColor}
          emissiveIntensity={0.06}
          roughness={0.8}
          metalness={0.2}
        />
      </mesh>

      {/* ── Walls (3 sides — front open for iso view) ── */}
      {/* Back wall (north) */}
      <mesh
        geometry={wallHGeo}
        scale={[w, 1, 1]}
        position={[0, WALL_HEIGHT / 2, -d / 2]}
        receiveShadow
      >
        <meshStandardMaterial
          color="#12111a"
          emissive={accentColor}
          emissiveIntensity={0.04}
          roughness={0.9}
          transparent
          opacity={wallOpacity + 0.15}
        />
      </mesh>

      {/* Left wall */}
      <mesh
        geometry={wallVGeo}
        scale={[1, 1, d]}
        position={[-w / 2, WALL_HEIGHT / 2, 0]}
        receiveShadow
      >
        <meshStandardMaterial
          color="#12111a"
          emissive={accentColor}
          emissiveIntensity={0.04}
          roughness={0.9}
          transparent
          opacity={wallOpacity}
        />
      </mesh>

      {/* Right wall */}
      <mesh
        geometry={wallVGeo}
        scale={[1, 1, d]}
        position={[w / 2, WALL_HEIGHT / 2, 0]}
        receiveShadow
      >
        <meshStandardMaterial
          color="#12111a"
          emissive={accentColor}
          emissiveIntensity={0.04}
          roughness={0.9}
          transparent
          opacity={wallOpacity}
        />
      </mesh>

      {/* ── Room accent edge (neon border strip on floor perimeter) ── */}
      <mesh position={[0, 0.001, -d / 2 + 0.04]}>
        <boxGeometry args={[w, 0.02, 0.04]} />
        <meshStandardMaterial color={accentColor} emissive={accentColor} emissiveIntensity={1.5} />
      </mesh>

      {/* ── Furniture ── */}
      <Furniture roomColor={accentColor} />

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

      {/* ── Room label (SDF text — no DOM overhead) ── */}
      <Text
        position={[0, WALL_HEIGHT + 0.15, -d / 2 + 0.15]}
        rotation={[0, 0, 0]}
        fontSize={0.22}
        color={accentColor}
        font="https://fonts.gstatic.com/s/orbitron/v31/yMJMMIlzdpvBhQQL_SC3X9yhF25-T1nyGy6xpmIyXjU.woff2"
        anchorX="center"
        anchorY="bottom"
        outlineWidth={0.008}
        outlineColor="#000000"
      >
        {label.toUpperCase()}
      </Text>

      {/* ── Speech bubble (HTML overlay, pooled — max 15 globally) ── */}
      {bubble?.text && (
        <Html
          position={[0, AVATAR_HEAD_Y + 0.4, 0]}
          center
          distanceFactor={6}
          style={{ pointerEvents: 'none' }}
          zIndexRange={[10, 0]}
          occlude={false}
        >
          <div className={`speech-bubble bubble-${bubble.variant ?? 'default'}`}
            style={{ maxWidth: '160px', fontSize: '11px' }}>
            {bubble.text}
          </div>
        </Html>
      )}
    </group>
  );
}

// Need to import this for the Html speech bubble position calculation
const AVATAR_HEAD_Y = 1.22; // mirrors constants3d — imported there but repeated here for closure clarity
