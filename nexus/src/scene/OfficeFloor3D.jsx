/**
 * OfficeFloor3D.jsx — Drop-in replacement for <OfficeFloor> using React Three Fiber.
 *
 * Architecture:
 *  - <Canvas> with isometric OrthographicCamera at [100,100,100] looking at origin
 *  - <MapControls> locked to isometric angles (pan only, no orbit)
 *  - <EffectComposer> with <Bloom> for neon glow (replaces CSS box-shadow)
 *  - <Grid> for the holographic floor grid
 *  - 5x <Room3D> — one per agent room
 *  - <Walkway3D> — central corridor
 *  - <TransferLine3D> — handoff arcs
 *  - `frameloop` switches between "demand" (idle) and "always" (active) for perf
 *
 * Props mirror <OfficeFloor> exactly so Workspace.jsx can swap with zero changes:
 *   simulation, missionId, paused, reducedMotion, bubbles, transfers, onSelect, selectedId, celebrating
 */

import { Suspense, useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import {
  OrthographicCamera,
  MapControls,
  Grid,
  Stats,
} from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';

import Room3D         from './Room3D.jsx';
import Walkway3D      from './Walkway3D.jsx';
import TransferLine3D from './TransferLine3D.jsx';
import { ROOM_CONFIGS } from './constants3d.js';

// ─── Helper: resolve agents array from any storage format ─────────────────────
function getAgentsArray(simulation) {
  if (!simulation?.agents) return [];
  if (Array.isArray(simulation.agents)) return simulation.agents;           // real sim
  if (simulation.agents instanceof Map) return [...simulation.agents.values()];
  return Object.values(simulation.agents);
}

// ─── Helper: get status for a specific agentId ────────────────────────────────
function getAgentStatus(simulation, agentId) {
  const agents = getAgentsArray(simulation);
  const agent  = agents.find(a => a.id === agentId);
  return agent?.status ?? 'idle';
}

// ─── Isometric scene content (inside Canvas) ─────────────────────────────────
function OfficeScene({ simulation, bubbles, transfers, selectedId, onSelect, overlayRef }) {
  return (
    <>
      {/* ── Ambient + hemisphere lighting ── */}
      <ambientLight intensity={0.15} />
      <hemisphereLight skyColor="#0d0b1a" groundColor="#05050a" intensity={0.3} />

      {/* ── Holographic floor grid ── */}
      <Grid
        args={[24, 24]}
        position={[0, -0.001, 0]}
        cellSize={1}
        cellThickness={0.4}
        cellColor="#1a1a3e"
        sectionSize={4}
        sectionThickness={0.8}
        sectionColor="#003366"
        fadeDistance={30}
        fadeStrength={1.5}
        infiniteGrid
      />

      {/* ── Walkway ── */}
      <Walkway3D />

      {/* ── Rooms ── */}
      {ROOM_CONFIGS.map((config) => (
        <Room3D
          key={config.id}
          config={config}
          agentStatus={getAgentStatus(simulation, config.agentId)}
          bubble={bubbles?.[config.agentId] ?? null}
          selectedId={selectedId}
          onSelect={onSelect}
          overlayRef={overlayRef}
        />
      ))}

      {/* ── Transfer arcs ── */}
      <TransferLine3D transfers={transfers} />

      {/* ── Bloom post-processing (replaces CSS neon box-shadow) ── */}
      <EffectComposer>
        <Bloom luminanceThreshold={0.3} luminanceSmoothing={0.9} intensity={1.5} mipmapBlur />
      </EffectComposer>

      {/* ── Dev perf stats (DEV only) ── */}
      {import.meta.env.DEV && <Stats />}
    </>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────
export default function OfficeFloor3D({
  simulation,
  missionId,
  paused,
  reducedMotion,
  bubbles,
  transfers,
  onSelect,
  selectedId,
  celebrating,
}) {
  // Adaptive frameloop: always when agents active, demand when idle (saves GPU)
  const anyActive = useMemo(() => {
    return getAgentsArray(simulation).some(a => a?.status && a.status !== 'idle');
  }, [simulation]);

  const frameloop = (anyActive && !paused && !reducedMotion) ? 'always' : 'demand';

  // Stable DOM portal for drei <Html> — avoids remount race on R3F event connection
  const [overlayEl, setOverlayEl] = useState(null);
  const overlayRef = useMemo(() => ({ current: overlayEl }), [overlayEl]);

  return (
    <div
      ref={setOverlayEl}
      className="office-floor-3d"
      style={{ width: '100%', height: '100%', background: '#05050a' }}
    >
      {/* Wait for overlayEl to be set before mounting Canvas (Html portal depends on it) */}
      {overlayEl && (
        <Canvas
          frameloop={frameloop}
          shadows
          gl={{ antialias: true, toneMapping: 5 /* ACESFilmicToneMapping */ }}
          style={{ position: 'absolute', inset: 0, background: '#05050a' }}
        >
          {/* True isometric camera: equal angles from X, Y, Z axes */}
          <OrthographicCamera
            makeDefault
            position={[100, 100, 100]}
            zoom={40}
            near={-500}
            far={1000}
          />

          {/* Pan + zoom only — no orbit (preserves isometric angle) */}
          <MapControls
            makeDefault
            enableRotate={false}
            enableZoom={true}
            zoomSpeed={0.8}
            panSpeed={0.8}
            screenSpacePanning={false}
            minZoom={20}
            maxZoom={80}
          />

          <Suspense fallback={null}>
            <OfficeScene
              simulation={simulation}
              bubbles={bubbles}
              transfers={transfers}
              selectedId={selectedId}
              onSelect={onSelect}
              overlayRef={overlayRef}
            />
          </Suspense>
        </Canvas>
      )}

      {/* Celebration overlay lives in DOM (same as 2D) */}
      {celebrating && (
        <div
          className="celebration-overlay"
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            pointerEvents: 'none',
            zIndex: 20,
          }}
        >
          <span style={{ fontSize: '3rem' }}>🎉</span>
        </div>
      )}
    </div>
  );
}
