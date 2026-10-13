/**
 * Agent3D.jsx — 3D avatar for an agent inside the isometric office.
 *
 * Renders a blocky humanoid (body + head) with:
 *  - Status-driven emissive color
 *  - Idle: subtle float
 *  - Thinking: bob animation + violet glow
 *  - Working: faster pulse + green glow
 *  - WaitingApproval: amber strobe
 *  - Done: cyan steady glow
 *  - Selection: yellow ring beneath feet
 *  - Click → onSelect(agentId)
 */

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

import {
  AVATAR_BODY_SIZE,
  AVATAR_HEAD_SIZE,
  AVATAR_BODY_Y,
  AVATAR_HEAD_Y,
  STATUS_EMISSIVE,
  BOB_AMPLITUDE,
  BOB_SPEED,
  PULSE_SPEED,
} from './constants3d.js';

// Reusable geometries (created once, shared)
const bodyGeo  = new THREE.BoxGeometry(...AVATAR_BODY_SIZE);
const headGeo  = new THREE.BoxGeometry(...AVATAR_HEAD_SIZE);
const ringGeo  = new THREE.RingGeometry(0.22, 0.32, 32);

export default function Agent3D({ agentId, agentConfig, status = 'idle', selected = false, onSelect }) {
  const bodyRef   = useRef();
  const headRef   = useRef();
  const groupRef  = useRef();
  const matRef    = useRef();

  const baseColor    = agentConfig?.color ?? '#8888ff';
  const emissiveHex  = STATUS_EMISSIVE[status] ?? '#000000';

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (!groupRef.current) return;

    switch (status) {
      case 'thinking':
        // Gentle vertical bob
        groupRef.current.position.y = Math.sin(t * BOB_SPEED) * BOB_AMPLITUDE;
        break;
      case 'working':
        // Fast micro-bob + emissive pulse via uniform
        groupRef.current.position.y = Math.sin(t * PULSE_SPEED * 1.8) * (BOB_AMPLITUDE * 0.5);
        if (matRef.current) {
          const pulse = (Math.sin(t * PULSE_SPEED) * 0.5 + 0.5) * 0.8 + 0.2;
          matRef.current.emissiveIntensity = pulse;
        }
        break;
      case 'waitingApproval':
        // Amber strobe
        if (matRef.current) {
          const strobe = Math.sin(t * 6) > 0 ? 1.2 : 0.3;
          matRef.current.emissiveIntensity = strobe;
        }
        break;
      case 'done':
        // Steady bright cyan
        if (matRef.current) matRef.current.emissiveIntensity = 1.0;
        break;
      default:
        // idle — tiny drift
        groupRef.current.position.y = Math.sin(t * 0.8) * 0.01;
        if (matRef.current) matRef.current.emissiveIntensity = 0.0;
    }
  });

  const handleClick = (e) => {
    e.stopPropagation();
    onSelect?.(agentId);
  };

  return (
    <group ref={groupRef} onClick={handleClick}>
      {/* Body */}
      <mesh ref={bodyRef} geometry={bodyGeo} position={[0, AVATAR_BODY_Y, 0]} castShadow>
        <meshStandardMaterial
          ref={matRef}
          color={baseColor}
          emissive={emissiveHex}
          emissiveIntensity={0}
          roughness={0.3}
          metalness={0.6}
        />
      </mesh>

      {/* Head */}
      <mesh ref={headRef} geometry={headGeo} position={[0, AVATAR_HEAD_Y, 0]} castShadow>
        <meshStandardMaterial
          color={baseColor}
          emissive={emissiveHex}
          emissiveIntensity={0}
          roughness={0.25}
          metalness={0.7}
        />
      </mesh>

      {/* Selection ring (flat, on floor level) */}
      {selected && (
        <mesh geometry={ringGeo} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
          <meshBasicMaterial color="#ffe600" side={THREE.DoubleSide} transparent opacity={0.9} />
        </mesh>
      )}
    </group>
  );
}
