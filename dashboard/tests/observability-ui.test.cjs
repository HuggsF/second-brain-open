'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),{dom,find}=require('./topology-dom.cjs');
function latest(environment='production',at=1000,ok=true) {
 const sample={ok,at:new Date(at*1000).toISOString(),process:{status:ok?'online':'stopped',restarts:2},internal:{status:'ok',environment,revision:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',workerEnabled:environment==='production',emissionEnabled:environment==='production'},external:{status:'ok',environment,revision:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',workerEnabled:environment==='production',emissionEnabled:environment==='production'},database:{ok:true,pending:3,processing:environment==='production'?1:0,failed:0,automaticShops:environment==='production'?2:0,logisticsReviewJobs:0,multipleVolumeReviewJobs:0,rateLimitsSinceDeploy:0,terminalErrorsSinceDeploy:0},failure_count:0,failure_reasons:[],warning_count:0};
 return {schema_version:1,space_id:'kiosk',environment,observation:{id:7,collected_at:at,report:{environment,expected_sha:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',ok,snapshots:[structuredClone(sample),structuredClone(sample)]}},last_attempt:{id:7,collected_at:at,report:{ok},error:null},collection_failed:false,stale:false,age_seconds:0};
}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
async function settle(){for(let i=0;i<12;i++)await Promise.resolve();}
function harness(get,project=require('../hub-topology.js').project) {
 const view=dom();let now=1000,nextTimer=0;const timers=new Map();const window={BrainLive:{get,state:data=>data.collection_failed?'Falha na coleta':data.observation?'Saudável na janela observada':'Sem coleta'},BrainHubTopology:{project},localStorage:{setItem(){throw new Error('Reports must remain in memory');}}};
 const context=vm.createContext({window,document:view.document,Date:class extends Date {static now(){return now*1000;}},setTimeout:(callback,delay)=>{const id=++nextTimer;timers.set(id,{callback,delay});return id;},clearTimeout:id=>timers.delete(id)});
 if(fs.existsSync(path.join(__dirname,'../hub-topology-ui.js')))vm.runInContext(fs.readFileSync(path.join(__dirname,'../hub-topology-ui.js'),'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../observability-ui.js'),'utf8'),context);
 return {...view,window,timers,setNow:value=>now=value,tick:async()=>{const scheduled=[...timers.values()];timers.clear();for(const task of scheduled)task.callback();await settle();}};
}
function environmentCard(main,environment){return find(main,item=>item.getAttribute('data-environment')===environment&&item.className.includes('live-card'))[0];}
function aspect(card,id){return find(card,item=>item.getAttribute('data-node-id')===id&&item.getAttribute('data-view')==='map')[0];}
function success(path){if(path==='capabilities')return Promise.resolve({observability:{targets:['production','hml']}});const environment=path.includes('environment=hml')?'hml':'production';return Promise.resolve(path.includes('/history')?{environment,items:[{collected_at:999,error:null,report:{ok:true}}]}:latest(environment));}
test('offline render keeps both environment maps visible without a prior collection',async()=>{
 const h=harness(()=>Promise.reject(new Error('arbitrary server message')));h.window.BrainObservability.render(h.main,h.U);
 assert.ok(environmentCard(h.main,'production'),'Production map should render before network');assert.ok(environmentCard(h.main,'hml'));
 await settle();for(const environment of ['production','hml']){const card=environmentCard(h.main,environment);assert.ok(aspect(card,'process'));assert.match(card.textContent,/Desconhecido/);}assert.doesNotMatch(h.main.textContent,/arbitrary server message/);
});
test('one unavailable environment leaves the other metrics and history visible',async()=>{
 const h=harness(path=>path.includes('environment=hml')?Promise.reject(new Error('unavailable')):success(path));h.window.BrainObservability.render(h.main,h.U);await settle();
 const prod=environmentCard(h.main,'production'),hml=environmentCard(h.main,'hml');assert.ok(prod);assert.ok(hml);assert.match(prod.textContent,/Saudável/);assert.match(prod.textContent,/Reinícios acumulados/);assert.match(prod.textContent,/3 \/ 1 \/ 0/);assert.match(prod.textContent,/Histórico recente/);assert.match(hml.textContent,/Desconhecido/);
});
test('HTTP or session loss preserves last observed failure as yellow history',async()=>{
 let online=true;const h=harness(path=>online?(path.includes('/history')||path==='capabilities'?success(path):Promise.resolve(latest(path.includes('hml')?'hml':'production',1000,false))):Promise.reject(new Error('session expired')));
 h.window.BrainObservability.render(h.main,h.U);await settle();assert.match(aspect(environmentCard(h.main,'production'),'process').textContent,/Falha observada/);
 online=false;h.setNow(1015);await h.tick();const prod=environmentCard(h.main,'production');assert.match(aspect(prod,'process').textContent,/Atenção/);assert.match(prod.textContent,/histórica|anterior/);assert.match(prod.textContent,/Reinícios acumulados/);assert.match(prod.textContent,/Histórico recente/);assert.doesNotMatch(h.main.textContent,/session expired/);
});
test('uncompleted poll still ages cached observations past 180 seconds',async()=>{
 let pending=false;const blocked=deferred(),h=harness(path=>pending?blocked.promise:success(path));h.window.BrainObservability.render(h.main,h.U);await settle();h.setNow(1180);pending=true;await h.tick();assert.match(aspect(environmentCard(h.main,'production'),'process').textContent,/Saudável/);
 h.setNow(1181);await h.tick();assert.match(aspect(environmentCard(h.main,'production'),'process').textContent,/Atenção/);h.window.BrainObservability.dispose();blocked.resolve(latest());await settle();
});
test('history failure cannot discard a new valid observation',async()=>{
 const h=harness(path=>path.includes('/history')?Promise.reject(new Error('history down')):success(path));h.window.BrainObservability.render(h.main,h.U);await settle();const prod=environmentCard(h.main,'production');assert.match(aspect(prod,'process').textContent,/Saudável/);assert.match(prod.textContent,/Reinícios acumulados/);assert.match(prod.textContent,/Histórico.*indisponível|histórico.*indisponível/);
});
test('dispose ignores pending responses and prevents restarting timers',async()=>{
 const blocked=deferred(),h=harness(()=>blocked.promise);h.window.BrainObservability.render(h.main,h.U);const before=h.main.textContent;h.window.BrainObservability.dispose();blocked.resolve({observability:{targets:['production','hml']}});await settle();assert.equal(h.main.textContent,before);assert.equal(h.timers.size,0);
});
test('rendering a second view cannot be overwritten by the first request',async()=>{
 const old=deferred();let first=true;const h=harness(path=>{if(first){first=false;return old.promise;}return success(path);});h.window.BrainObservability.render(h.main,h.U);h.main.replaceChildren();h.window.BrainObservability.render(h.main,h.U);await settle();const before=h.main.textContent;old.reject(new Error('OLD VIEW ERROR'));await settle();assert.equal(h.main.textContent,before);assert.equal(h.timers.size,1);
});
test('poll preserves keyboard focus and expanded lists for the selected aspect',async()=>{
 const h=harness(success);h.window.BrainObservability.render(h.main,h.U);await settle();let prod=environmentCard(h.main,'production');const list=find(prod,item=>item.className==='topology-list')[0],history=find(prod,item=>item.className==='live-history')[0];list.open=true;history.open=true;const selected=find(list,item=>item.tagName==='button'&&item.getAttribute('data-node-id')==='database')[0];selected.focus();selected.press('Enter');h.setNow(1015);await h.tick();prod=environmentCard(h.main,'production');assert.equal(h.document.activeElement.isConnected,true);assert.equal(h.document.activeElement.getAttribute('data-node-id'),'database');assert.equal(h.document.activeElement.getAttribute('data-view'),'list');assert.equal(find(prod,item=>item.className==='topology-list')[0].open,true);assert.equal(find(prod,item=>item.className==='live-history')[0].open,true);
});

test('pending hml requests do not block new production observations',async()=>{
 const blocked=deferred();let productionReads=0;const h=harness(path=>{
  if(path==='observability?environment=hml')return blocked.promise;
  if(path==='observability?environment=production'){productionReads++;const value=latest('production',productionReads===1?1000:1015);for(const sample of value.observation.report.snapshots)sample.process.restarts=productionReads===1?2:8;return Promise.resolve(value);}
  return success(path);
 });
 h.window.BrainObservability.render(h.main,h.U);await settle();h.setNow(1015);await h.tick();const prod=environmentCard(h.main,'production'),metrics=find(prod,item=>item.className==='live-metrics')[0],terms=metrics.children;const index=terms.findIndex(item=>item.textContent==='Reinícios acumulados');assert.equal(terms[index+1].textContent,'8');h.window.BrainObservability.dispose();blocked.resolve(latest('hml'));await settle();
});
test('pending history does not block later current observations',async()=>{
 const blocked=deferred();let reads=0;const h=harness(path=>{
  if(path.includes('/history'))return blocked.promise;
  if(path==='observability?environment=production'){reads++;const value=latest('production',reads===1?1000:1015);for(const sample of value.observation.report.snapshots)sample.process.restarts=reads===1?2:9;return Promise.resolve(value);}
  return success(path);
 });
 h.window.BrainObservability.render(h.main,h.U);await settle();h.setNow(1015);await h.tick();const metrics=find(environmentCard(h.main,'production'),item=>item.className==='live-metrics')[0],index=metrics.children.findIndex(item=>item.textContent==='Reinícios acumulados');assert.equal(metrics.children[index+1].textContent,'9');h.window.BrainObservability.dispose();blocked.resolve({environment:'production',items:[]});await settle();
});

function metricValue(card,label){
 const metrics=find(card,item=>item.className==='live-metrics')[0],index=metrics.children.findIndex(item=>item.textContent===label);
 return metrics.children[index+1].textContent;
}
for(const [name,mutate]of [
 ['future sample timestamp',value=>{for(const sample of value.observation.report.snapshots)sample.at=1016;}],
 ['invalid sample timestamp',value=>{value.observation.report.snapshots[0].at='invalid-date';}],
 ['future collection timestamp',value=>{value.observation.collected_at=1016;}],
 ['invalid collection timestamp',value=>{value.observation.collected_at='1015';}],
 ['negative collection timestamp',value=>{value.observation.collected_at=-1;}],
 ['incomplete snapshots',value=>{value.observation.report.snapshots.pop();}],
 ['invalid snapshot',value=>{value.observation.report.snapshots[0]=null;}],
 ['invalid aggregate assessment',value=>{value.observation.report.ok='true';}],
 ['divergent envelope environment',value=>{value.environment='hml';}],
 ['divergent report environment',value=>{value.observation.report.environment='hml';}]
]){
 test(name+' cannot replace the last valid observation with unvalidated metrics',async()=>{
  let newer=false;const h=harness(path=>{
   if(path!=='observability?environment=production')return success(path);
   const value=latest('production',newer?1015:1000,!newer?false:true);
   if(newer){for(const sample of value.observation.report.snapshots)sample.process.restarts=9;mutate(value);}
   return Promise.resolve(value);
  });
  h.window.BrainObservability.render(h.main,h.U);await settle();assert.match(aspect(environmentCard(h.main,'production'),'process').textContent,/Falha observada/);
  newer=true;h.setNow(1015);await h.tick();const prod=environmentCard(h.main,'production');
  assert.equal(metricValue(prod,'Reinícios acumulados'),'2');assert.match(aspect(prod,'process').textContent,/Atenção/);assert.match(prod.textContent,/histórica|histórico/);
  const details=find(prod,item=>item.getAttribute('data-topology-details')==='true')[0];assert.match(details.textContent,/stopped/);assert.match(details.textContent,/Estado PM2/);assert.match(prod.textContent,/Resposta de observabilidade incompatível/);h.window.BrainObservability.dispose();
 });
}
test('legitimate insufficient indicators replace the cache with unknown evidence',async()=>{
 let newer=false;const h=harness(path=>{
  if(path!=='observability?environment=production')return success(path);
  const value=latest('production',newer?1015:1000,!newer?false:true);
  if(newer)value.observation.report.snapshots=[0,1].map(()=>({ok:true,at:1015,process:{restarts:9},internal:{},external:{},database:{},failure_count:0,warning_count:0}));
  return Promise.resolve(value);
 });
 h.window.BrainObservability.render(h.main,h.U);await settle();newer=true;h.setNow(1015);await h.tick();const prod=environmentCard(h.main,'production');
 assert.equal(metricValue(prod,'Reinícios acumulados'),'9');for(const id of ['process','internal','external','database'])assert.match(aspect(prod,id).textContent,/Desconhecido/);assert.doesNotMatch(prod.textContent,/Resposta de observabilidade incompatível|preservada como histórica/);h.window.BrainObservability.dispose();
});
test('historical warnings require attention even when aggregate report ok is true',async()=>{
 const historical=latest('production').observation;for(const sample of historical.report.snapshots){sample.warning_count=1;sample.database.rateLimitsSinceDeploy=2;}
 const h=harness(path=>path==='observability/history?environment=production&limit=6'?Promise.resolve({environment:'production',items:[historical]}):success(path));
 h.window.BrainObservability.render(h.main,h.U);await settle();const history=find(environmentCard(h.main,'production'),item=>item.className==='live-history')[0];
 assert.match(history.textContent,/Requer atenção/);assert.doesNotMatch(history.textContent,/Saudável na janela/);h.window.BrainObservability.dispose();
});
test('history distinguishes normal collected evidence from insufficient reports without aging it today',async()=>{
 const normal=latest('production',900).observation,insufficient={collected_at:901,report:{ok:true}};
 const h=harness(path=>path==='observability/history?environment=production&limit=6'?Promise.resolve({environment:'production',items:[normal,insufficient]}):success(path));h.setNow(2000);
 h.window.BrainObservability.render(h.main,h.U);await settle();const history=find(environmentCard(h.main,'production'),item=>item.className==='live-history')[0],entries=find(history,'li');
 assert.match(entries[0].textContent,/Saudável na janela/);assert.match(entries[1].textContent,/Sem saúde comprovada/);h.window.BrainObservability.dispose();
});

for(const [name,metadata]of [
 ['future attempt',{last_attempt:{id:8,collected_at:1016,error:'SOURCE_UNAVAILABLE'}}],
 ['invalid attempt timestamp',{last_attempt:{id:8,collected_at:'1015',error:'SOURCE_UNAVAILABLE'}}],
 ['negative attempt timestamp',{last_attempt:{id:8,collected_at:-1,error:'SOURCE_UNAVAILABLE'}}],
 ['invalid attempt shape',{last_attempt:'invalid'}],
 ['invalid collection flag',{collection_failed:'true'}],
 ['invalid stale flag',{stale:'true'}]
]){
 test('missing observation with '+name+' preserves validated history and checks',async()=>{
  let newer=false;const h=harness(path=>{
   if(path!=='observability?environment=production')return success(path);
   return Promise.resolve(newer?{environment:'production',observation:null,last_attempt:{id:8,collected_at:1015,error:'SOURCE_UNAVAILABLE'},collection_failed:true,stale:true,...metadata}:latest('production',1000,false));
  });
  h.window.BrainObservability.render(h.main,h.U);await settle();newer=true;h.setNow(1015);await h.tick();const prod=environmentCard(h.main,'production');
  assert.match(aspect(prod,'process').textContent,/Atenção/);assert.equal(metricValue(prod,'Reinícios acumulados'),'2');assert.match(find(prod,item=>item.getAttribute('data-topology-details')==='true')[0].textContent,/stopped/);assert.match(prod.textContent,/Resposta de observabilidade incompatível/);h.window.BrainObservability.dispose();
 });
}
for(const lastAttempt of [{id:8,collected_at:1015,error:'SOURCE_UNAVAILABLE'},null]){
 test('missing observation with '+(lastAttempt?'valid attempt':'no attempt')+' keeps valid previous evidence as history',async()=>{
  let newer=false;const h=harness(path=>path==='observability?environment=production'?Promise.resolve(newer?{environment:'production',observation:null,last_attempt:lastAttempt,collection_failed:true,stale:true}:latest('production',1000,false)):success(path));
  h.window.BrainObservability.render(h.main,h.U);await settle();newer=true;h.setNow(1015);await h.tick();const prod=environmentCard(h.main,'production');
  assert.match(aspect(prod,'process').textContent,/Atenção/);assert.equal(metricValue(prod,'Reinícios acumulados'),'2');assert.match(find(prod,item=>item.getAttribute('data-topology-details')==='true')[0].textContent,/stopped/);assert.doesNotMatch(prod.textContent,/Resposta de observabilidade incompatível/);h.window.BrainObservability.dispose();
 });
}
