import assert from 'node:assert/strict';
import test from 'node:test';
const api = await import('../src/reducer.js').catch(e => { if(e.code === 'ERR_MODULE_NOT_FOUND') return null; throw e; });
function initial(){ assert.ok(api, 'Reducer ainda ausente'); return api.createInitialState('Missão', 1000); }
function act(s,type,payload,now=2000){ return api.simulationReducer(s,{type,payload,now}); }
function gate(){ let s=act(initial(),'START'); for(let i=0;i<10;i++) s=act(s,'TICK'); return s; }
test('estado inicial usa timestamp explícito e permanece idle',()=>{ const s=initial(); assert.equal(s.simulation.logs[0].at,1000); assert.equal(s.missionId,0); assert.equal(s.simulation.mode,'idle'); });
test('START invalida geração somente no ciclo novo',()=>{ let s=act(initial(),'START'); assert.equal(s.missionId,1); assert.equal(act(s,'START'),s); s=act(s,'PAUSE'); assert.equal(act(s,'START').missionId,1); });
test('TICK usa tempo da action e ignora geração antiga',()=>{ const s=act(initial(),'START'); const n=act(s,'TICK',undefined,5000); assert.equal(n.simulation.tick,1); assert.equal(n.simulation.logs[0].at,5000); assert.equal(api.simulationReducer(n,{type:'TICK',now:6000,missionId:0}),n); });
test('PAUSE congela e RESUME preserva geração',()=>{ const s=act(act(initial(),'START'),'PAUSE'); assert.equal(act(s,'TICK'),s); const n=act(s,'RESUME'); assert.equal(n.simulation.mode,'running'); assert.equal(n.missionId,s.missionId); });
test('aprovação pausada libera gate sem retomar',()=>{ const s=act(act(gate(),'PAUSE'),'APPROVE'); assert.equal(s.simulation.mode,'paused'); assert.equal(s.simulation.needsApproval,false); assert.equal(act(s,'TICK'),s); });
test('RESET limpa métricas e invalida geração',()=>{ const s=act(act(initial(),'START'),'TICK'); const n=act(s,'RESET'); assert.equal(n.missionId,2); assert.equal(n.simulation.tick,0); assert.equal(n.simulation.task,'Missão'); });
test('NEW_TASK limpa seleção e fecha diálogo com nova geração',()=>{ let s=act(initial(),'SELECT_AGENT','coder'); s=act(s,'OPEN_TASK'); const n=act(s,'NEW_TASK',' Nova missão '); assert.equal(n.missionId,1); assert.equal(n.simulation.task,'Nova missão'); assert.equal(n.selectedId,null); assert.equal(n.taskOpen,false); });
test('seleção aceita agente e null mas rejeita desconhecido',()=>{ const s=initial(); assert.equal(act(s,'SELECT_AGENT','unknown'),s); assert.equal(act(act(s,'SELECT_AGENT','coder'),'SELECT_AGENT',null).selectedId,null); });
test('velocidade só aceita 1 ou 2',()=>{ const s=initial(); assert.equal(act(s,'SET_SPEED',3),s); assert.equal(act(s,'SET_SPEED',2).speed,2); });
test('movimento manual e do SO são independentes',()=>{ let s=act(initial(),'TOGGLE_MOTION'); s=act(s,'SET_SYSTEM_MOTION',true); assert.equal(s.manualReducedMotion,true); assert.equal(s.systemReducedMotion,true); assert.equal(act(s,'TOGGLE_MOTION').systemReducedMotion,true); });
test('diálogo abre e fecha sem mudar missão',()=>{ const s=act(initial(),'OPEN_TASK'); assert.equal(s.taskOpen,true); assert.equal(act(s,'CLOSE_TASK').taskOpen,false); assert.equal(s.missionId,0); });
test('ações inválidas e tempo ausente são inertes',()=>{ const s=initial(); for(const a of [null,{}, {type:'START'}, {type:'NEW_TASK',payload:42,now:1},{type:'SET_SYSTEM_MOTION',payload:'yes'}]) assert.equal(api.simulationReducer(s,a),s); });
test('reducer mantém snapshot congelado intacto',()=>{ const s=initial(); function freeze(v){ if(v&&typeof v==='object'){Object.freeze(v); Object.values(v).forEach(freeze);} } freeze(s); const n=act(s,'START'); n.simulation.agents[0].memory.push('novo'); assert.equal(s.simulation.agents[0].memory.length,2); });
test('START após término aumenta geração e reinicia trabalho',()=>{ let s=act(gate(),'APPROVE'); for(let i=0;i<3;i++)s=act(s,'TICK'); const n=act(s,'START'); assert.equal(n.missionId,2); assert.equal(n.simulation.tick,0); });
test('payload interno malformado não substitui workspace',()=>{const s=initial();assert.equal(act(s,'PROTOCOL_STATE',{simulation:{},missionId:0}),s);});
