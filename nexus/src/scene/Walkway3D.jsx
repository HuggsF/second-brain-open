/**
 * Walkway3D.jsx — Central corridor connecting rooms, with holographic floor grid
 * and decorative plant pots at the ends.
 */

import * as THREE from 'three';
import { WALKWAY_POSITION, WALKWAY_SIZE, FLOOR_H } from './constants3d.js';

const corridorGeo = new THREE.BoxGeometry(1, FLOOR_H, 1);
const plantGeo    = new THREE.CylinderGeometry(0.12, 0.15, 0.35, 8);
const soilGeo     = new THREE.CylinderGeometry(0.1, 0.1, 0.05, 8);

function PlantPot({ position }) {
  return (
    <group position={position}>
      {/* Pot */}
      <mesh geometry={plantGeo} position={[0, 0.175, 0]} castShadow>
        <meshStandardMaterial color="#1a1030" emissive="#a78bfa" emissiveIntensity={0.15} roughness={0.6} metalness={0.3} />
      </mesh>
      {/* Soil / plant top */}
      <mesh geometry={soilGeo} position={[0, 0.375, 0]}>
        <meshStandardMaterial color="#39ff14" emissive="#39ff14" emissiveIntensity={0.4} roughness={0.9} />
      </mesh>
    </group>
  );
}

export default function Walkway3D() {
  const [w, d] = WALKWAY_SIZE;

  return (
    <group position={WALKWAY_POSITION}>
      {/* ── Corridor floor ── */}
      <mesh
        geometry={corridorGeo}
        scale={[w, 1, d]}
        position={[0, -FLOOR_H / 2, 0]}
        receiveShadow
      >
        <meshStandardMaterial
          color="#08071a"
          emissive="#0044ff"
          emissiveIntensity={0.04}
          roughness={0.95}
          metalness={0.1}
        />
      </mesh>

      {/* ── Center line strip (holographic walkway marker) ── */}
      <mesh position={[0, 0.002, 0]}>
        <boxGeometry args={[w, 0.015, 0.06]} />
        <meshStandardMaterial color="#00f0ff" emissive="#00f0ff" emissiveIntensity={0.9} transparent opacity={0.7} />
      </mesh>

      {/* ── Decorative plants at ends of walkway ── */}
      <PlantPot position={[-w / 2 + 0.4, 0, 0]} />
      <PlantPot position={[ w / 2 - 0.4, 0, 0]} />

      {/* ── Entry arrow (subtle floor marking) ── */}
      <mesh position={[0, 0.002, d / 2 - 0.1]} rotation={[0, 0, 0]}>
        <planeGeometry args={[0.4, 0.4]} />
        <meshBasicMaterial color="#ff007f" transparent opacity={0.5} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}
