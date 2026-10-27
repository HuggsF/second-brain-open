import assert from 'node:assert/strict';
import test from 'node:test';
const mod=await import('../src/adapters/simulation-adapter.js').catch(e=>{if(e.code==='ERR_MODULE_NOT_FOUND')return null;throw e;});
const reducer=await import('../src/reducer.js').catch(e=>{if(e.code==='ERR_MODULE_NOT_FOUND')return null;throw e;});
function store(){assert.ok(reducer,'Reducer ausente');let state=reducer.createInitialState('x',0);const listeners=new Set();return {now:()=>100, getState:()=>state,dispatch(a){state=reducer.simulationReducer(state,a);listeners.forEach(f=>f(state));},subscribe(f){listeners.add(f);return()=>listeners.delete(f);},listeners};}
test('adapter local delega estado, dedup por geração e dispose',()=>{assert.ok(mod,'Adapter ausente');const b=store();const a=mod.createAdapter('local',b);let states=0,events=[];a.onStateChange(()=>states++);a.onCollabEvent((e,m)=>events.push([e.id,m]));a.start();a.pause();a.resume();assert.equal(states,3);assert.equal(events.length,1);a.reset();a.start();assert.equal(events.length,2);assert.equal(events[1][1],3);a.dispose();b.dispatch({type:'PAUSE',now:200});assert.equal(states,5);assert.equal(b.listeners.size,0);});
test('ws exige transporte injetado e faz rollback de comando rejeitado',()=>{assert.ok(mod,'Adapter ausente');const b=store();assert.throws(()=>mod.createAdapter('ws',b));let receive;let sent=[];const a=mod.createAdapter('ws',{...b,transport:{send(c){sent.push(c);},subscribe(f){receive=f;return()=>{receive=null;};}}});a.start();assert.equal(b.getState().simulation.mode,'running');receive({type:'REJECT',commandId:sent[0].commandId,missionId:sent[0].missionId,revision:1});assert.equal(b.getState().simulation.mode,'idle');assert.equal(b.getState().pendingCommands.length,0);a.dispose();assert.equal(receive,null);});
test('eventos remotos atualizam estado e rejeitam geração antiga',()=>{assert.ok(mod);const b=store();let receive;const a=mod.createAdapter('sse',{...b,transport:{send(){},subscribe(f){receive=f;return()=>{};}}});receive({schemaVersion:1,id:'e',missionId:0,sequence:1,agentId:'coder',type:'status_change',payload:{status:'working',progress:30},timestamp:50});assert.equal(b.getState().simulation.agents.find(a=>a.id==='coder').progress,30);b.dispatch({type:'RESET',now:100});receive({schemaVersion:1,id:'e2',missionId:0,sequence:2,agentId:'coder',type:'status_change',payload:{status:'done',progress:100},timestamp:200});assert.equal(b.getState().simulation.agents.find(a=>a.id==='coder').progress,0);a.dispose();});
test('rollback não reutiliza geração cancelada',()=>{assert.ok(mod);const b=store();let receive,sent;const a=mod.createAdapter('ws',{...b,transport:{send(c){sent=c;},subscribe(f){receive=f;return()=>{};}}});a.start();const generation=b.getState().missionId;receive({type:'REJECT',commandId:sent.commandId,missionId:sent.missionId,revision:1});assert.ok(b.getState().missionId>generation);a.dispose();});
test('start com tarefa inválida não inicia missão antiga',()=>{const b=store();const a=mod.createAdapter('local',b);a.start(42);assert.equal(b.getState().simulation.mode,'idle');a.dispose();});
test('reset invalida comandos pendentes da geração anterior',()=>{const b=store();let receive;const sent=[];const a=mod.createAdapter('ws',{...b,transport:{send(c){sent.push(c);},subscribe(f){receive=f;return()=>{};}}});a.start();a.reset();assert.equal(b.getState().pendingCommands.length,1);assert.equal(b.getState().pendingCommands[0].action.type,'RESET');const before=b.getState();receive({type:'ACK',commandId:sent[0].commandId,missionId:sent[0].missionId,revision:1});assert.equal(b.getState(),before);a.dispose();});
test('evento antes do ACK não se perde no replay',()=>{const b=store();let receive,sent;const a=mod.createAdapter('ws',{...b,transport:{send(c){sent=c;},subscribe(f){receive=f;return()=>{};}}});a.start();receive({schemaVersion:1,id:'early',missionId:1,sequence:1,agentId:'coder',type:'status_change',payload:{status:'working',progress:30},timestamp:50});assert.equal(b.getState().simulation.agents[2].progress,30);receive({type:'ACK',commandId:sent.commandId,missionId:sent.missionId,revision:1});assert.equal(b.getState().simulation.agents[2].progress,30);a.dispose();});

