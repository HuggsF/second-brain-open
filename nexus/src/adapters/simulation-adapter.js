import { simulationReducer } from '../reducer.js';
import { decodeEvent, createEventGate, createCommandLedger, queueCommand, settleCommand } from './event-protocol.js';

/** bindings: dispatch(action), getState(), subscribe(callback), optional now/transport. */
export function createAdapter(mode = 'local', bindings) {
  if (!bindings || !['dispatch','getState','subscribe'].every(k => typeof bindings[k] === 'function')) throw new TypeError('State bindings required');
  if (!['local','ws','sse'].includes(mode)) throw new TypeError('Unknown adapter mode');
  const transport = bindings.transport;
  if (mode !== 'local' && (!transport || typeof transport.send !== 'function' || typeof transport.subscribe !== 'function')) throw new TypeError('Injected event and command transport required');
  const now = bindings.now || Date.now;
  const stateListeners = new Set(), eventListeners = new Set(), seen = new Set();
  let disposed = false, serial = 0, eventMission = bindings.getState().missionId;
  let wireGate = createEventGate(eventMission);
  let ledger = createCommandLedger(bindings.getState(), eventMission);
  let journal = [];
  let publishing = false;
  let observedWorkspace = bindings.getState();
  const unchanged = state => state;
  // The protocol ledger validates/settles commands. The journal preserves their
  // causal position relative to events, including events before confirmation.
  function replayJournal() {
    let confirmed = ledger.confirmed;
    while (journal.length && (journal[0].kind === 'event' || journal[0].resolution)) {
      const entry = journal.shift();
      if (entry.resolution !== 'REJECT') confirmed = simulationReducer(confirmed,entry.action);
    }
    const optimistic = journal.reduce((state,entry) => entry.resolution === 'REJECT'
      ? state : simulationReducer(state,entry.action),confirmed);
    ledger = { ...ledger,confirmed,optimistic };
  }
  function settle(reply) {
    const next = settleCommand(ledger,reply,unchanged);
    if (next === ledger) return false;
    ledger = next;
    journal = journal.map(entry => entry.commandId === reply.commandId
      ? {...entry,resolution:reply.type} : entry);
    replayJournal();
    return true;
  }
  function emit(event, missionId) {
    if (seen.has(event.id)) return;
    seen.add(event.id);
    if (seen.size > 512) seen.delete(seen.values().next().value);
    for (const callback of eventListeners) callback(structuredClone(event), missionId);
  }
  const unsubscribeState = bindings.subscribe(workspace => {
    if (disposed) return;
    const externalMotorChange = !publishing && mode !== 'local' &&
      (workspace.simulation !== observedWorkspace.simulation || workspace.missionId !== observedWorkspace.missionId);
    observedWorkspace = workspace;
    if (externalMotorChange) {
      // Direct Context engine transitions supersede the optimistic command
      // branch. Cancel it rather than replay old operations over the new state.
      ledger = createCommandLedger(workspace,workspace.missionId,ledger.revision);
      journal = [];
      if (workspace.pendingCommands.length) { publish(); return; }
    }
    if (workspace.missionId !== eventMission) {
      eventMission = workspace.missionId; seen.clear(); wireGate = createEventGate(eventMission);
    }
    for (const callback of stateListeners) callback(workspace);
    for (const event of workspace.simulation.collabEvents || []) if (!event.consumed) emit(event, workspace.missionId);
  });
  function publish(uiOverrides = {}) {
    const current = bindings.getState();
    const currentGeneration = current.missionId;
    if (ledger.optimistic.missionId < currentGeneration) {
      // A rejected optimistic cycle is canceled permanently, even though its
      // engine snapshot rolls back. Its visual generation must never return.
      const generation = currentGeneration + 1;
      ledger = { ...ledger, confirmed:{...ledger.confirmed,missionId:generation}, optimistic:{...ledger.optimistic,missionId:generation} };
      journal = [];
    }
    const controls = Object.fromEntries(['selectedId','speed','manualReducedMotion','systemReducedMotion','taskOpen']
      .map(key => [key,current[key]]));
    publishing = true;
    try {
      bindings.dispatch({ type: 'PROTOCOL_STATE', payload: { ...ledger.optimistic,...controls,...uiOverrides,
        connection: { mode, status: 'connected', error: null }, pendingCommands: ledger.pending.map(c => ({...c})) } });
    } finally { publishing = false; }
  }
  const unsubscribeTransport = mode === 'local' ? null : transport.subscribe(input => {
    if (disposed) return;
    if (input?.type === 'ACK' || input?.type === 'REJECT') {
      // A later mission cancels all commands from the former generation.
      if (bindings.getState().missionId !== ledger.optimistic.missionId) return;
      if (settle(input)) publish();
      return;
    }
    const event = decodeEvent(input);
    if (!event || !wireGate(event)) return;
    const action = { type:'REMOTE_EVENT',payload:event };
    if (ledger.pending.length && bindings.getState().missionId === ledger.optimistic.missionId) {
      journal.push({kind:'event',action});
      if (journal.filter(entry => entry.kind === 'event').length > 120) {
        journal.splice(journal.findIndex(entry => entry.kind === 'event'),1);
      }
      replayJournal();
      publish();
    } else bindings.dispatch(action);
  });
  function command(type,payload) {
    if (disposed) return;
    const action = { type, payload, now: now() };
    if (mode === 'local') { bindings.dispatch(action); return; }
    const current = bindings.getState();
    if (type === 'RESET' || type === 'NEW_TASK' || !ledger.pending.length || current.missionId !== ledger.optimistic.missionId) {
      ledger = createCommandLedger(current,current.missionId,ledger.revision);
      journal = [];
    }
    const envelope = { schemaVersion: 1, commandId: `command:${ledger.missionId}:${++serial}`, missionId: ledger.missionId, action };
    const next = queueCommand(ledger,envelope,unchanged);
    if (next === ledger) return;
    ledger = next;
    journal.push({kind:'command',commandId:envelope.commandId,action});
    replayJournal();
    const uiOverrides = type === 'NEW_TASK' ? {selectedId:null,taskOpen:false} : type === 'RESET' ? {selectedId:null} : {};
    publish(uiOverrides);
    try { transport.send(envelope); }
    catch (error) {
      settle({type:'REJECT',commandId:envelope.commandId,missionId:envelope.missionId,revision:ledger.revision+1});
      publish();
      bindings.dispatch({type:'PROTOCOL_STATE',payload:{...bindings.getState(),connection:{mode,status:'error',error:String(error.message || error)}}});
    }
  }
  function listen(collection,callback) {
    if (disposed || typeof callback !== 'function') return () => {};
    collection.add(callback); return () => collection.delete(callback);
  }
  return {
    start(task) { if (task !== undefined) { if (typeof task !== 'string' || !task.trim()) return; command('NEW_TASK',task); } command('START'); },
    pause: () => command('PAUSE'), resume: () => command('RESUME'), approve: () => command('APPROVE'),
    reset: () => command('RESET'), tick: () => command('TICK'),
    onStateChange: callback => listen(stateListeners,callback), onCollabEvent: callback => listen(eventListeners,callback),
    dispose() { if (disposed) return; disposed = true; unsubscribeState(); unsubscribeTransport?.(); stateListeners.clear(); eventListeners.clear(); seen.clear(); }
  };
}
