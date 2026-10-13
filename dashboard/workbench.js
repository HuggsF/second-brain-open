/* Functional local retrieval and plan preparation; no simulated agents or model answers. */
(function(){
'use strict';
function queries(main,U){
 const {el,button,badge,graph:G,core:C,head,notify}=U;
 let query=U.route.q||'',hops=U.route.hops||1,result=null;
 main.append(head('CONSULTAS / CONTEXTO','Encontre evidências, com o caminho até elas.','Busca textual com expansão das relações locais. Confira os trechos antes de formar uma conclusão.'));
 main.append(el('p',{class:'callout'},'Esta consulta recupera documentos e entidades do snapshot. Não utiliza embeddings, não gera uma resposta por IA e não chama serviços externos.'));
 const input=el('input',{type:'search',value:query,placeholder:'Ex.: como recuperar uma emissão incerta?','aria-label':'Pergunta ou termos de consulta',required:true,maxlength:500});
 const form=el('form',{class:'query-form'},el('label',{},'Pergunta ou termos',input),button('Recuperar evidências',()=>{},'primary'));
 form.querySelector('button').type='submit';
 const results=el('section',{'aria-label':'Resultados da consulta'}),history=el('aside',{class:'panel','aria-label':'Histórico de consultas'});
 function renderHistory(){
  history.replaceChildren(U.panelTitle('Histórico local','Últimas 12 consultas · neste navegador'));
  if(!U.saved.history.length)history.append(el('p',{class:'small muted'},'Suas consultas aparecem aqui após a recuperação.'));
  for(const entry of U.saved.history){
   history.append(el('div',{class:'history-item'},button(entry.query,()=>{input.value=entry.query;run(entry.query);},'row-link')));
  }
  if(U.saved.history.length)history.append(button('Limpar histórico',async()=>{if(!await U.confirmAction({title:'Limpar o histórico de consultas?',description:'As últimas consultas salvas neste navegador serão apagadas. Não há como desfazer.',confirmLabel:'Limpar histórico'}))return;U.saved.history=[];U.persist();renderHistory();notify('Histórico removido deste navegador.');},'subtle'));
  history.append(el('hr'),el('h3',{},'Como a recuperação funciona'),el('div',{class:'contract-list'},el('p',{},'1. Busca termos em títulos, entidades e texto completo.'),el('p',{},'2. Expande até dois saltos no catálogo curado.'),el('p',{},'3. Mostra fontes, linhas e hashes reais.'),el('p',{},'4. Registra lacunas; não preenche ausência com inferências.')));
 }
 function renderResults(){
  results.replaceChildren();
  if(!result){results.append(el('section',{class:'panel'},U.empty('Comece com uma pergunta','Você verá os trechos, as entidades relacionadas e as lacunas da recuperação.')));return;}
  const summary=el('section',{class:'panel'},U.panelTitle('Contexto recuperado',query,button('Exportar contexto',()=>U.exportJSON({...result,snapshot_id:G.snapshot_id,built_at:G.built_at},'kiosk-contexto.json'),'subtle')));
  summary.append(el('div',{class:'pipeline'},badge(result.seeds.length+' entidades iniciais','blue'),el('span',{'aria-hidden':true},'→'),badge(result.nodes.length+' entidades no contexto','accent'),el('span',{'aria-hidden':true},'→'),badge(result.citations.length+' fontes citadas','good')));
  if(result.nodes.length){
   summary.append(el('h3',{},'Entidades e relações recuperadas'));
   const tags=el('div',{class:'tag-row'});
   for(const id of result.nodes){const n=G.nodes.find(n=>n.id===id);if(n)tags.append(button(n.label,()=>U.navigate({page:'graph',node:id,view:Object.keys(n.views)[0],q:'',evidence:'all',focus:'1',hops}),'subtle'));}
   summary.append(tags);
   if(result.edges.length){
    const rels=el('details',{class:'toc'},el('summary',{},result.edges.length+' relações do catálogo'));
    for(const id of result.edges){const edge=G.edges.find(e=>e.id===id);if(!edge)continue;rels.append(U.row(G.nodes.find(n=>n.id===edge.source).label+' → '+G.nodes.find(n=>n.id===edge.target).label,edge.relation+' · '+(U.evidence[edge.evidence]||edge.evidence),()=>U.openDoc(edge.source_file)));}
    summary.append(rels);
   }
  }
  results.append(summary);
  if(!result.citations.length)results.append(el('section',{class:'panel'},U.empty('Nenhuma evidência textual encontrada','Refine os termos. O sistema não produziu uma resposta sem fontes.')));
  else for(const [index,citation] of result.citations.entries()){
   const card=el('article',{class:'citation-card'},el('div',{class:'tag-row'},badge('F'+(index+1),'blue'),badge('Linhas '+citation.lineStart+'–'+citation.lineEnd)),el('h3',{},U.documentTitle(citation.document)),el('p',{class:'citation-meta'},citation.section),el('pre',{},citation.text),el('details',{class:'provenance'},el('summary',{},citation.document+' · SHA-256 '+citation.sha256.slice(0,12)+'…'),el('code',{},citation.sha256)),button('Ler o trecho na fonte →',()=>U.openDoc(citation.document,citation.section,[citation.lineStart,citation.lineEnd]),'subtle'));
   results.append(card);
  }
  const gaps=el('section',{class:'panel'},U.panelTitle('Limites e lacunas','A recuperação mostra o que conseguiu comprovar.'));
  for(const gap of result.gaps)gaps.append(el('p',{class:'small muted'},gap));
  results.append(gaps);
 }
 function run(value){
  query=String(value).trim().slice(0,500);
  if(!query){notify('Digite uma pergunta ou termos específicos.');input.focus();return;}
  input.value=query;U.update({q:query,hops:String(hops)});
  result=C.retrieve(G,query,{limit:6,hops});
  U.saved.history=[{query,at:new Date().toISOString()},...U.saved.history.filter(h=>h.query!==query)].slice(0,12);U.persist();
  renderResults();renderHistory();notify(result.citations.length+' fontes recuperadas. Confira os trechos e as lacunas.');
 }
 form.addEventListener('submit',e=>{e.preventDefault();run(input.value);});
 main.append(el('section',{class:'panel'},form,el('div',{class:'action-row'},U.select('Expansão',[['1','1 salto'],['2','2 saltos']],String(hops),v=>{hops=Number(v);}),...['rastreio cancelado','rollback produção','múltiplos volumes'].map(q=>button(q,()=>run(q),'subtle')))));
 main.append(el('div',{class:'query-layout'},results,history));
 renderHistory();renderResults();
 if(query)run(query);
}
function agents(main,U){
 const {el,button,badge,head,core:C,notify}=U;
 const template=()=>({version:1,steps:[
  {id:'research',name:'Recuperar fontes e relações',role:'researcher',dependsOn:[],tools:['search','read_graph','read_sources'],budgetSeconds:60},
  {id:'review',name:'Verificar evidências e lacunas',role:'reviewer',dependsOn:['research'],tools:['read_sources'],budgetSeconds:90},
  {id:'write',name:'Consolidar decisão com citações',role:'writer',dependsOn:['review'],tools:['read_sources'],budgetSeconds:60}
 ]});
 let plan=U.saved.plan?structuredClone(U.saved.plan):template();
 main.append(head('PLANOS / AGENTES','Prepare o trabalho antes de executá-lo.','Defina papéis, dependências e ferramentas. Valide o plano e exporte um contrato para o futuro backend.'));
 main.append(el('p',{class:'callout warn'},'Backend de execução não conectado. As etapas abaixo são um plano editável, sem agentes em execução. Nenhum tempo, custo ou resultado foi simulado.'));
 const steps=el('div',{class:'plan-steps'}),message=el('div',{class:'plan-message',role:'status','aria-live':'polite'}),preview=el('pre',{class:'plan-preview','aria-label':'Contrato JSON do plano'}),diagram=el('ol',{class:'progress-list','aria-label':'Dependências do plano'});
 const roles=[
  ['dev','Desenvolvedor (Dev Full-Cycle)'],
  ['devops','DevOps / SRE'],
  ['qa','QA & Testes'],
  ['architect','Arquiteto / Tech Lead'],
  ['researcher','Pesquisador'],
  ['reviewer','Revisor'],
  ['writer','Redator']
 ];
 const toolNames={search:'Buscar texto',read_graph:'Ler relações',read_sources:'Ler fontes'};
 function check(announce=false){
  const valid=C.validatePlan(plan);
  message.replaceChildren();
  message.append(el('p',{class:'callout'+(valid.ok?'':' error')},valid.ok?'Plano válido · '+plan.steps.length+' etapas · '+plan.steps.reduce((sum,s)=>sum+s.budgetSeconds,0)+' segundos de orçamento configurado. Sem execução.':'O plano precisa de ajustes: '+valid.errors.join(' ')));
  preview.textContent=JSON.stringify(plan,null,2);
  diagram.replaceChildren(...plan.steps.map(step=>el('li',{},el('strong',{},step.name||step.id),el('span',{class:'muted small'},' · '+step.id+' · '+(step.dependsOn.length?'após '+step.dependsOn.join(', '):'sem dependências')))));
  U.saved.plan=structuredClone(plan);U.persist();
  if(announce)notify(valid.ok?'Contrato válido. Pronto para exportação local.':valid.errors[0]);
  return valid;
 }
 function renderSteps(){
  steps.replaceChildren();
  for(const [index,step] of plan.steps.entries()){
   const card=el('section',{class:'plan-step','aria-label':'Etapa '+(index+1)});
   card.append(el('div',{class:'plan-step-head'},el('h3',{},'Etapa '+(index+1)+' · '+step.id),button('Remover',()=>{
    plan.steps=plan.steps.filter(s=>s.id!==step.id);for(const s of plan.steps)s.dependsOn=s.dependsOn.filter(id=>id!==step.id);
    renderSteps();check();notify('Etapa removida. Suas dependências também foram retiradas.');
   },'subtle')));
   card.append(el('div',{class:'plan-step-fields'},el('label',{},'Nome da etapa '+(index+1),el('input',{value:step.name,maxlength:160,'aria-label':'Nome da etapa '+(index+1),oninput:e=>{step.name=e.target.value;check();}})),U.select('Papel da etapa '+(index+1),roles,step.role,v=>{step.role=v;check();}),el('label',{},'Orçamento em segundos '+(index+1),el('input',{type:'number',min:1,max:86400,value:step.budgetSeconds,'aria-label':'Orçamento em segundos '+(index+1),oninput:e=>{step.budgetSeconds=Number(e.target.value);check();}}))));
   const tools=el('fieldset',{class:'plan-step-deps'},el('legend',{class:'small muted'},'Ferramentas permitidas · etapa '+(index+1)));
   for(const [name,label] of Object.entries(toolNames))tools.append(el('label',{},el('input',{type:'checkbox',checked:step.tools.includes(name),onchange:e=>{step.tools=e.target.checked?[...step.tools,name]:step.tools.filter(t=>t!==name);check();}}),label));
   card.append(tools);
   const deps=el('fieldset',{class:'plan-step-deps'},el('legend',{class:'small muted'},'Depende de · etapa '+(index+1)));
   for(const candidate of plan.steps.filter(s=>s.id!==step.id))deps.append(el('label',{},el('input',{type:'checkbox',checked:step.dependsOn.includes(candidate.id),'aria-label':'Etapa '+step.id+' depende de '+candidate.id,onchange:e=>{step.dependsOn=e.target.checked?[...step.dependsOn,candidate.id]:step.dependsOn.filter(id=>id!==candidate.id);check();}}),candidate.id));
   if(plan.steps.length===1)deps.append(el('span',{class:'small muted'},'Adicione outra etapa para definir uma dependência.'));
   card.append(deps);steps.append(card);
  }
 }
 const file=el('input',{type:'file',accept:'.json,application/json','aria-label':'Importar plano JSON',onchange:async e=>{
  const selected=e.target.files[0];if(!selected)return;
  if(selected.size>1_000_000){notify('O plano ultrapassa o limite de 1 MB.');e.target.value='';return;}
  try{
   const candidate=JSON.parse(await selected.text()),valid=C.validatePlan(candidate);
   if(!valid.ok){notify('Importação recusada: '+valid.errors[0]+'. O plano atual foi preservado.');return;}
   plan={version:1,steps:candidate.steps.map(s=>({id:s.id,name:s.name,role:s.role,dependsOn:s.dependsOn,tools:s.tools,budgetSeconds:s.budgetSeconds}))};
   renderSteps();check();notify('Plano importado e validado localmente.');
  }catch(_){notify('JSON inválido. O plano atual foi preservado.');}
  finally{e.target.value='';}
 }});
 const actions=el('div',{class:'action-row'},button('+ Adicionar etapa',()=>{
  if(plan.steps.length>=100){notify('Limite de 100 etapas atingido.');return;}
  let num=plan.steps.length+1;while(plan.steps.some(s=>s.id==='step-'+num))num++;
  plan.steps.push({id:'step-'+num,name:'Nova etapa',role:'researcher',dependsOn:[],tools:['search'],budgetSeconds:60});renderSteps();check();
 },'primary'),button('Validar plano',()=>check(true),'subtle'),button('Exportar JSON',()=>{if(check().ok)U.exportJSON(plan,'kiosk-agent-plan.json');else notify('Corrija o plano antes de exportar.');},'subtle'),button('Restaurar modelo',()=>{plan=template();renderSteps();check();notify('Modelo restaurado.');},'subtle'));
 const editor=el('section',{class:'panel'},el('div',{class:'plan-top'},U.panelTitle('Plano de investigação','Contrato versionado · DAG'),badge('Execução indisponível','warn')),actions,message,steps,el('hr'),el('label',{},'Importar contrato local',file));
 const contract=el('aside',{class:'panel'},U.panelTitle('Caminho para execução real','Próximos contratos de integração'));
 contract.append(el('div',{class:'readiness'},el('div',{},el('strong',{},'Preparação local'),badge('Disponível','good')),el('div',{},el('strong',{},'Backend multiagente'),badge('Não conectado','warn')),el('div',{},el('strong',{},'GraphRAG semântico'),badge('Não conectado','warn')),el('div',{},el('strong',{},'Observabilidade por MCP'),el('a',{href:'#page=observability'},'Consultar última coleta'))));
 contract.append(el('div',{class:'contract-list'},el('p',{},el('strong',{},'1. Adapter HTTP + BFF'), ' · autenticação e fontes autorizadas por espaço.'),el('p',{},el('strong',{},'2. Recuperação híbrida'), ' · texto, vetores, grafo e citações rastreáveis.'),el('p',{},el('strong',{},'3. Orquestrador durável'), ' · DAG, budgets, cancelamento e eventos SSE.'),el('p',{},el('strong',{},'4. Ferramentas isoladas'), ' · allowlist e aprovação vinculada à ação.')));
 contract.append(el('hr'),el('h3',{},'Dependências configuradas'),diagram,el('hr'),el('details',{class:'toc'},el('summary',{},'Ver contrato JSON'),preview),button('Copiar contrato',()=>U.copy(JSON.stringify(plan,null,2)),'subtle'),el('p',{class:'legend-note'},el('a',{href:'analysis/graphrag-multiagent-contract.md'},'Ler arquitetura e contrato de evolução')));
 main.append(el('div',{class:'query-layout'},editor,contract));
 renderSteps();check();
}
window.BrainWorkbench=Object.freeze({render(main,U){if(U.route.page==='queries')queries(main,U);else agents(main,U);}});
})();