function remoteRunning() {
  const bindings = store();
  bindings.dispatch({ type: 'START', now: 1 });
  const sent = [];
  let receive;
  const adapter = mod.createAdapter('ws', {
    ...bindings,
    transport: {
      send(command) { sent.push(command); },
      subscribe(callback) { receive = callback; return () => {}; },
    },
  });
  return {
    bindings, adapter, sent,
    receive(message) { receive(message); },
    reply(index, revision) {
      receive({ type: 'ACK', commandId: sent[index].commandId, missionId: sent[index].missionId, revision });
    },
    status(sequence, progress) {
      receive({ schemaVersion: 1, id: `remote-${sequence}`, missionId: 1, sequence,
        agentId: 'researcher', type: 'status_change', payload: { status: 'working', progress }, timestamp: 150 });
    },
  };
}

test('ACK preserva controles UI alterados externamente durante pendência', () => {
  const { bindings, adapter, reply } = remoteRunning();
  adapter.pause();
  for (const action of [
    { type: 'SET_SPEED', payload: 2 },
    { type: 'SELECT_AGENT', payload: 'coder' },
    { type: 'TOGGLE_MOTION' },
    { type: 'SET_SYSTEM_MOTION', payload: true },
    { type: 'OPEN_TASK' },
  ]) bindings.dispatch(action);
  reply(0, 1);
  const current = bindings.getState();
  assert.equal(current.speed, 2);
  assert.equal(current.selectedId, 'coder');
  assert.equal(current.manualReducedMotion, true);
  assert.equal(current.systemReducedMotion, true);
  assert.equal(current.taskOpen, true);
  assert.equal(current.simulation.mode, 'paused');
  adapter.dispose();
});

test('transição externa do motor cancela pendência anterior e ACK não a desfaz', () => {
  const { bindings, adapter, reply } = remoteRunning();
  adapter.pause();
  bindings.dispatch({ type: 'RESUME', now: 200 });
  assert.equal(bindings.getState().pendingCommands.length, 0);
  reply(0, 1);
  assert.equal(bindings.getState().simulation.mode, 'running');
  adapter.dispose();
});

test('status remoto após TICK pendente prevalece antes e depois do ACK', () => {
  const { bindings, adapter, status, reply } = remoteRunning();
  adapter.tick();
  status(1, 88);
  assert.equal(bindings.getState().simulation.agents[1].progress, 88);
  reply(0, 1);
  assert.equal(bindings.getState().simulation.tick, 1);
  assert.equal(bindings.getState().simulation.agents[1].progress, 88);
  adapter.dispose();
});

test('TICK posterior ao evento remoto mantém ordem causal em ambos os ACKs', () => {
  const { bindings, adapter, status, reply } = remoteRunning();
  adapter.tick();
  status(1, 88);
  adapter.tick();
  assert.equal(bindings.getState().simulation.agents[1].progress, 35);
  reply(0, 1);
  assert.equal(bindings.getState().simulation.agents[1].progress, 35);
  reply(1, 2);
  assert.equal(bindings.getState().simulation.tick, 2);
  assert.equal(bindings.getState().simulation.agents[1].progress, 35);
  adapter.dispose();
});
