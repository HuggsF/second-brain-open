/**
 * nexus_bridge.mjs — Node.js bridge for Python integration tests.
 *
 * Modes:
 *   decode  — reads a JSON array of events from stdin, runs each through
 *             decodeEvent(), outputs { total, rejected: [] }.
 *   e2e     — connects to the ws_server, sends tasks, collects reducer
 *             state, outputs a report.
 *
 * Usage:
 *   node tests/nexus_bridge.mjs decode < events.json
 *   node tests/nexus_bridge.mjs e2e <port> <task1> [task2 ...]
 */
import { decodeEvent } from '../nexus/src/adapters/event-protocol.js';
import { createWsTransport } from '../nexus/src/adapters/ws-transport.js';
import { createAdapter } from '../nexus/src/adapters/simulation-adapter.js';
import { createInitialState, simulationReducer } from '../nexus/src/reducer.js';

const [,, mode, ...rest] = process.argv;

// Redirect informational logs to stderr so stdout is clean JSON for Python tests.
const origInfo = console.info;
const origWarn = console.warn;
console.info = (...args) => process.stderr.write(args.join(' ') + '\n');
console.warn = (...args) => process.stderr.write(args.join(' ') + '\n');

// ─── decode mode ────────────────────────────────────────────────────────────
async function runDecode() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf-8');
  const events = JSON.parse(raw);
  const rejected = [];
  for (let i = 0; i < events.length; i++) {
    if (!decodeEvent(events[i])) rejected.push({ index: i, event: events[i] });
  }
  console.log(JSON.stringify({ total: events.length, rejected }));
}

// ─── e2e mode ───────────────────────────────────────────────────────────────

/** Minimal Redux-style store wrapping the simulation reducer. */
function createStore(initialState) {
  let state = initialState;
  const listeners = new Set();
  return {
    getState: () => state,
    dispatch(action) {
      const next = simulationReducer(state, action);
      if (next !== state || action.type === 'PROTOCOL_STATE') {
        state = action.type === 'PROTOCOL_STATE' && action.payload ? action.payload : next;
        for (const cb of listeners) cb(state);
      }
    },
    subscribe(cb) { listeners.add(cb); return () => listeners.delete(cb); },
  };
}

async function runE2E() {
  const [portStr, ...tasks] = rest;
  const port = Number(portStr);
  if (!port || !tasks.length) {
    console.error('Usage: nexus_bridge.mjs e2e <port> <task1> [task2 ...]');
    process.exit(1);
  }

  const missions = [];
  let baseMissionId = 1;

  for (const task of tasks) {
    const result = await runOneMission(port, task, baseMissionId);
    missions.push(result);
    // Next mission uses a higher base ID so the server assigns increasing IDs.
    baseMissionId = (result.missionId ?? baseMissionId) + 2;
  }

  const ok = missions.every(m => m.mode === 'completed');
  console.log(JSON.stringify({ ok, missions }));
}

async function runOneMission(port, task, baseMissionId = 1) {
  const init = createInitialState(task);
  // The server requires missionId > 0 for NEW_TASK envelopes.
  // The adapter uses the store's missionId in wire envelopes.
  const store = createStore({ ...init, missionId: baseMissionId });
  let remoteLogs = 0;
  let missionId = null;
  const collabSet = new Set();

  const transport = createWsTransport(`ws://127.0.0.1:${port}`);

  // Wait for connection
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Connection timeout')), 10000);
    const unsub = transport.subscribe(msg => {
      if (msg?.type === 'CONNECTION' && msg.status === 'connected') {
        clearTimeout(timeout);
        unsub();
        resolve();
      }
    });
  });

  const adapter = createAdapter('ws', {
    ...store,
    transport,
    now: Date.now,
  });

  // Track events via transport listener (counts remote events)
  let resolveCompletion;
  const completionPromise = new Promise(r => { resolveCompletion = r; });

  const unsubEvents = transport.subscribe(msg => {
    if (!msg || msg.type === 'CONNECTION' || msg.type === 'ACK' || msg.type === 'REJECT') return;
    const event = decodeEvent(msg);
    if (!event) return;
    remoteLogs++;
    // Track the missionId from the actual running mission (latest event wins).
    missionId = event.missionId;
    if (event.type === 'collaboration') collabSet.add(event.payload.subtype);
    if (event.type === 'approval_request') {
      // Auto-approve after a short delay
      setTimeout(() => adapter.approve(), 50);
    }
    if (event.type === 'completion') {
      // Let remaining events settle, then resolve
      setTimeout(() => resolveCompletion(), 300);
    }
  });

  // Start the mission
  adapter.newTask(task);
      adapter.start();

  // Safety timeout
  const safetyTimeout = setTimeout(() => resolveCompletion(), 60000);
  await completionPromise;
  clearTimeout(safetyTimeout);

  unsubEvents();
  adapter.dispose();
  transport.dispose();

  const finalState = store.getState();
  const sim = finalState.simulation || finalState;
  const statuses = {};
  for (const agent of (sim.agents || [])) {
    statuses[agent.id] = agent.status;
  }

  return {
    task,
    missionId: missionId ?? finalState.missionId,
    stateTask: sim.task,
    finalMissionId: missionId ?? finalState.missionId,
    remoteLogs,
    collab: [...collabSet],
    mode: sim.mode,
    statuses,
    pendingCommands: (finalState.pendingCommands || []).length,
    connection: 'ws',
  };
}

// ─── main ───────────────────────────────────────────────────────────────────
if (mode === 'decode') {
  runDecode().catch(err => { console.error(err); process.exit(1); });
} else if (mode === 'e2e') {
  runE2E().catch(err => { console.error(err); process.exit(1); });
} else {
  console.error(`Unknown mode: ${mode}. Use "decode" or "e2e".`);
  process.exit(1);
}
