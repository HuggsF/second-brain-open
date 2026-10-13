import React, { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from 'react';
import { createInitialState, simulationReducer } from './reducer.js';
import { createAdapter } from './adapters/simulation-adapter.js';
import { createWsTransport } from './adapters/ws-transport.js';

const ADAPTER_MODE = import.meta.env.VITE_ADAPTER_MODE || 'local';
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8848';

const SimulationContext = createContext(null);

export function createTickDriver(workspace, dispatch, clock = {}) {
  if (workspace.simulation.mode !== 'running' || workspace.simulation.needsApproval) return () => {};
  const schedule = clock.setInterval || globalThis.setInterval;
  const clear = clock.clearInterval || globalThis.clearInterval;
  const now = clock.now || Date.now;
  let active = true;
  const id = schedule(() => { if (active) dispatch({ type: 'TICK', now: now(), missionId: workspace.missionId }); }, 2000 / workspace.speed);
  return () => { if (!active) return; active = false; clear(id); };
}

export function subscribeSystemMotion(callback, matchMedia = globalThis.matchMedia?.bind(globalThis)) {
  if (!matchMedia) return () => {};
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  callback(Boolean(media.matches));
  const listener = event => callback(Boolean(event.matches));
  if (media.addEventListener) media.addEventListener('change', listener);
  else media.addListener?.(listener);
  return () => { if (media.removeEventListener) media.removeEventListener('change', listener); else media.removeListener?.(listener); };
}

export function SimulationProvider({ children, task, now = Date.now }) {
  const clock = useRef(now); clock.current = now;
  const [workspace, rawDispatch] = useReducer(simulationReducer, null, () => createInitialState(task, clock.current()));
  const stateRef = useRef(workspace);
  const listeners = useRef(new Set());
  const dispatch = useCallback(action => {
    // Synchronous bindings make adapter getState/read-after-dispatch deterministic;
    // React still renders the same reducer transition, with no adapter-owned store.
    const next = simulationReducer(stateRef.current,action);
    if (next === stateRef.current) return;
    stateRef.current = next;
    rawDispatch(action);
    for (const callback of listeners.current) callback(next);
  }, []);
  const bindings = useMemo(() => ({ dispatch, getState: () => stateRef.current,
    subscribe(callback) { listeners.current.add(callback); return () => listeners.current.delete(callback); }, now: () => clock.current() }), [dispatch]);
  // Inicializar adapter (local ou WebSocket)
  const adapterRef = useRef(null);
  useEffect(() => {
    if (ADAPTER_MODE === 'ws') {
      const transport = createWsTransport(WS_URL);
      adapterRef.current = createAdapter('ws', { ...bindings, transport });
      console.info(`[nexus] Adapter mode: WS → ${WS_URL}`);
      return () => { adapterRef.current?.dispose(); transport.dispose(); };
    }
    // modo local: nenhum adapter externo necessário
    console.info('[nexus] Adapter mode: local (simulação)');
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  const actions = useMemo(() => {
    const send = (type,payload) => dispatch({ type,payload,now:clock.current() });
    return { start: () => send('START'), pause: () => send('PAUSE'), resume: () => send('RESUME'),
      tick: () => send('TICK'), reset: () => send('RESET'), approve: () => send('APPROVE'),
      newTask: task => send('NEW_TASK',task), selectAgent: id => send('SELECT_AGENT',id),
      setSpeed: speed => send('SET_SPEED',speed), toggleMotion: () => send('TOGGLE_MOTION'),
      setSystemMotion: value => send('SET_SYSTEM_MOTION',value), openTask: () => send('OPEN_TASK'), closeTask: () => send('CLOSE_TASK') };
  }, [dispatch]);
  useEffect(() => createTickDriver(workspace,dispatch,{ now: () => clock.current() }),
    [workspace.simulation.mode,workspace.simulation.needsApproval,workspace.speed,workspace.missionId,dispatch]);
  useEffect(() => subscribeSystemMotion(actions.setSystemMotion),[actions]);
  const value = useMemo(() => ({workspace, simulation:workspace.simulation, actions, bindings,
    effectiveReducedMotion: workspace.manualReducedMotion || workspace.systemReducedMotion }),[workspace,actions,bindings]);
  return <SimulationContext.Provider value={value}>{children}</SimulationContext.Provider>;
}
export function useSimulationContext() {
  const value = useContext(SimulationContext);
  if (!value) throw new Error('useSimulationContext requires SimulationProvider');
  return value;
}
