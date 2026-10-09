(function(){
'use strict';
let timer;
function dispose(){clearTimeout(timer);}
function render(main,U){
 dispose();const {el,head,badge}=U;
 main.append(head('OPERAÇÃO','Observabilidade','Coletas de produção e homologação por MCP. Somente leitura; atualização do coletor a cada 60 segundos.'));
 const status=el('p',{role:'status','aria-live':'polite'},'Conectando ao BFF local…');
 const body=el('div',{class:'live-grid'});main.append(status,body);
 const date=v=>v?new Date(v*1000).toLocaleString('pt-BR'):'Ainda não disponível';
 async function update(){
  if(!body.isConnected)return;
  try{
   const capability=await window.BrainLive.get('capabilities');
   const results=await Promise.all(capability.observability.targets.map(async environment=>({environment,latest:await window.BrainLive.get('observability?environment='+environment),history:await window.BrainLive.get('observability/history?environment='+environment+'&limit=6')})));
   if(!body.isConnected)return;
   const rail=document.querySelector('.rail-bottom .small');if(rail)rail.textContent='Fontes locais · coletas por MCP';
   status.textContent='Sessão autenticada · espaço KIOSK · histórico local de até 7 dias. Janela de erros: últimos 5 minutos. Não consulta pedidos no Bling ou J&T.';
   body.replaceChildren();
   for(const {environment,latest,history} of results){
    const report=latest.observation?.report,sample=report?.snapshots.at(-1),db=sample?.database||{},process=sample?.process||{};
    const card=el('section',{class:'panel live-card'},el('h2',{},environment==='production'?'Produção':'Homologação'),badge(window.BrainLive.state(latest),latest.stale||latest.collection_failed||!report?.ok?'warn':'good'));
    card.append(el('p',{class:'small muted'},'Última coleta: '+date(latest.observation?.collected_at)),el('p',{class:'small muted'},'Última tentativa: '+date(latest.last_attempt?.collected_at)));
    if(latest.collection_failed||latest.stale)card.append(el('p',{class:'live-warning'},'A observação anterior foi preservada. Ela não comprova a saúde atual do serviço.'));
    const metrics=[['PM2',process.status??'—'],['Reinícios acumulados',process.restarts??'—'],['HTTP interno / externo',(sample?.internal?.status??'—')+' / '+(sample?.external?.status??'—')],['Banco legível',db.ok===true?'Sim':'Não comprovado'],['Fila pendente / processando / falha',[db.pending,db.processing,db.failed].map(v=>v??'—').join(' / ')],['Lojas automáticas',db.automaticShops??'—'],['Jobs sem objeto logístico / múltiplos volumes',[db.logisticsReviewJobs,db.multipleVolumeReviewJobs].map(v=>v??'Não disponível').join(' / ')],['Rate limits / demais erros (5 min)',[db.rateLimitsSinceDeploy,db.terminalErrorsSinceDeploy].map(v=>v??'—').join(' / ')],['Worker ativo',sample?.internal?.workerEnabled===true?'Sim':sample?.internal?.workerEnabled===false?'Não':'Não comprovado']];
    const list=el('dl',{class:'live-metrics'});for(const [label,value]of metrics)list.append(el('dt',{},label),el('dd',{},String(value)));card.append(list);
    card.append(el('p',{class:'small muted'},'SHA esperado: '+(report?.expected_sha??'—')),el('p',{class:'small muted'},'SHA interno: '+(sample?.internal?.revision??'—')));
    if(sample&&!report.ok)card.append(el('p',{class:'live-warning'},'Verificações com alerta: '+sample.failure_count+'. '+(sample.failure_reasons?.length?sample.failure_reasons.join(' '):'Conferir saúde, revisão, política de emissão, banco e erros.')));
    if(sample?.warning_count)card.append(el('p',{class:'live-warning'},'Avisos na última amostra: '+sample.warning_count+'. Confira os indicadores de rate limiting e as pendências do ambiente.'));
    const details=el('details',{},el('summary',{},'Histórico recente'));const entries=el('ul');
    for(const item of history.items)entries.append(el('li',{},date(item.collected_at)+' · '+(item.error?'Coleta indisponível':item.report.ok?'Saudável na janela':'Requer atenção')));details.append(entries);card.append(details);body.append(card);
   }
   body.append(el('section',{class:'panel live-card'},el('h2',{},'Próximas conexões'),el('p',{},'GraphRAG semântico e execução multiagente ainda não conectados. O daemon de observação é independente da ingestão do vault.'),el('p',{},'A consistência fiscal entre Hub, Bling e J&T precisa de auditoria específica. Saúde operacional não comprova reconciliação de etiquetas.')));
  }catch(error){if(body.isConnected){status.textContent=error.message;body.replaceChildren(el('p',{class:'live-warning'},'Sem observabilidade atual comprovada. A biblioteca e os planos locais continuam disponíveis.'));}}
  if(body.isConnected)timer=setTimeout(update,15000);
 }
 update();
}
window.BrainObservability={render,dispose};
})();
