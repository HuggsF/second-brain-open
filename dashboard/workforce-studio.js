/* Workforce Studio — Drop & Grill demand refinement
   Pattern: window.BrainWorkforceStudio.render(main, U)
   U is the shared api object from app.js */
(function(root){
'use strict';

/* ── Agent Personas ──────────────────────────────────────── */
const AGENTS=[
  {id:'discovery',  icon:'🔍',name:'Discovery Lead',  phase:'discovery'},
  {id:'spec',       icon:'📋',name:'Product Spec',     phase:'spec'},
  {id:'architect',  icon:'📐',name:'Architect',        phase:'architecture'},
  {id:'planner',    icon:'🗂️',name:'SDD Planner',      phase:'planning'},
  {id:'implementer',icon:'⚡',name:'TDD Engine',       phase:'implementation'},
  {id:'harness',    icon:'🛡️',name:'QA Harness',       phase:'validation'},
  {id:'docs',       icon:'📄',name:'Doc & Sync',       phase:'documentation'},
];

/* ── Pipeline Stages ─────────────────────────────────────── */
const STAGES=[
  {id:'drop',           label:'Drop Ideia',      mark:'💡',agent:null},
  {id:'discovery',      label:'RAG Brain',       mark:'🔍',agent:'discovery'},
  {id:'spec',           label:'Spec Gate',       mark:'📋',agent:'spec'},
  {id:'architecture',   label:'ADR / Contrato',  mark:'📐',agent:'architect'},
  {id:'planning',       label:'SDD Plan',        mark:'🗂️',agent:'planner'},
  {id:'implementation', label:'TDD',             mark:'⚡',agent:'implementer'},
  {id:'validation',     label:'Harness',         mark:'🛡️',agent:'harness'},
  {id:'documentation',  label:'PR & Sync',       mark:'📄',agent:'docs'},
];

/* ── PRD Sections (from prd-feature-template.md) ─────────── */
const PRD_SECTIONS=[
  {id:'summary',       title:'1. Resumo Executivo',          required:true},
  {id:'context',       title:'2. Contexto e Problema',       required:true},
  {id:'objectives',    title:'3. Objetivos e Métricas',      required:true},
  {id:'scope',         title:'4. Escopo (In/Out)',            required:true},
  {id:'requirements',  title:'5. Requisitos Funcionais',     required:true},
  {id:'nfr',           title:'6. Requisitos Não-Funcionais', required:false},
  {id:'architecture',  title:'7. Arquitetura Proposta',      required:false},
  {id:'decisions',     title:'8. Decisões e Trade-offs',     required:false},
  {id:'dependencies',  title:'9. Dependências',              required:false},
  {id:'risks',         title:'10. Riscos e Mitigações',      required:false},
  {id:'acceptance',    title:'11. Critérios de Aceitação',   required:true},
  {id:'invariants',    title:'12. Invariantes Negativos',    required:true},
];

/* ── Question Templates ──────────────────────────────────── */
function generateQuestions(rawText){
  const questions=[];
  // Stakeholder / business questions
  questions.push({id:'q-business-1', target:'operacao', targetLabel:'🏢 Operação / Stakeholder',
    text:'Qual o objetivo de negócio principal desta demanda? Quem é o usuário final e qual dor resolve?', section:'summary'});
  questions.push({id:'q-business-2', target:'operacao', targetLabel:'🏢 Operação / Stakeholder',
    text:'Qual o cenário atual (como funciona hoje)? E qual o cenário desejado após a implementação?', section:'context'});
  questions.push({id:'q-business-3', target:'operacao', targetLabel:'🏢 Operação / Stakeholder',
    text:'Quais métricas de sucesso podemos medir? (ex: tempo reduzido, taxa de erro, volume processado)', section:'objectives'});
  questions.push({id:'q-business-4', target:'operacao', targetLabel:'🏢 Operação / Stakeholder',
    text:'Quais sistemas e atores estão envolvidos? (ex: Hub, Bling, J&T, Corpem, SAP, ERP)', section:'context'});
  // Technical / integration questions
  questions.push({id:'q-tech-1', target:'fornecedor', targetLabel:'🔌 Fornecedor / Integração',
    text:'Quais são os contratos de entrada e saída esperados? (Campos do JSON/XML, endpoints, formatos)', section:'requirements'});
  questions.push({id:'q-tech-2', target:'fornecedor', targetLabel:'🔌 Fornecedor / Integração',
    text:'Existe documentação de API ou especificação técnica do fornecedor/sistema externo?', section:'dependencies'});
  // Architecture decisions
  questions.push({id:'q-arch-1', target:'arquitetura', targetLabel:'📐 Decisão de Arquitetura',
    text:'O que acontece em caso de falha? (timeout, serviço indisponível, payload inválido, rate limit)', section:'risks'});
  questions.push({id:'q-arch-2', target:'arquitetura', targetLabel:'📐 Decisão de Arquitetura',
    text:'O que esta funcionalidade NUNCA deve fazer? (invariantes negativos — ex: nunca reprocessar sem cancelar)', section:'invariants'});
  // Scope
  questions.push({id:'q-scope-1', target:'operacao', targetLabel:'🏢 Operação / Stakeholder',
    text:'O que está FORA do escopo desta demanda? O que fica para uma próxima fase?', section:'scope'});
  // Acceptance
  questions.push({id:'q-accept-1', target:'arquitetura', targetLabel:'📐 Decisão de Arquitetura',
    text:'Quais são os critérios mínimos para considerar esta demanda "pronta" e entregue?', section:'acceptance'});
  return questions;
}

/* ── Storage key ─────────────────────────────────────────── */
const STORAGE_KEY='kiosk.workforce.v1';

function loadState(){
  try{
    const raw=localStorage.getItem(STORAGE_KEY);
    if(!raw)return {demands:[],activeDemandId:null};
    const parsed=JSON.parse(raw);
    if(parsed && Array.isArray(parsed.demands))return parsed;
  }catch(_){}
  return {demands:[],activeDemandId:null};
}

function saveState(state){
  try{localStorage.setItem(STORAGE_KEY,JSON.stringify(state));}catch(_){}
}

function newDemand(rawText){
  const id='DEM-DRAFT-'+Date.now().toString(36).toUpperCase();
  const questions=generateQuestions(rawText);
  return {
    id, title:'', rawText:rawText||'', createdAt:new Date().toISOString(),
    updatedAt:new Date().toISOString(),
    currentPhase:'drop', dorScore:0,
    questions:questions.map(q=>({...q,answer:'',answeredAt:null})),
    prd:Object.fromEntries(PRD_SECTIONS.map(s=>[s.id,''])),
  };
}

function computeDoR(demand){
  const sections=PRD_SECTIONS;
  const requiredSections=sections.filter(s=>s.required);
  const filledRequired=requiredSections.filter(s=>(demand.prd[s.id]||'').trim().length>10).length;
  const totalQuestions=demand.questions.length;
  const answeredQuestions=demand.questions.filter(q=>(q.answer||'').trim().length>3).length;
  // 60% weight on required PRD sections filled, 40% on answered questions
  const sectionScore=requiredSections.length?filledRequired/requiredSections.length:0;
  const questionScore=totalQuestions?answeredQuestions/totalQuestions:0;
  return Math.round((sectionScore*0.6+questionScore*0.4)*100);
}

function computePhase(demand){
  const score=demand.dorScore;
  if(!demand.rawText)return 'drop';
  if(score<20)return 'discovery';
  if(score<50)return 'spec';
  if(score<70)return 'architecture';
  if(score<85)return 'planning';
  if(score<95)return 'implementation';
  if(score<100)return 'validation';
  return 'documentation';
}

function dorColor(score){
  if(score>=85)return 'var(--good)';
  if(score>=50)return 'var(--warn)';
  return 'var(--danger)';
}

/* ── Main render ─────────────────────────────────────────── */
function render(main,U){
  const {el,button,badge,head,panelTitle,notify,select,exportJSON,copy,row,confirmAction}=U;
  let state=loadState();

  function save(){saveState(state);}

  /* ── Demand selector / creator ─────────────────────────── */
  function renderDemandBar(container){
    container.replaceChildren();
    const bar=el('div',{class:'wf-demand-list'});
    for(const d of state.demands){
      const pill=el('button',{class:'wf-demand-pill',type:'button','aria-pressed':String(d.id===state.activeDemandId),
        onclick:()=>{state.activeDemandId=d.id;save();renderAll();}},
        (d.title||d.id),el('span',{class:'wf-demand-score'},d.dorScore+'%'));
      bar.append(pill);
    }
    bar.append(button('+ Nova demanda',()=>{
      const d=newDemand('');
      state.demands.push(d);state.activeDemandId=d.id;save();renderAll();
    },'primary'));
    container.append(bar);
  }

  function getActive(){return state.demands.find(d=>d.id===state.activeDemandId);}

  /* ── Squad bar ─────────────────────────────────────────── */
  function renderSquad(container,demand){
    container.replaceChildren();
    const squad=el('div',{class:'wf-squad'});
    for(const agent of AGENTS){
      const stageIndex=STAGES.findIndex(s=>s.id===agent.phase);
      const currentIndex=STAGES.findIndex(s=>s.id===(demand?.currentPhase||'drop'));
      let agentState='locked';
      if(stageIndex<currentIndex)agentState='done';
      else if(stageIndex===currentIndex)agentState=demand?.dorScore>=85?'active':'waiting';
      const card=el('div',{class:'wf-agent-card','data-active':String(agentState==='active'),'data-waiting':String(agentState==='waiting')},
        el('span',{class:'wf-agent-icon','aria-hidden':'true'},agent.icon),
        el('div',{class:'wf-agent-info'},
          el('span',{class:'wf-agent-name'},agent.name),
          el('span',{class:'wf-agent-status','data-state':agentState},
            agentState==='done'?'✓ Concluído':agentState==='active'?'● Ativo':agentState==='waiting'?'▲ Aguardando':'○ Em espera')));
      squad.append(card);
    }
    container.append(squad);
  }

  /* ── Pipeline ──────────────────────────────────────────── */
  function renderPipeline(container,demand){
    container.replaceChildren();
    const pipe=el('div',{class:'wf-pipeline'});
    const currentIndex=STAGES.findIndex(s=>s.id===(demand?.currentPhase||'drop'));
    for(const [i,stage] of STAGES.entries()){
      if(i>0)pipe.append(el('div',{class:'wf-pipeline-edge','data-done':String(i<=currentIndex)}));
      let nodeState='locked';
      if(i<currentIndex)nodeState='done';
      else if(i===currentIndex)nodeState='active';
      const node=el('button',{class:'wf-pipeline-node',type:'button','data-state':nodeState,
        onclick:()=>{notify(stage.label+' — '+(nodeState==='done'?'Etapa concluída':nodeState==='active'?'Etapa atual':'Aguardando etapas anteriores'));}},
        el('span',{class:'wf-pipeline-mark','aria-hidden':'true'},nodeState==='done'?'✓':stage.mark),
        el('span',{class:'wf-pipeline-label'},stage.label));
      pipe.append(node);
    }
    container.append(pipe);
  }

  /* ── DoR bar ───────────────────────────────────────────── */
  function renderDoR(container,demand){
    container.replaceChildren();
    const score=demand?.dorScore||0;
    const color=dorColor(score);
    const status=score>=85?'✅ Pronta para desenvolvimento':score>=50?'⚠️ Em refinamento (bloqueada para código)':'🔴 Incompleta — responda as perguntas';
    const bar=el('div',{class:'wf-dor'},
      el('span',{class:'wf-dor-label'},'Definition of Ready'),
      el('div',{class:'wf-dor-track'},el('div',{class:'wf-dor-fill',style:'width:'+score+'%;background:'+color})),
      el('span',{class:'wf-dor-pct',style:'color:'+color},score+'%'));
    container.append(bar,el('p',{class:'small',style:'color:'+color+';padding:0 0 4px'},status));
  }

  /* ── Questions pane ────────────────────────────────────── */
  function renderQuestions(container,demand){
    container.replaceChildren();
    if(!demand){container.append(el('p',{class:'small muted'},'Crie ou selecione uma demanda.'));return;}
    const pane=el('div',{class:'wf-questions'});
    // Group by target
    const groups={operacao:[],fornecedor:[],arquitetura:[]};
    for(const q of demand.questions)(groups[q.target]||[]).push(q);
    for(const [target,qs] of Object.entries(groups)){
      if(!qs.length)continue;
      for(const q of qs){
        const answered=!!(q.answer||'').trim();
        const card=el('div',{class:'wf-question-card','data-answered':String(answered)});
        card.append(el('span',{class:'wf-question-target','data-target':target},q.targetLabel));
        card.append(el('p',{class:'wf-question-text'},q.text));
        if(answered){
          card.append(el('div',{class:'wf-answer-saved'},'✓ '+q.answer));
          card.append(button('Editar resposta',()=>{q.answer='';q.answeredAt=null;updateDemand(demand);renderAll();},'subtle'));
        }else{
          const input=el('textarea',{class:'wf-answer-input',placeholder:'Sua resposta…','aria-label':'Resposta para: '+q.text,rows:2});
          const submit=el('button',{class:'wf-answer-btn',type:'button',onclick:()=>{
            const val=input.value.trim();
            if(!val){notify('Digite uma resposta antes de confirmar.');return;}
            q.answer=val;q.answeredAt=new Date().toISOString();
            // Auto-fill PRD section
            if(q.section && demand.prd[q.section]!==undefined){
              demand.prd[q.section]=(demand.prd[q.section]?demand.prd[q.section]+'\n\n':'')+'> **'+q.targetLabel+'**: '+val;
            }
            updateDemand(demand);renderAll();
            notify('Resposta registrada. DoR atualizado para '+demand.dorScore+'%.');
          }},'Confirmar');
          card.append(el('div',{class:'wf-answer-row'},input,submit));
        }
        pane.append(card);
      }
    }
    container.append(pane);
  }

  /* ── Live doc pane ─────────────────────────────────────── */
  function renderDocPane(container,demand){
    container.replaceChildren();
    if(!demand){container.append(el('p',{class:'small muted'},'Nenhuma demanda selecionada.'));return;}
    const pane=el('div',{class:'wf-doc-pane'});

    // Tabs
    let activeTab='prd';
    const tabBar=el('div',{class:'wf-doc-tabs'});
    const tabContent=el('div',{});
    function setTab(tab){
      activeTab=tab;
      for(const btn of tabBar.children)btn.setAttribute('aria-selected',String(btn.dataset.tab===tab));
      renderTabContent();
    }
    for(const [tab,label] of [['prd','📄 PRD Viva'],['gates','🚦 Gates de Validação'],['export','📦 Exportar']]){
      tabBar.append(el('button',{class:'wf-doc-tab',type:'button','data-tab':tab,'aria-selected':String(tab===activeTab),
        onclick:()=>setTab(tab)},label));
    }

    function renderTabContent(){
      tabContent.replaceChildren();
      if(activeTab==='prd'){
        // PRD sections
        const title=el('h2',{},'PRD: '+(demand.title||demand.id));
        tabContent.append(title);
        for(const section of PRD_SECTIONS){
          const content=demand.prd[section.id]||'';
          const filled=content.trim().length>10;
          const sec=el('div',{class:'wf-doc-section','data-filled':String(filled)},
            el('div',{class:'wf-doc-section-title'},
              el('span',{},filled?'✓':'○'),section.title,section.required?badge('Obrigatório','warn'):''),
            el('div',{class:'wf-doc-section-body'},content||''));
          // Allow direct editing
          sec.addEventListener('click',()=>{
            const existing=demand.prd[section.id]||'';
            const textarea=el('textarea',{class:'wf-answer-input',rows:4,value:existing,placeholder:'Preencha '+section.title+'…'});
            const saveBtn=el('button',{class:'wf-answer-btn',type:'button',onclick:()=>{
              demand.prd[section.id]=textarea.value;updateDemand(demand);renderAll();notify(section.title+' atualizada.');
            }},'Salvar');
            const dialog=el('dialog',{class:'confirm-dialog','aria-label':'Editar '+section.title},
              el('h2',{},section.title),textarea,el('div',{class:'action-row'},button('Cancelar',()=>dialog.close(),'subtle'),saveBtn));
            dialog.addEventListener('close',()=>dialog.remove());
            document.body.append(dialog);dialog.showModal();textarea.focus();
          });
          tabContent.append(sec);
        }
      }else if(activeTab==='gates'){
        tabContent.append(el('h2',{},'Gates de Validação'));
        const gates=el('div',{class:'wf-gates'});
        const checks=[
          {label:'Resumo Executivo preenchido', ok:!!(demand.prd.summary||'').trim()},
          {label:'Contexto e Problema definido', ok:!!(demand.prd.context||'').trim()},
          {label:'Escopo delimitado (in/out)',   ok:!!(demand.prd.scope||'').trim()},
          {label:'Requisitos Funcionais escritos',ok:!!(demand.prd.requirements||'').trim()},
          {label:'Invariantes Negativos declarados',ok:!!(demand.prd.invariants||'').trim()},
          {label:'Critérios de Aceitação definidos',ok:!!(demand.prd.acceptance||'').trim()},
          {label:'DoR Score ≥ 85%',              ok:demand.dorScore>=85},
          {label:'Todas as perguntas respondidas',ok:demand.questions.every(q=>(q.answer||'').trim())},
        ];
        for(const check of checks){
          gates.append(el('div',{class:'wf-gate','data-ok':String(check.ok)},
            el('span',{class:'wf-gate-mark'},check.ok?'✓':'○'),
            el('span',{class:'wf-gate-label'},check.label)));
        }
        tabContent.append(gates);
        if(demand.dorScore>=85){
          tabContent.append(el('p',{class:'callout'},'🎉 Demanda pronta para geração de Briefs SDD e execução pelo Workforce.'));
          tabContent.append(button('Aprovar & Gerar Briefs SDD →',()=>{
            notify('Demanda aprovada! Geração de briefs SDD seria disparada aqui (backend não conectado).');
          },'primary'));
        }else{
          tabContent.append(el('p',{class:'callout warn'},'Responda as perguntas pendentes para desbloquear a execução. Score atual: '+demand.dorScore+'%.'));
        }
      }else if(activeTab==='export'){
        tabContent.append(el('h2',{},'Exportar Demanda'));
        const md=generateMarkdown(demand);
        tabContent.append(el('pre',{style:'font-size:12px;max-height:400px;overflow:auto;white-space:pre-wrap;background:var(--bg);padding:14px;border-radius:8px'},md));
        tabContent.append(el('div',{class:'action-row'},
          button('Copiar Markdown',()=>copy(md),'subtle'),
          button('Exportar JSON',()=>exportJSON(demand,demand.id+'.json'),'subtle')));
      }
    }
    pane.append(tabBar,tabContent);
    renderTabContent();
    container.append(pane);
  }

  function generateMarkdown(demand){
    let md='---\ntype: demand-draft\nid: '+demand.id+'\ntitle: '+(demand.title||'Sem título')+'\ndor_score: '+demand.dorScore+'\nstatus: '+(demand.dorScore>=85?'ready':'refining')+'\ncreated: '+demand.createdAt+'\nupdated: '+demand.updatedAt+'\n---\n# PRD: '+(demand.title||demand.id)+'\n\n';
    md+='> **Input original:** '+demand.rawText+'\n\n';
    for(const section of PRD_SECTIONS){
      md+='## '+section.title+'\n'+(demand.prd[section.id]||'_Aguardando informação._')+'\n\n';
    }
    md+='---\n## Perguntas e Respostas\n\n';
    for(const q of demand.questions){
      md+='- **'+q.targetLabel+'**: '+q.text+'\n';
      md+='  - _Resposta:_ '+(q.answer||'Pendente')+'\n\n';
    }
    return md;
  }

  function updateDemand(demand){
    demand.dorScore=computeDoR(demand);
    demand.currentPhase=computePhase(demand);
    demand.updatedAt=new Date().toISOString();
    save();
  }

  /* ── Brain dump (initial input) ────────────────────────── */
  function renderBrainDump(container,demand){
    container.replaceChildren();
    if(!demand){return;}
    const dump=el('div',{class:'wf-braindump'});
    const textarea=el('textarea',{placeholder:'Cole aqui qualquer coisa: uma ideia, um erro, uma mensagem do WhatsApp, uma necessidade que ouviu na empresa…\n\nExemplo: "Precisamos ajustar a integração da Corpem para Recife. O Tadeu falou que agora precisa mandar código da transportadora antes de faturar no Bling."',rows:4,value:demand.rawText||''});
    const titleInput=el('input',{type:'text',placeholder:'Título curto da demanda (ex: Integração Corpem Recife)',value:demand.title||'','aria-label':'Título da demanda',style:'min-height:44px;background:var(--bg);color:var(--text);border:1px solid var(--field-border);border-radius:8px;padding:10px 12px;font:inherit;width:100%'});
    const actions=el('div',{class:'wf-braindump-actions'},
      button('Salvar & Analisar',()=>{
        demand.rawText=textarea.value.trim();
        demand.title=titleInput.value.trim()||demand.id;
        if(!demand.rawText){notify('Descreva a demanda antes de analisar.');return;}
        // Auto-fill summary from raw text
        if(!(demand.prd.summary||'').trim()){demand.prd.summary=demand.rawText;}
        updateDemand(demand);renderAll();
        notify('Demanda registrada! Responda as perguntas para aumentar o DoR.');
      },'primary'),
      button('Limpar',async()=>{
        if(!await confirmAction({title:'Limpar esta demanda?',description:'O texto e todas as respostas serão apagados.',confirmLabel:'Limpar'}))return;
        demand.rawText='';demand.title='';demand.prd=Object.fromEntries(PRD_SECTIONS.map(s=>[s.id,'']));
        demand.questions.forEach(q=>{q.answer='';q.answeredAt=null;});
        updateDemand(demand);renderAll();notify('Demanda limpa.');
      },'subtle'));
    // Delete demand button
    if(state.demands.length>0){
      actions.append(button('Excluir demanda',async()=>{
        if(!await confirmAction({title:'Excluir '+demand.id+'?',description:'A demanda e todas as respostas serão removidas permanentemente.',confirmLabel:'Excluir'}))return;
        state.demands=state.demands.filter(d=>d.id!==demand.id);
        state.activeDemandId=state.demands[0]?.id||null;
        save();renderAll();notify('Demanda excluída.');
      },'danger'));
    }
    dump.append(el('label',{},'Título',titleInput),el('label',{},'Brain Dump — sua ideia, erro ou necessidade',textarea),actions);
    container.append(dump);
  }

  /* ── Full render orchestration ─────────────────────────── */
  const demandBar=el('div',{});
  const squadEl=el('div',{});
  const pipelineEl=el('div',{});
  const dorEl=el('div',{});
  const brainDumpEl=el('section',{class:'panel'});
  const questionsEl=el('div',{});
  const docPaneEl=el('div',{});

  function renderAll(){
    const demand=getActive();
    renderDemandBar(demandBar);
    renderSquad(squadEl,demand);
    renderPipeline(pipelineEl,demand);
    renderDoR(dorEl,demand);
    renderBrainDump(brainDumpEl,demand);
    renderQuestions(questionsEl,demand);
    renderDocPane(docPaneEl,demand);
  }

  /* ── Page shell ────────────────────────────────────────── */
  main.append(head('WORKFORCE STUDIO','Drop, Refine & Build','Jogue uma ideia. A esteira vai te grillando até virar uma task bem definida.',[
    button('Exportar tudo',()=>{exportJSON(state,'kiosk-workforce-state.json');},'subtle')]));

  main.append(demandBar);

  // If no demands, create the first one
  if(!state.demands.length){
    const d=newDemand('');state.demands.push(d);state.activeDemandId=d.id;save();
  }
  if(!state.activeDemandId)state.activeDemandId=state.demands[0]?.id;

  main.append(squadEl);
  main.append(pipelineEl);

  const dorPanel=el('section',{class:'panel'},panelTitle('Índice de Prontidão (Definition of Ready)','A demanda só desbloqueia execução com DoR ≥ 85%.'));
  dorPanel.append(dorEl);
  main.append(dorPanel);

  main.append(brainDumpEl);

  const splitTitle=el('div',{class:'page-heading',style:'padding-top:12px'},
    el('div',{},el('span',{class:'eyebrow'},'REFINAMENTO'),el('h2',{},'Perguntas de Campo & PRD Viva')));
  main.append(splitTitle);

  const split=el('div',{class:'wf-split'},questionsEl,docPaneEl);
  main.append(split);

  renderAll();
}

const api=Object.freeze({render});
root.BrainWorkforceStudio=api;
if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
