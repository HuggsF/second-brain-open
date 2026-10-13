import { AGENTS, createSimulation, startSimulation, pauseSimulation, tickSimulation, approveTask } from './simulation.mjs';
import { decodeEvent } from './adapters/event-protocol.js';

function validWorkspace(value) {
  const s = value?.simulation;
  return s && ['idle','running','paused','completed'].includes(s.mode) && Number.isSafeInteger(s.tick) && s.tick >= 0 && s.tick <= 13
    && typeof s.task === 'string' && Array.isArray(s.agents) && s.agents.length === 5 && AGENTS.every(a => s.agents.some(b => b.id === a.id && Array.isArray(b.memory) && Array.isArray(b.history)))
    && Array.isArray(s.logs) && Array.isArray(s.collabEvents) && typeof s.needsApproval === 'boolean'
    && Number.isSafeInteger(value.missionId) && value.missionId >= 0 && [1,2].includes(value.speed)
    && ['manualReducedMotion','systemReducedMotion','taskOpen'].every(k => typeof value[k] === 'boolean')
    && value.connection && Array.isArray(value.pendingCommands);
}

export function createInitialState(task, now = 0) {
  return { simulation: createSimulation(task, Number.isFinite(now) ? now : 0), missionId: 0,
    selectedId: null, speed: 1, manualReducedMotion: false, systemReducedMotion: false,
    taskOpen: false, connection: { mode: 'local', status: 'connected', error: null }, pendingCommands: [] };
}
const timed = new Set(['START','PAUSE','RESUME','TICK','RESET','APPROVE','NEW_TASK']);
export function simulationReducer(state, action) {
  if (!action || typeof action.type !== 'string') return state;
  if (action.missionId !== undefined && action.missionId !== state.missionId) return state;
  if (timed.has(action.type) && (!Number.isFinite(action.now) || action.now < 0)) return state;
  const { type, payload, now } = action;
  let simulation = state.simulation;
  let missionId = state.missionId;
  switch (type) {
    case 'START':
      simulation = startSimulation(simulation, now);
      if (simulation !== state.simulation && state.simulation.mode !== 'paused') missionId++;
      break;
    case 'RESUME': if (simulation.mode !== 'paused') return state; simulation = startSimulation(simulation, now); break;
    case 'PAUSE': simulation = pauseSimulation(simulation, now); break;
    case 'TICK': simulation = tickSimulation(simulation, now); break;
    case 'APPROVE': simulation = approveTask(simulation, now); break;
    case 'RESET': return { ...state, simulation: createSimulation(simulation.task, now), missionId: missionId + 1, selectedId: null, pendingCommands: [] };
    case 'NEW_TASK':
      if (typeof payload !== 'string' || !payload.trim()) return state;
      return { ...state, simulation: createSimulation(payload, now), missionId: missionId + 1, selectedId: null, taskOpen: false, pendingCommands: [] };
    case 'SELECT_AGENT': return payload === null || AGENTS.some(a => a.id === payload) ? { ...state, selectedId: payload } : state;
    case 'SET_SPEED': return payload === 1 || payload === 2 ? { ...state, speed: payload } : state;
    case 'TOGGLE_MOTION': return { ...state, manualReducedMotion: !state.manualReducedMotion };
    case 'SET_SYSTEM_MOTION': return typeof payload === 'boolean' ? { ...state, systemReducedMotion: payload } : state;
    case 'OPEN_TASK': return { ...state, taskOpen: true };
    case 'CLOSE_TASK': return { ...state, taskOpen: false };
    case 'PROTOCOL_STATE': return validWorkspace(payload) ? payload : state;
    case 'REMOTE_EVENT': {
      const event = decodeEvent(payload);
      if (!event || event.missionId !== missionId) return state;
      simulation = structuredClone(simulation);
      const agent = simulation.agents.find(a => a.id === event.agentId);
      if (event.payload.status !== undefined) agent.status = event.payload.status;
      if (event.payload.progress !== undefined) agent.progress = event.payload.progress;
      if (event.type === 'approval_request') { simulation.needsApproval = true; agent.status = 'waitingApproval'; }
      if (event.type === 'completion') { agent.status = 'done'; agent.progress = 100; agent.completed = 1;
        if (simulation.agents.every(a => a.status === 'done')) { simulation.mode = 'completed'; simulation.needsApproval = false; }
      }
      if (event.type === 'message') simulation.logs = [{id:event.id,agentId:agent.id,agentName:agent.name,message:event.payload.message,at:event.timestamp,kind:'info',source:'backend-python'},...simulation.logs].slice(0,60);
      if (event.type === 'collaboration') simulation.collabEvents = [...simulation.collabEvents,{id:event.id,type:event.payload.subtype,
        agentId:agent.id,from:event.payload.from || agent.id,to:event.payload.to || [],bubble:event.payload.bubble || null,at:event.timestamp,consumed:false}].slice(-120);
      break;
    }
    default: return state;
  }
  return simulation === state.simulation ? state : { ...state, simulation, missionId, pendingCommands: missionId !== state.missionId ? [] : state.pendingCommands };
}
