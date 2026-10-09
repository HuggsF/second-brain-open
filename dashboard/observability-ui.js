(function(){
'use strict';
const environments=['production','hml'];
let current;
function dispose(){if(current){current.cancelled=true;clearTimeout(current.timer);current=null;}}
function date(value){return Number.isFinite(value)?new Date(value*1000).toLocaleString('pt-BR'):'Ainda não disponível';}
// observedAt só é atribuído após o modelo validar envelope, duas amostras e datas.
// Estados unknown ainda podem representar indicadores parciais de uma observação válida.
function evaluatedObservation(model){return model.observation!==null&&model.nodes.every(node=>Number.isFinite(node.observedAt));}
function historicalState(environment,item){
 if(item?.error)return 'Coleta indisponível';
 const at=item?.collected_at,now=Date.now()/1000;
 const model=window.BrainHubTopology.project(environment,{environment,observation:item,last_attempt:item,collection_failed:false,stale:false},Number.isFinite(at)&&at<=now?at:NaN);
 if(!evaluatedObservation(model)||model.summary.status==='unknown')return 'Sem saúde comprovada na janela';
 return model.summary.status==='green'?'Saudável na janela':'Requer atenção';
}
function render(main,U){
 dispose();const {el,head,badge}=U;
 const session={cancelled:false,capabilityPending:false,targets:null,timer:null,states:new Map()};current=session;
 main.append(head('OPERAÇÃO','Observabilidade','Topologia interna de produção e homologação. Somente leitura; atualização do coletor a cada 60 segundos.'));
 const status=el('p',{class:'live-status',role:'status','aria-live':'polite'},'Conectando ao BFF local…');
 const body=el('div',{class:'live-grid'});main.append(status,body);
 const alive=()=>!session.cancelled&&current===session&&body.isConnected;
 function paint(environment){
  if(!alive())return;
  const state=session.states.get(environment),latest=state.latest;
  const projection=latest&&state.fetchFailed?{...latest,collection_failed:true}:latest;
  const model=window.BrainHubTopology.project(environment,projection,Date.now()/1000);
  const card=state.card,active=card.ownerDocument.activeElement;
  const focus=active&&card.contains(active)?{node:active.getAttribute('data-node-id'),view:active.getAttribute('data-view'),summary:active.tagName.toLowerCase()==='summary'?active.parentNode.className:null}:null;
  const listOpen=card.querySelector('.topology-list')?.open??false,historyOpen=card.querySelector('.live-history')?.open??false,metricsOpen=card.querySelector('.live-observed-metrics')?.open??true;
  const report=latest?.observation?.report,snapshots=report?.snapshots,sample=Array.isArray(snapshots)?snapshots.at(-1):null,db=sample?.database||{},process=sample?.process||{};
  const label=model.summary.status==='green'?'good':model.summary.status==='unknown'?'':'warn';
  const title=el('div',{class:'live-card-heading'},el('h2',{},environment==='production'?'Produção':'Homologação'),badge(model.summary.status==='green'?'Saudável na janela observada':model.summary.status==='unknown'?'Sem saúde atual comprovada':'Requer atenção',label));
  const topology=window.BrainHubTopologyUI.render(model,U,{selectedId:state.selected,onSelect:id=>{state.selected=id;}});
  card.replaceChildren(title,topology);topology.querySelector('.topology-list').open=listOpen;
  if(state.fetchFailed)card.append(el('p',{class:'live-warning'},state.invalidResponse?(latest?.observation?'Resposta de observabilidade incompatível. A última observação válida foi preservada como histórica.':'Resposta de observabilidade incompatível. Sem observação válida para este ambiente.'):'Consulta ao BFF indisponível ou sessão expirada. A topologia continua disponível.'));
  if(model.collection.status==='failed'||latest?.stale||model.nodes.some(node=>Number.isFinite(node.ageSeconds)&&node.ageSeconds>180))card.append(el('p',{class:'live-warning'},'A observação anterior foi preservada como histórica. Ela não comprova a saúde atual do serviço.'));
  if(state.lastFetchAt!==null)card.append(el('p',{class:'small muted'},'Última consulta da tela: '+date(state.lastFetchAt)));
  const metrics=el('details',{class:'live-observed-metrics',open:true},el('summary',{},'Indicadores da última observação'));
  metrics.append(el('p',{class:'small muted'},'Última coleta: '+date(latest?.observation?.collected_at)),el('p',{class:'small muted'},'Última tentativa do coletor: '+date(latest?.last_attempt?.collected_at)));
  const values=[['PM2',process.status??'—'],['Reinícios acumulados',process.restarts??'—'],['HTTP interno / externo',(sample?.internal?.status??'—')+' / '+(sample?.external?.status??'—')],['Banco legível',db.ok===true?'Sim':'Não comprovado'],['Fila pendente / processando / falha',[db.pending,db.processing,db.failed].map(v=>v??'—').join(' / ')],['Lojas automáticas',db.automaticShops??'—'],['Jobs sem objeto logístico / múltiplos volumes',[db.logisticsReviewJobs,db.multipleVolumeReviewJobs].map(v=>v??'Não disponível').join(' / ')],['Rate limits / demais erros (5 min)',[db.rateLimitsSinceDeploy,db.terminalErrorsSinceDeploy].map(v=>v??'—').join(' / ')],['Worker ativo',sample?.internal?.workerEnabled===true?'Sim':sample?.internal?.workerEnabled===false?'Não':'Não comprovado']];
  const list=el('dl',{class:'live-metrics'});for(const [label,value]of values)list.append(el('dt',{},label),el('dd',{},String(value)));metrics.append(list);
  metrics.append(el('p',{class:'small muted'},'SHA esperado: '+(report?.expected_sha??'—')),el('p',{class:'small muted'},'SHA interno: '+(sample?.internal?.revision??'—')));
  if(sample&&report.ok===false)metrics.append(el('p',{class:'live-warning'},'Verificações com alerta: '+(sample.failure_count??'Não disponível')+'. '+(Array.isArray(sample.failure_reasons)&&sample.failure_reasons.length?sample.failure_reasons.join(' '):'Conferir saúde, revisão, política de emissão, banco e erros.')));
  if(sample?.warning_count)metrics.append(el('p',{class:'live-warning'},'Avisos na última amostra: '+sample.warning_count+'. Confira os indicadores de rate limiting e as pendências do ambiente.'));
  metrics.open=metricsOpen;card.append(metrics);
  const history=el('details',{class:'live-history'},el('summary',{},'Histórico recente')),entries=el('ul');
  for(const item of state.history)entries.append(el('li',{},date(item?.collected_at)+' · '+historicalState(environment,item)));
  if(!state.history.length)entries.append(el('li',{class:'muted'},'Nenhuma coleta no histórico disponível.'));
  history.append(entries);if(state.historyFailed)history.append(el('p',{class:'small live-warning'},'Histórico atual indisponível. Entradas anteriores foram preservadas.'));history.open=historyOpen;card.append(history);
  if(focus?.node)topology.querySelector('[data-node-id='+JSON.stringify(focus.node)+'][data-view='+JSON.stringify(focus.view)+']')?.focus({preventScroll:true});
  else if(focus?.summary)card.querySelector('.'+focus.summary)?.querySelector('summary')?.focus({preventScroll:true});
 }
 function paintAll(){for(const environment of environments)paint(environment);}
 function summarize(){
  if(!alive())return;
  const states=[...session.states.values()],connected=states.filter(state=>!state.fetchFailed&&state.latest).length;
  status.textContent=connected===2?'Sessão autenticada · espaço KIOSK · histórico local de até 7 dias. Janela de erros: últimos 5 minutos. Não consulta pedidos no Bling ou J&T.':connected?'Observação disponível para um ambiente. O outro mantém a topologia e a última evidência local.':'BFF indisponível ou sessão expirada. Os mapas e as observações anteriores continuam disponíveis nesta tela.';
 }
 for(const environment of environments){
  const card=el('section',{class:'panel live-card','data-environment':environment});
  session.states.set(environment,{card,latest:null,history:[],selected:'process',fetchFailed:false,invalidResponse:false,historyFailed:false,lastFetchAt:null,latestPending:false,historyPending:false});body.append(card);
 }
 body.append(el('section',{class:'panel live-card live-next'},el('h2',{},'Próximas conexões'),el('p',{},'GraphRAG semântico e execução multiagente ainda não conectados. O daemon de observação é independente da ingestão do vault.'),el('p',{},'A consistência fiscal entre Hub, Bling e J&T precisa de auditoria específica. Saúde operacional não comprova reconciliação de etiquetas.')));
 paintAll();
 function refreshEnvironment(environment){
  const state=session.states.get(environment);
  if(!state.latestPending){
   state.latestPending=true;state.lastFetchAt=Date.now()/1000;
   (async()=>{
    let invalidResponse=false;
    try{
     const latest=await window.BrainLive.get('observability?environment='+environment);
     if(!alive())return;
     const retained=latest?.observation===null&&state.latest?.observation;
     const next=retained?{...latest,observation:state.latest.observation}:latest;
     const candidate=window.BrainHubTopology.project(environment,next,Date.now()/1000);
     invalidResponse=!latest||latest.environment!==environment||(next.observation!==null&&!evaluatedObservation(candidate));
     if(invalidResponse)throw new Error('Invalid observation envelope');
     state.latest=retained?{...next,collection_failed:true,stale:true}:next;
     state.fetchFailed=false;state.invalidResponse=false;
    }catch(_){if(!alive())return;state.fetchFailed=true;state.invalidResponse=invalidResponse;}
    finally{state.latestPending=false;}
    if(alive()){paint(environment);summarize();}
   })();
  }
  if(!state.historyPending){
   state.historyPending=true;
   (async()=>{
    try{
     const history=await window.BrainLive.get('observability/history?environment='+environment+'&limit=6');
     if(!alive())return;
     if(!history||history.environment!==environment||!Array.isArray(history.items))throw new Error('Invalid history envelope');
     state.history=history.items;state.historyFailed=false;
    }catch(_){if(!alive())return;state.historyFailed=true;}
    finally{state.historyPending=false;}
    if(alive())paint(environment);
   })();
  }
 }
 function refreshTargets(){
  if(!alive()||!session.targets)return;
  for(const environment of environments){
   if(session.targets.includes(environment))refreshEnvironment(environment);
   else{session.states.get(environment).fetchFailed=true;paint(environment);}
  }
 }
 function update(){
  if(!alive())return;
  paintAll();session.timer=setTimeout(update,15000);
  if(!session.capabilityPending){
   session.capabilityPending=true;
   (async()=>{
    try{
     const capability=await window.BrainLive.get('capabilities');
     if(!alive())return;
     const targets=capability?.observability?.targets;
     if(!Array.isArray(targets))throw new Error('Invalid capabilities');
     const firstTargets=session.targets===null;
     session.targets=targets.filter(environment=>environments.includes(environment));
     const rail=document.querySelector('.rail-bottom .small');if(rail)rail.textContent='Fontes locais · coletas por MCP';
     if(firstTargets)refreshTargets();
     summarize();
    }catch(_){
     if(!alive())return;
     if(!session.targets){
      for(const state of session.states.values()){state.fetchFailed=true;state.historyFailed=true;state.lastFetchAt=Date.now()/1000;}
      paintAll();summarize();
     }
    }finally{session.capabilityPending=false;}
   })();
  }
  refreshTargets();
 }
 update();
}
window.BrainObservability={render,dispose};
})();
