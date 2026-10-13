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

import { Suspense, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import {
  OrthographicCamera,
  MapControls,
  Grid,
  Stats,
} from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';

import Room3D       from './Room3D.jsx';
import Walkway3D    from './Walkway3D.jsx';
import TransferLine3D from './TransferLine3D.jsx';
import { ROOM_CONFIGS } from './constants3d.js';

// ─── Helper: extract agent status from simulation state ───────────────────────
function getAgentStatus(simulation, agentId) {
  if (!simulation?.agents) return 'idle';
  // simulation.agents is a Map or plain object keyed by agentId
  const agent =
    simulation.agents instanceof Map
      ? simulation.agents.get(agentId)
      : simulation.agents[agentId];
  return agent?.status ?? 'idle';
}

// ─── Isometric scene content (inside Canvas) ─────────────────────────────────
function OfficeScene({ simulation, bubbles, transfers, selectedId, onSelect }) {
  // Derive active status — any non-idle agent → always render
  const anyActive = useMemo(() => {
    if (!simulation?.agents) return false;
    const agents = simulation.agents instanceof Map
      ? [...simulation.agents.values()]
      : Object.values(simulation.agents ?? {});
    return agents.some(a => a?.status && a.status !== 'idle');
  }, [simulation]);

  return (
    <>
      {/* ── Ambient + hemisphere lighting ── */}
      <ambientLight intensity={0.15} />
      <hemisphereLight
        skyColor="#0d0b1a"
        groundColor="#05050a"
        intensity={0.3}
      />

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
        />
      ))}

      {/* ── Transfer arcs ── */}
      <TransferLine3D transfers={transfers} />

      {/* ── Bloom post-processing (replaces CSS neon box-shadow) ── */}
      <EffectComposer>
        <Bloom
          luminanceThreshold={0.3}
          luminanceSmoothing={0.9}
          intensity={1.5}
          mipmapBlur
        />
      </EffectComposer>

      {/* ── Dev stats (only in development mode) ── */}
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
  // Switch frameloop to demand when all agents are idle (saves GPU)
  const anyActive = useMemo(() => {
    if (!simulation?.agents) return false;
    const agents = simulation.agents instanceof Map
      ? [...simulation.agents.values()]
      : Object.values(simulation.agents ?? {});
    return agents.some(a => a?.status && a.status !== 'idle');
  }, [simulation]);

  const frameloop = (anyActive && !paused && !reducedMotion) ? 'always' : 'demand';

  return (
    <div
      className="office-floor-3d"
      style={{ width: '100%', height: '100%', background: '#05050a' }}
    >
      <Canvas
        frameloop={frameloop}
        shadows
        gl={{ antialias: true, toneMapping: 5 /* ACESFilmicToneMapping */ }}
        style={{ background: '#05050a' }}
      >
        {/* True isometric camera: position [100,100,100], zoom 40 */}
        <OrthographicCamera
          makeDefault
          position={[100, 100, 100]}
          zoom={40}
          near={-500}
          far={1000}
        />

        {/* Pan-only controls — lock polar + azimuth for true isometric */}
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
          />
        </Suspense>
      </Canvas>

      {/* ── Celebration overlay — kept in DOM (same as 2D) ── */}
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
