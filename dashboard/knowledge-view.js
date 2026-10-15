/* Human-facing local knowledge explorer. Source text stays data; actions stay local. */
(function(){
'use strict';
let serial=0;
const ICONS={search:'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',explore:'M12 3v18M3 12h18M5.6 5.6l12.8 12.8M5.6 18.4L18.4 5.6',library:'M4 3h6v18H4zM14 4l5-1 4 17-5 1z',save:'M6 3h12v18l-6-4-6 4z',arrow:'M5 12h14M13 6l6 6-6 6',close:'M6 6l12 12M18 6L6 18',info:'M12 11v6M12 7h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',source:'M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6'};
function mount(host,options={}){
 const M=window.BrainKnowledgeModel,C=options.core||window.BrainCore,markdown=options.markdown||window.BrainMarkdown;
 const el=(tag,attrs={},...children)=>{const node=document.createElement(tag);for(const [key,value] of Object.entries(attrs)){if(value==null||value===false)continue;if(key.startsWith('on')&&typeof value==='function')node.addEventListener(key.slice(2),value);else node.setAttribute(key,String(value));}for(const child of children.flat(Infinity))if(child!=null)node.append(typeof child==='string'||typeof child==='number'?document.createTextNode(String(child)):child);return node;};
 const icon=name=>{const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');for(const [key,value] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.7','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true',class:'kp-icon'}))svg.setAttribute(key,value);const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',ICONS[name]||ICONS.explore);svg.append(path);return svg;};
 const button=(label,action,cls='kp-button',iconName)=>el('button',{type:'button',class:cls,onclick:action},iconName?icon(iconName):null,el('span',{},label));
 if(!M||!C||!window.BrainKnowledgeMotion||!options.graph){host.append(el('section',{class:'kp-error'},el('h1',{},'Não foi possível abrir o conhecimento'),el('p',{},'Os dados ou módulos locais não foram carregados. Recarregue a página.')));return {dispose(){},getState(){return {};}};}
 const model=M.build(options.graph),id='kp-'+(++serial);
 let storage=options.storage;
 if(!storage)try{storage=localStorage;}catch(_){storage={getItem(){return null;},setItem(){throw new Error('storage unavailable');}};}
 let stored=[];try{const parsed=JSON.parse(storage.getItem('kiosk.knowledge-product.v1')||'[]');if(Array.isArray(parsed))stored=parsed.filter(x=>typeof x==='string').slice(0,2000);}catch(_){}
 const saved=new Set(stored),state={section:'explore',q:options.initialQuery||'',groupId:null,nodeId:options.initialNode||null,view:matchMedia('(max-width:700px)').matches?'cards':'map',motion:!matchMedia('(prefers-reduced-motion: reduce)').matches,limit:12,path:null,quality:'all'};
 const app=el('div',{class:'kp-app'}),sidebar=el('aside',{class:'kp-sidebar','aria-label':'Navegação do conhecimento'}),workspace=el('div',{class:'kp-workspace'});
 const status=el('div',{class:'kp-status',role:'status','aria-live':'polite'}),dialog=el('dialog',{class:'kp-dialog','aria-labelledby':id+'-dialog-title'});
 const notify=text=>{status.textContent=text;};
 function publish(){options.onStateChange?.({...state});}
 function persist(message){try{storage.setItem('kiosk.knowledge-product.v1',JSON.stringify([...saved]));notify(message);}catch(_){notify('O navegador bloqueou o armazenamento. As alterações valem apenas nesta sessão.');}renderNav();}
 function toggleSave(key){const removing=saved.has(key);if(removing)saved.delete(key);else saved.add(key);persist(removing?'Item retirado da coleção.':'Salvo na sua coleção local.');renderInspector();if(state.section==='saved')renderContent();}
 function setSection(section){state.section=section;state.q='';state.groupId=null;state.nodeId=null;searchInput.value='';state.path=null;state.limit=12;render();}
 const nav=el('nav',{class:'kp-nav','aria-label':'Explorar o segundo cérebro'});
 function renderNav(){nav.replaceChildren();for(const [section,label,symbol] of [['explore','Explorar','explore'],['library','Biblioteca','library'],['saved','Salvos','save']])nav.append(button(label,()=>setSection(section),'kp-nav-item'+(state.section===section?' kp-active':''),symbol));nav.append(el('span',{class:'kp-nav-caption'},saved.size+' itens na coleção local'));}
 const brand=button('Second Brain',()=>{state.nodeId=null;state.groupId=null;setSection('explore');},'kp-brand','explore');
 const groupNav=el('div',{class:'kp-spaces'});
 for(const group of model.groups)groupNav.append(button(group.label,()=>chooseGroup(group.id),'kp-space kp-token-'+group.token));
 sidebar.append(brand,el('div',{class:'kp-workspace-name'},el('span',{class:'kp-workspace-icon'},'K'),el('div',{},el('strong',{},'KIOSK Brands'),el('span',{},'Workspace de conhecimento'))),nav,el('span',{class:'kp-side-label'},'COLEÇÕES'),groupNav,el('div',{class:'kp-side-bottom'},button('Sobre o protótipo',showRoadmap,'kp-nav-item','info'),el('div',{class:'kp-local-note'},el('span',{class:'kp-connection-dot'}),'Dados locais · leitura e exploração')));
 const searchInput=el('input',{type:'search',id:id+'-search','aria-label':'Buscar no conhecimento',placeholder:'Busque uma regra, sistema ou decisão…',value:state.q,oninput:event=>{state.q=event.target.value;state.path=null;state.limit=12;renderContent();publish();}});
 const search=el('div',{class:'kp-search'},el('label',{for:id+'-search',class:'kp-sr-only'},'Buscar no conhecimento'),icon('search'),searchInput,el('kbd',{},'Ctrl K'));
 const topbar=el('header',{class:'kp-topbar'},search,el('span',{class:'kp-preview-badge'},el('span',{class:'kp-connection-dot'}),'Em desenvolvimento'),button('Como explorar',showGuide,'kp-button kp-subtle','info'));
 const content=el('main',{class:'kp-content'}),intro=el('section',{class:'kp-intro'}),metrics=el('div',{class:'kp-metrics'}),journeys=el('div',{class:'kp-journeys'}),explorer=el('section',{class:'kp-explorer'});
 const stage=el('div',{class:'kp-stage-panel'}),inspector=el('aside',{class:'kp-inspector','aria-label':'Contexto do item'}),stageTools=el('div',{class:'kp-stage-tools'}),sceneTitle=el('div',{class:'kp-scene-title'}),sceneDescription=el('p',{class:'kp-scene-description'});
 const modes=el('div',{class:'kp-segment','aria-label':'Forma de explorar'}),mapButton=button('Mapa',()=>{state.view='map';renderContent();}),cardsButton=button('Cartões',()=>{state.view='cards';renderContent();});modes.append(mapButton,cardsButton);
 const surface=el('div',{class:'kp-graph-surface'}),svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('role','group');svg.setAttribute('aria-label','Mapa do conhecimento, selecione uma categoria ou item');surface.append(svg);
 const cards=el('div',{class:'kp-cards'}),stageFoot=el('div',{class:'kp-stage-foot'}),stageMessage=el('span',{class:'kp-graph-caption'});
 const toolbar=el('div',{class:'kp-camera-tools'},button('−',()=>renderer.zoom(.8),'kp-button kp-square'),button('+',()=>renderer.zoom(1.2),'kp-button kp-square'),button('Enquadrar',()=>renderer.fit(),'kp-button kp-subtle'));
 toolbar.children[0].setAttribute('aria-label','Diminuir zoom');toolbar.children[1].setAttribute('aria-label','Aumentar zoom');
 const motionButton=button(state.motion?'Movimento ativo':'Movimento reduzido',()=>{state.motion=!state.motion;renderContent();},'kp-motion-button');
 stageFoot.append(stageMessage,motionButton,toolbar);
 stageTools.append(sceneTitle,modes);stage.append(stageTools,sceneDescription,surface,cards,stageFoot);explorer.append(stage,inspector);
 const collectionFilters=el('div',{class:'kp-collection-filters'});
 for(const group of model.groups)collectionFilters.append(button(group.label,()=>chooseGroup(group.id),'kp-chip kp-token-'+group.token));
 const allButton=button('Todas as coleções',()=>{state.groupId=null;state.nodeId=null;state.path=null;state.q='';searchInput.value='';state.section='explore';render();},'kp-chip');
 const filtersWrap=el('div',{class:'kp-filter-row'},allButton,collectionFilters);
 const footer=el('footer',{class:'kp-footer'},el('span',{},'Conhecimento com origem. Contexto antes de ação.'),button('O que já funciona?',showRoadmap,'kp-text-button'));
 content.append(intro,metrics,journeys,filtersWrap,explorer,footer,status);workspace.append(topbar,content);app.append(sidebar,workspace,dialog);host.append(app);
 const renderer=window.BrainKnowledgeMotion.mount(svg,{onNode:node=>{if(node.kind==='core'){state.groupId=null;state.nodeId=null;state.path=null;state.q='';searchInput.value='';render();}else if(node.kind==='category')chooseGroup(node.groupId);else chooseNode(node.entityId||node.id);},onEdge:edge=>showRelation(edge)});
 let currentScene=null;
 function chooseGroup(groupId){state.groupId=groupId;state.nodeId=null;state.q='';state.path=null;state.limit=12;state.section='explore';searchInput.value='';render();}
 function chooseNode(nodeId){if(!model.nodes.some(node=>node.id===nodeId))return;state.nodeId=nodeId;state.q='';state.path=null;state.section='explore';searchInput.value='';render();}
 function empty(title,description){return el('div',{class:'kp-empty'},icon('search'),el('h3',{},title),el('p',{},description));}
 function groupOf(node){return model.groups.find(group=>group.id===node.groupId);}
 const evidenceLabel={implementado:'Implementação declarada',local:'Implementação local declarada',documentado:'Documentado',parcial:'Documentação parcial',proposto:'Proposta',relatado:'Relato'};
 function resultCard(result){
  if(result.kind==='document')return el('article',{class:'kp-result-card kp-document-card'},el('span',{class:'kp-card-kicker'},'FONTE DO CONHECIMENTO'),el('h3',{},result.label),el('p',{},result.snippet||'Leia a fonte completa para conhecer este registro.'),sourceButton(result.document));
  const node=model.nodes.find(item=>item.id===(result.nodeId||result.id));if(!node)return null;
  return el('article',{class:'kp-result-card kp-token-'+(groupOf(node)?.token||'accent')},el('span',{class:'kp-card-kicker'},node.type),el('h3',{},node.label),el('p',{},result.snippet||node.description),el('div',{class:'kp-card-meta'},node.sourceBrief?'Fonte breve · precisa de contexto':(evidenceLabel[node.evidence]||'Registro do catálogo')),el('div',{class:'kp-card-actions'},button('Explorar item',()=>chooseNode(node.id),'kp-card-action','arrow'),node.document?sourceButton(node.document,'Ler fonte'):null));
 }
 function sourceButton(ref,label='Ler fonte'){const b=button(label,()=>openSource(ref),'kp-card-action','source');b.setAttribute('data-kp-source',ref);return b;}
 function renderMetrics(){metrics.replaceChildren();for(const [value,label,detail,symbol] of [[model.nodes.length,'itens no seu mapa','Sistemas, agentes e conhecimento','explore'],[model.edges.length,'conexões documentadas','Relações distintas entre os itens','arrow'],[Object.keys(model.documents).length,'fontes para consultar','Notas, decisões e playbooks','source']])metrics.append(el('div',{class:'kp-metric'},icon(symbol),el('div',{},el('strong',{},String(value)),el('span',{},label),el('small',{},detail))));}
 function renderJourneys(){journeys.replaceChildren(el('span',{class:'kp-section-label'},'UM BOM LUGAR PARA COMEÇAR'));
  const row=el('div',{class:'kp-journey-grid'});
  for(const [label,desc,fn] of [['Emissão exige NF real?','Encontre a regra e leia a fonte.',()=>{state.q='NF real';state.section='library';searchInput.value=state.q;render();}],['Como Bling chega à transportadora?','Siga uma conexão documentada.',showPath],['O que os agentes fazem?','Conheça os papéis e suas relações.',()=>chooseGroup('agents')]])row.append(button(label,fn,'kp-journey'),el('span',{class:'kp-sr-only'},desc));
  journeys.append(row);
 }
 function renderContent(){
  const group=model.groups.find(g=>g.id===state.groupId),selected=model.nodes.find(n=>n.id===state.nodeId);
  intro.replaceChildren(el('div',{},el('span',{class:'kp-eyebrow'},state.section==='saved'?'SUA COLEÇÃO':state.section==='library'?'BIBLIOTECA LOCAL':'CONHECIMENTO QUE FAZ SENTIDO'),el('h1',{},state.section==='saved'?'Seu contexto, sempre por perto.':state.section==='library'?'Encontre a informação. Leia a origem.':'Veja as conexões. Entenda o contexto.'),el('p',{},state.section==='saved'?'Itens que você escolheu guardar neste navegador.':state.section==='library'?'Pesquisa textual nos documentos do seu segundo cérebro.':'Um espaço para explorar sistemas, agentes e decisões — uma conexão de cada vez.')));
  const isResults=!!state.q||state.section!=='explore';modes.hidden=isResults;surface.hidden=isResults||state.view!=='map';cards.hidden=!isResults&&state.view==='map';toolbar.hidden=surface.hidden;motionButton.hidden=surface.hidden;
  mapButton.setAttribute('aria-pressed',String(state.view==='map'));cardsButton.setAttribute('aria-pressed',String(state.view==='cards'));motionButton.textContent=state.motion?'Movimento ativo':'Movimento reduzido';motionButton.setAttribute('aria-pressed',String(state.motion));
  allButton.setAttribute('aria-pressed',String(!state.groupId));for(const chip of collectionFilters.children)chip.setAttribute('aria-pressed',String(chip.textContent===group?.label));
  cards.replaceChildren();
  if(isResults){
   let results;
   if(state.q)results=M.search(model,state.q,{limit:60,kind:state.section==='library'?'document':'all'});
   else if(state.section==='saved')results=[...saved].map(key=>key.startsWith('entity:')?{kind:'entity',id:key.slice(7)}:{kind:'document',document:key.slice(9),label:model.documents[key.slice(9)]?.title||key.slice(9)}).filter(result=>result.kind==='document'?model.documents[result.document]:model.nodes.some(n=>n.id===result.id));
   else results=Object.entries(model.documents).map(([document,source])=>({kind:'document',id:document,document,label:source.title||document.split('/').pop().replace(/\.md$/,''),snippet:source.text.replace(/^---[\s\S]*?\r?\n---\s*/,'').replace(/^#+\s+.+$/gm,'').trim().slice(0,180)}));
   if(state.section==='saved')results=results.filter(result=>saved.has(result.kind==='document'?'document:'+result.document:'entity:'+(result.nodeId||result.id)));
   if(state.groupId){const ids=new Set(model.nodes.filter(n=>n.groupId===state.groupId).map(n=>n.id)),refs=new Set(model.nodes.filter(n=>n.groupId===state.groupId).map(n=>n.document));results=results.filter(result=>result.kind==='entity'?ids.has(result.nodeId||result.id):refs.has(result.document));}
   sceneTitle.replaceChildren(el('h2',{},state.q?'Resultados para “'+state.q+'”':state.section==='saved'?'Itens salvos':'Todas as fontes'),el('span',{class:'kp-count'},results.length+' resultados'));
   sceneDescription.textContent=state.q?'Até 50 correspondências locais. Abra a fonte para conferir o contexto.':'Tudo que aparece aqui vem do snapshot local.';
   for(const result of results.slice(0,state.limit)){const card=resultCard(result);if(card)cards.append(card);}
   if(!results.length)cards.append(empty(state.section==='saved'&&!state.q?'Sua coleção começa com uma descoberta.':'Nenhum resultado nesta seleção.','Explore um item, leia sua fonte ou tente uma busca mais curta.'));
   if(results.length>state.limit)cards.append(button('Mostrar mais resultados',()=>{state.limit+=12;renderContent();},'kp-button kp-load-more'));
   stageMessage.textContent=results.length>state.limit?Math.min(results.length,state.limit)+' de '+results.length+' resultados':'Busca textual · sem geração por IA';
  }else{
   const sceneLimit=state.view==='map'?12:state.limit;
   currentScene=state.path?.found?pathScene():selected?M.focus(model,{nodeId:selected.id,limit:sceneLimit}):group?M.focus(model,{groupId:group.id,limit:sceneLimit}):M.overview(model);
   const mode=selected||state.path?'entity':group?'group':'overview';currentScene={...currentScene,mode,selectedId:state.path?'hub':selected?.id};
   sceneTitle.replaceChildren(el('h2',{},state.path?'Da origem à transportadora':selected?selected.label:group?group.label:'Um mapa, cinco formas de explorar'),el('span',{class:'kp-count'},state.path?state.path.edges.length+' conexões':selected?'Contexto local':group?group.count+' itens':'5 coleções'));
   sceneDescription.textContent=state.path?'Um percurso entre relações registradas; não representa uma execução.':selected?'Relações de entrada e saída deste item. Selecione outra conexão para continuar.':group?'Explore os itens desta coleção e a documentação associada.':'Selecione uma coleção para aproximar. O detalhe aparece quando você precisa dele.';
   renderer.update(currentScene,{motion:state.motion,animate:state.view==='map',selectedId:currentScene.selectedId});
   const visible=currentScene.nodes.filter(n=>n.kind==='entity');
   if(visible.length){for(const item of visible){const card=resultCard({kind:'entity',id:item.entityId||item.id});if(card)cards.append(card);}}else for(const g of model.groups)cards.append(el('article',{class:'kp-result-card kp-token-'+g.token},el('span',{class:'kp-card-kicker'},'COLEÇÃO'),el('h3',{},g.label),el('p',{},g.description),button('Explorar '+g.count+' itens',()=>chooseGroup(g.id),'kp-card-action','arrow')));
   stageMessage.textContent=mode==='overview'?'Agrupamentos organizam a leitura; não são relações do conhecimento.':(currentScene.shown||visible.length)+' de '+(currentScene.total||visible.length)+' itens · setas indicam relações documentadas';
   if(group&&(currentScene.total||0)>visible.length)cards.append(button('Mostrar mais itens',()=>{state.limit+=12;renderContent();},'kp-button kp-load-more'));
  }
  renderInspector();publish();
 }
 function renderInspector(){
  inspector.replaceChildren();const node=model.nodes.find(n=>n.id===state.nodeId),group=model.groups.find(g=>g.id===state.groupId);
  if(state.path?.found){
   inspector.append(el('span',{class:'kp-eyebrow'},'PERCURSO DOCUMENTADO'),el('h2',{},'Como os sistemas se conectam'),el('p',{},state.path.nodes.map(nodeId=>model.nodes.find(n=>n.id===nodeId)?.label||nodeId).join(' → ')));
   for(const edgeId of state.path.edges){const raw=options.graph.edges.find(e=>e.id===edgeId);if(raw)inspector.append(el('div',{class:'kp-relation-summary'},el('strong',{},raw.relation),sourceButton(raw.source_file,'Conferir a fonte')));}
   inspector.append(el('p',{class:'kp-honesty-note'},'O grafo descreve relações. Este percurso não executa nenhuma operação.'));return;
  }
  if(!node){inspector.append(el('div',{class:'kp-inspector-art'},icon(group?'library':'explore')),el('span',{class:'kp-eyebrow'},group?'COLEÇÃO EM FOCO':'CADA CONEXÃO TEM UM CONTEXTO'),el('h2',{},group?group.label:'Comece com uma curiosidade.'),el('p',{},group?group.description:'Escolha uma coleção no mapa, busque uma dúvida ou siga um dos percursos sugeridos.'),el('div',{class:'kp-next-steps'},el('span',{},'01 · Encontre um item'),el('span',{},'02 · Entenda suas conexões'),el('span',{},'03 · Confira a fonte')));
   inspector.append(el('div',{class:'kp-honesty-note'},el('strong',{},'Uma base em construção'),el('p',{},'Relações e estados vêm do catálogo. Fontes breves são sinalizadas para você avaliar o contexto.')));return;}
  const groupInfo=groupOf(node),relations=model.edges.filter(edge=>edge.source===node.id||edge.target===node.id);
  inspector.append(el('span',{class:'kp-eyebrow kp-token-'+(groupInfo?.token||'accent')},groupInfo?.label||node.type),el('h2',{},node.label),el('span',{class:'kp-evidence'},evidenceLabel[node.evidence]||'Registro do catálogo'),el('p',{},node.description||'Este item está registrado no catálogo de conhecimento.'),el('div',{class:'kp-inspector-actions'},button(saved.has('entity:'+node.id)?'Item salvo':'Salvar item',()=>toggleSave('entity:'+node.id),'kp-button','save'),button('Copiar contexto',()=>copyContext(node),'kp-button kp-subtle')));
  if(node.sourceBrief)inspector.append(el('div',{class:'kp-honesty-note kp-warning'},el('strong',{},'Esta fonte ainda é breve.'),el('p',{},'O registro oferece pouco contexto. O estado declarado no catálogo não comprova funcionamento atual.')));
  if(node.sourcePresent)inspector.append(sourceButton(node.document,'Ler fonte do item'));else inspector.append(el('p',{class:'kp-honesty-note'},'A fonte deste item não está incluída no snapshot.'));
  inspector.append(el('h3',{class:'kp-inspector-section-title'},relations.length+' conexões registradas'));
  if(!relations.length)inspector.append(el('p',{class:'kp-small'},'Ainda não há relações documentadas para este item.'));
  for(const edge of relations.slice(0,12)){
   const outgoing=edge.source===node.id,other=model.nodes.find(n=>n.id===(outgoing?edge.target:edge.source));
   if(!other)continue;
   const row=el('div',{class:'kp-relation'},button(other.label,()=>chooseNode(other.id),'kp-relation-button'),el('span',{},(outgoing?'→ ':'← ')+edge.relation),sourceButton(edge.source_file,'Fonte da relação'));inspector.append(row);
  }
  if(relations.length>12)inspector.append(el('p',{class:'kp-small'},'Exibindo 12 de '+relations.length+' relações.'));
 }
 function pathScene(){const ids=new Set(state.path.nodes);return {mode:'entity',selectedId:'hub',nodes:model.nodes.filter(n=>ids.has(n.id)).map(n=>({...n,kind:'entity',entityId:n.id,subtitle:n.type})),edges:state.path.edges.map(edgeId=>options.graph.edges.find(e=>e.id===edgeId)).filter(Boolean),links:[],total:ids.size,shown:ids.size};}
 function showPath(){state.path=C.shortestPath(options.graph,'bling','jt',{directed:true,view:'flow'});state.nodeId=null;state.groupId=null;state.q='';state.section='explore';state.view='map';searchInput.value='';if(!state.path.found)notify('Este snapshot não contém o percurso sugerido. Explore as fontes disponíveis.');render();}
 function showRelation(edge){state.nodeId=edge.source;state.path=null;renderInspector();notify('Relação documentada: '+edge.relation+'. Consulte a fonte para avaliar o contexto.');}
 function dialogShell(title){dialog.replaceChildren();const close=button('Fechar',()=>dialog.close(),'kp-button kp-subtle','close');dialog.append(el('header',{class:'kp-dialog-head'},el('h2',{id:id+'-dialog-title'},title),close));return close;}
 function openDialog(close){if(!dialog.open)dialog.showModal();close.focus();}
 function openSource(ref){
  const source=model.documents[ref];if(!source){notify('A fonte não está incluída neste snapshot.');return;}
  const close=dialogShell(source.title||ref.split('/').pop().replace(/\.md$/,''));
  dialog.append(el('p',{class:'kp-dialog-intro'},'Fonte do snapshot local · leia o contexto antes de concluir.'),el('div',{class:'kp-source-actions'},button(saved.has('document:'+ref)?'Fonte salva':'Salvar fonte',()=>{toggleSave('document:'+ref);},'kp-button','save')));
  const article=el('article',{class:'kp-markdown'}),body=source.text.replace(/^---\r?\n[\s\S]*?\r?\n---\s*/, '');
  if(markdown)markdown.render(article,body,{onWikiLink:label=>{dialog.close();state.q=label;searchInput.value=label;state.section='library';render();}});else article.textContent=body;
  dialog.append(article,el('details',{class:'kp-provenance'},el('summary',{},'Origem e referência'),el('p',{},'vault/'+ref),el('p',{},'SHA-256 '+(source.sha256||'indisponível')),el('p',{},'Snapshot '+(model.snapshotId||'indisponível')+' · '+(source.lines||'?')+' linhas. O arquivo original é preservado.')));
  openDialog(close);
 }
 async function copyContext(node){
  const relations=model.edges.filter(e=>e.source===node.id||e.target===node.id),text=node.label+' — '+node.type+'\n'+node.description+'\n\nRelações documentadas:\n'+relations.map(e=>(model.nodes.find(n=>n.id===e.source)?.label||e.source)+' → '+e.relation+' → '+(model.nodes.find(n=>n.id===e.target)?.label||e.target)).join('\n')+'\n\nFonte: vault/'+node.document+'\nSnapshot: '+model.snapshotId+'\nEstado declarado: '+node.evidence+'; sem confirmação operacional atual.';
  try{if(!navigator.clipboard)throw new Error('unavailable');await navigator.clipboard.writeText(text);notify('Contexto copiado com referência da fonte.');}catch(_){const close=dialogShell('Seu contexto, pronto para copiar');dialog.append(el('textarea',{class:'kp-copy-field','aria-label':'Contexto com referências',readonly:true},text),el('p',{class:'kp-small'},'Selecione o texto e copie. O navegador não disponibilizou a cópia automática.'));openDialog(close);}
 }
 function showGuide(){const close=dialogShell('Um bom mapa começa com uma pergunta.');dialog.append(el('div',{class:'kp-guide'},el('section',{},el('span',{},'01'),el('h3',{},'Encontre o que importa'),el('p',{},'Use uma dúvida concreta ou comece por uma coleção. A busca é textual e funciona sobre as fontes locais.')),el('section',{},el('span',{},'02'),el('h3',{},'Aproxime para entender'),el('p',{},'Selecione um item para ver quem se conecta a ele. A seta preserva o sentido da relação.')),el('section',{},el('span',{},'03'),el('h3',{},'Volte à origem'),el('p',{},'Leia a fonte, avalie suas lacunas e guarde o contexto que vale revisitar.'))));openDialog(close);}
 function showRoadmap(){const close=dialogShell('Um produto em desenvolvimento.');
  dialog.append(el('p',{class:'kp-dialog-intro'},'O objetivo é transformar informação encontrada em contexto confiável e reutilizável.'),el('div',{class:'kp-roadmap'},...[
   ['Disponível neste protótipo','Encontrar e compreender','Busca textual, leitura de fontes, coleções locais, exploração de relações e cópia de contexto.'],
   ['Próxima etapa','Capturar e manter','Entrada de novas notas, revisão de fontes e histórico de mudanças. Exige persistência e fluxo editorial.'],
   ['Evolução planejada','Sintetizar com evidências','Busca híbrida e respostas citadas, com testes de recuperação e avaliação humana.'],
   ['Visão de longo prazo','Agir com supervisão','Transformar contexto em tarefas auditáveis, com permissões, aprovação e verificação de resultado.']
  ].map(([label,title,description])=>el('section',{},el('span',{class:'kp-card-kicker'},label),el('h3',{},title),el('p',{},description)))));
  if(options.onTechnical)dialog.append(button('Abrir explorador técnico',()=>{dialog.close();options.onTechnical();},'kp-button'));
  openDialog(close);
 }
 function render(){renderNav();renderMetrics();renderJourneys();renderContent();}
 function keyboard(event){if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();searchInput.focus();}if(event.key==='Escape'&&!dialog.open){state.nodeId=null;state.groupId=null;state.path=null;state.q='';searchInput.value='';render();}}
 document.addEventListener('keydown',keyboard);render();
 return Object.freeze({getState:()=>({...state}),dispose(){renderer.dispose();document.removeEventListener('keydown',keyboard);if(dialog.open)dialog.close();}});
}
window.BrainKnowledgeView=Object.freeze({mount});
})();
