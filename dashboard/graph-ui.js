/* Curated graph exploration; paths never infer undocumented connections. */
(function(){
'use strict';
let cleanup=()=>{};
function dispose(){cleanup();cleanup=()=>{};}
function render(main,U){
 dispose();
 const {el,button,badge,head,select,graph:G,core:C,notify,update,navigate,evidence}=U;
 if(!window.BrainGraphLayout||!window.BrainGraphScene){main.append(U.empty('Motor gráfico indisponível','Recarregue a página para carregar os módulos locais.',button('Tentar novamente',()=>location.reload())));return;}
 let r=U.route, mode=r.mode||((matchMedia('(max-width:650px)').matches)?'list':U.saved.graphMode), tab='summary';
 let layout=r.layout==='layered'?'layered':'radial',orientation=r.orientation==='vertical'?'vertical':'horizontal',focusDomain=r.categoryFocus||null;
 let selected=G.nodes.find(n=>n.id===r.node && n.views[r.view]), selectedEdge=G.edges.find(e=>e.id===r.edge && e.view===r.view);
 let path={nodes:[],edges:[],found:false}, camera={x:0,y:0,width:1000,height:460}, first=true,positions=new Map(),cameraFrom=null,cameraTo=null,lastSize=null;
 const domainNames={ecommerce:'E-commerce',erp:'ERP',hub:'Hub',logistics:'Logística',infra:'Infraestrutura',domain:'Domínio',platform:'Plataforma',crm:'CRM'};
 main.append(head('SEGUNDO CÉREBRO / GRAFO','Do panorama ao contexto.','Explore as órbitas. Selecione uma categoria para revelar sua hierarquia e seguir as relações documentadas.'));
 const graphPanel=el('section',{class:'panel graph-panel','aria-label':'Explorador de relações'}),inspector=el('aside',{class:'panel graph-inspector','aria-label':'Detalhes da seleção'});
 const count=el('span',{class:'inline-count',role:'status','aria-live':'polite'});
 const surface=el('div',{class:'graph-surface'}),list=el('div',{class:'graph-list','aria-label':'Lista equivalente ao grafo'});
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
 svg.setAttribute('aria-label','Mapa de entidades e relações');svg.setAttribute('role','group');surface.append(svg);
 const layoutStatus=el('p',{class:'graph-layout-status',role:'status','aria-live':'polite'});
 const renderer=window.BrainGraphScene.mount(svg,{
  onNode(node){
   if(node.kind==='core'){changeLayout('radial',null);return;}
   if(node.kind==='category'){changeLayout('layered',node.domain);return;}
   const entity=G.nodes.find(n=>n.id===node.entityId);if(entity)selectNode(entity);
  },
  onEdge:selectEdge,
  onFrame({progress}){if(cameraFrom&&cameraTo){for(const key of ['x','y','width','height'])camera[key]=cameraFrom[key]+(cameraTo[key]-cameraFrom[key])*progress;cameraUpdate();if(progress===1){cameraFrom=null;cameraTo=null;}}}
 });
 function changeLayout(next,domain=focusDomain){
  layout=next;focusDomain=domain;mode='map';
  U.saved.graphMode=mode;U.persist();
  update({layout,categoryFocus:focusDomain,orientation,mode});
  draw();
 }
 function subset(){
  r=U.route;
  let nodes=G.nodes.filter(n=>n.views[r.view]);
  if(r.q)nodes=nodes.filter(n=>C.normalize(n.label+' '+n.id+' '+n.type+' '+(n.issues||[]).join(' ')).includes(C.normalize(r.q)));
  if(r.evidence!=='all')nodes=nodes.filter(n=>n.evidence===r.evidence);
  if(r.domain&&r.domain!=='all')nodes=nodes.filter(n=>n.domain===r.domain);
  if(r.focus==='1'&&selected){const ids=new Set(C.neighborhood(G,selected.id,r.hops).nodes.map(n=>n.id));nodes=nodes.filter(n=>ids.has(n.id));}
  const ids=new Set(nodes.map(n=>n.id));
  return {nodes,edges:G.edges.filter(e=>e.view===r.view&&ids.has(e.source)&&ids.has(e.target)&&(!r.relation||r.relation==='all'||e.relation===r.relation))};
 }
 function resetSelectionIfHidden(data){
  if(selected&&!data.nodes.some(n=>n.id===selected.id)){selected=null;selectedEdge=null;update({node:null,edge:null});notify('A seleção ficou fora dos filtros. Escolha uma entidade visível.');}
  if(selectedEdge&&!data.edges.some(e=>e.id===selectedEdge.id)){selectedEdge=null;update({edge:null});}
 }
 function jump(node){
  navigate({page:'graph',view:node.views[r.view]?r.view:Object.keys(node.views)[0],node:node.id,edge:null,q:'',evidence:'all',domain:null,focus:null,relation:null});
 }
 function inspect(){
  inspector.replaceChildren();
  const item=selectedEdge||selected;
  if(!item){inspector.append(el('span',{class:'eyebrow'},'INSPECTOR'),el('h2',{},'Escolha uma conexão'),el('p',{},'Selecione uma entidade ou relação. A fonte e suas pendências aparecem aqui.'),el('div',{class:'readiness'},el('div',{},el('strong',{},'Código'),el('span',{class:'muted'},'Nível de evidência')),el('div',{},el('strong',{},'Implantação'),el('span',{class:'muted'},'Snapshot documentado'))));return;}
  inspector.append(el('span',{class:'eyebrow'},selectedEdge?'RELAÇÃO DOCUMENTADA':item.type.toUpperCase()),el('h2',{},selectedEdge?item.relation:item.label),badge(evidence[item.evidence]||item.evidence, ['parcial','proposto','relatado'].includes(item.evidence)?'warn':'good'));
  if(item.deployment)inspector.append(el('div',{class:'tag-row'},badge(item.deployment.label,'blue')));
  inspector.append(el('p',{class:'legend-note'},'Fonte: '+(item.document||item.source_file)),el('p',{class:'legend-note'},'Evidência registrada em '+(item.valid_at||'08/10/2026')+' · sem leitura ao vivo.'));
  const tabs=el('div',{class:'inspector-tabs','aria-label':'Conteúdo do inspector'});
  for(const [id,label] of [['summary','Resumo'],['relations','Relações'],['source','Fonte']]){const b=button(label,()=>{tab=id;inspect();inspector.querySelector('[aria-pressed=true]')?.focus({preventScroll:true});});b.setAttribute('aria-pressed',String(tab===id));tabs.append(b);}
  inspector.append(tabs);
  const body=el('div',{class:'inspector-content'});inspector.append(body);
  const ref=item.document||item.source_file;
  if(tab==='source'){body.append(button('Abrir fonte completa →',()=>U.openDoc(ref),'primary'));const doc=G.documents[ref];body.append(el('p',{class:'legend-note'},doc?C.stripFrontmatter(doc.text).slice(0,420)+'…':'Fonte indisponível.'));return;}
  if(tab==='summary'){
   if(selectedEdge){body.append(el('p',{},'De '+G.nodes.find(n=>n.id===item.source).label+' para '+G.nodes.find(n=>n.id===item.target).label+'. Esta direção é a relação curada no catálogo.'));}
   else {body.append(el('p',{},'Domínio: '+(domainNames[item.domain]||item.domain)+'. '+(item.issues?.length?item.issues.length+' pendências vinculadas.':'Sem pendências vinculadas no catálogo.')));}
   body.append(el('div',{class:'action-row'},button('Consultar fonte →',()=>U.openDoc(ref),'primary')));
   for(const issue of item.issues||[])body.append(button(issue+' · abrir backlog',()=>U.openDoc('systems/backlog-analise-hub-logistico.md',issue),'relation-button'));
   if(selected && !selectedEdge)body.append(button('Focar vizinhança',()=>{update({focus:'1',q:'',evidence:'all',domain:null});focusCheck.checked=true;draw();},'relation-button'));
  }else {
   const rels=selectedEdge?[selectedEdge]:G.edges.filter(e=>e.source===selected.id||e.target===selected.id);
   if(!rels.length)body.append(el('p',{},'Nenhuma relação cadastrada.'));
   for(const edge of rels){
    const target=G.nodes.find(n=>n.id===(edge.source===selected?.id?edge.target:edge.source));
    body.append(button((edge.source===selected?.id?'→ ':'← ')+target.label+' · '+edge.relation,()=>jump(target),'relation-button'),button('Fonte da relação',()=>U.openDoc(edge.source_file),'subtle'));
   }
  }
 }
 function selectNode(node){
  selected=node;selectedEdge=null;update({node:node.id,edge:null});
  renderer.select(node.id,path.edges);
  for(const n of list.querySelectorAll('[data-node]'))n.setAttribute('aria-pressed',String(n.dataset.node===node.id));
  if(U.route.focus==='1')draw();else inspect();
 }
 function selectEdge(edge){selectedEdge=edge;selected=null;update({edge:edge.id,node:null});renderer.select(null,[...path.edges,edge.id]);inspect();}
 function cameraUpdate(){svg.setAttribute('viewBox',[camera.x,camera.y,camera.width,camera.height].join(' '));}
 function fitted(points,frameFocus=false){
  const width=surface.clientWidth||900,height=surface.clientHeight||455;
  if(!points.size)return {...camera};
  const branch=frameFocus&&layout==='layered'&&focusDomain?new Set(['@domain:'+focusDomain,...G.nodes.filter(n=>n.domain===focusDomain).map(n=>n.id)]):null;
  const values=[...points].filter(([id])=>!branch||branch.has(id)).map(([,point])=>point);
  if(!values.length)return {...camera};
  const xs=values.map(p=>p.x),ys=values.map(p=>p.y);
  const minX=Math.min(...xs)-100,minY=Math.min(...ys)-100,maxX=Math.max(...xs)+100,maxY=Math.max(...ys)+100;
  const scale=Math.max((maxX-minX)/width,(maxY-minY)/height,0.75);
  const next={x:minX-((width*scale)-(maxX-minX))/2,y:minY-((height*scale)-(maxY-minY))/2,width:width*scale,height:height*scale};
  if(branch&&scale>12/11){
   const category=points.get('@domain:'+focusDomain),readableScale=12/11;
   next.width=width*readableScale;next.height=height*readableScale;
   next.x=category.x+(orientation==='horizontal'?280:0)-next.width/2;
   next.y=category.y+(orientation==='vertical'?280:0)-next.height/2;
   return next;
  }
  return next;
 }
 function fit(){cameraFrom=null;cameraTo=null;camera=fitted(positions);cameraUpdate();}
 function zoom(factor){
  cameraFrom=null;cameraTo=null;
  const next=Math.max(260,Math.min(30000,camera.width*factor)), ratio=next/camera.width;
  const h=camera.height*ratio;camera.x+=(camera.width-next)/2;camera.y+=(camera.height-h)/2;camera.width=next;camera.height=h;cameraUpdate();
 }
 function draw(){
  const activeId=document.activeElement?.dataset?.node;
  const data=subset();resetSelectionIfHidden(data);list.replaceChildren();
  count.textContent=data.nodes.length+' entidades · '+data.edges.length+' relações';
  surface.hidden=mode!=='map';list.hidden=mode!=='list';
  radialButton.setAttribute('aria-pressed',String(mode==='map'&&layout==='radial'));layerButton.setAttribute('aria-pressed',String(mode==='map'&&layout==='layered'));listButton.setAttribute('aria-pressed',String(mode==='list'));
  orientationSelect.hidden=layout!=='layered';
  categorySelect.querySelector('select').value=focusDomain||'';
  layoutStatus.textContent=layout==='radial'?'Órbitas por domínio · selecione uma categoria para abrir as camadas.':'Camadas '+(orientation==='horizontal'?'horizontais':'verticais')+(focusDomain?' · foco em '+(domainNames[focusDomain]||focusDomain):'')+' · núcleo → categoria → entidades.';
  if(!data.nodes.length){renderer.update({nodes:[],edges:[],links:[]},new Map(),{animate:false});positions=new Map();list.hidden=false;surface.hidden=true;list.append(U.empty('Nenhuma entidade nesta seleção','Remova os filtros para explorar o mapa.',button('Limpar filtros',()=>navigate({q:'',evidence:'all',domain:null,focus:null}))));inspect();return;}
  try{
   const scene=window.BrainGraphLayout.project(data,{domainLabels:domainNames});
   if(focusDomain&&!scene.nodes.some(n=>n.kind==='category'&&n.domain===focusDomain)){focusDomain=null;update({categoryFocus:null});}
   positions=layout==='radial'?window.BrainGraphLayout.radial(scene):window.BrainGraphLayout.layered(scene,{focusDomain,orientation});
   lastSize=[surface.clientWidth||900,surface.clientHeight||455];
   cameraFrom={...camera};cameraTo=fitted(positions,true);
   renderer.update(scene,positions,{layout,focusDomain,animate:!first&&mode==='map',duration:650});
   renderer.select(selected?.id,[...path.edges,...(selectedEdge?[selectedEdge.id]:[])]);first=false;
  }catch(error){
   surface.hidden=true;list.hidden=false;list.append(U.empty('Não foi possível organizar o mapa','As fontes continuam disponíveis na lista. Tente organizar o grafo novamente.',button('Tentar novamente',()=>draw())));
   layoutStatus.textContent='Falha ao calcular o layout. Use a lista para consultar as entidades.';
  }
  for(const n of data.nodes){
   const row=el('button',{class:'row-link','data-node':n.id,'aria-pressed':String(selected?.id===n.id),onclick:()=>selectNode(n)},el('span',{},el('span',{class:'row-title'},n.label),el('span',{class:'row-meta'},n.type+' · '+(domainNames[n.domain]||n.domain))),badge(evidence[n.evidence],['proposto','parcial','relatado'].includes(n.evidence)?'warn':'good'));
   list.append(row);
  }
  if(activeId&&mode==='list')list.querySelector('[data-node="'+CSS.escape(activeId)+'"]')?.focus({preventScroll:true});
  inspect();
 }
 const q=el('input',{type:'search',value:r.q,'aria-label':'Buscar entidades',placeholder:'Filtrar por entidade, tipo ou DEM…',oninput:e=>{update({q:e.target.value});draw();}});
 const focusCheck=el('input',{type:'checkbox',checked:r.focus==='1',onchange:e=>{if(e.target.checked&&!selected){e.target.checked=false;notify('Escolha uma entidade antes de focar a vizinhança.');return;}update({focus:e.target.checked?'1':null});draw();}});
 const domains=[...new Set(G.nodes.map(n=>n.domain))];
 main.append(el('div',{class:'filters'},el('label',{},'Entidades',q),select('Perspectiva',G.views.map(v=>[v.id,v.label]),r.view,v=>navigate({view:v,node:null,edge:null,focus:null,q:'',from:null,to:null,relation:null})),select('Evidência',[['all','Todas'],...Object.entries(evidence)],r.evidence,v=>{update({evidence:v});draw();}),select('Domínio',[['all','Todos'],...domains.map(d=>[d,domainNames[d]||d])],r.domain||'all',v=>{update({domain:v});draw();}),select('Relação',[['all','Todas as relações'],...[...new Set(G.edges.filter(e=>e.view===r.view).map(e=>e.relation))].map(v=>[v,v])],r.relation||'all',v=>{update({relation:v});draw();})));
 const radialButton=button('Órbitas',()=>changeLayout('radial',null)),layerButton=button('Camadas',()=>changeLayout('layered',focusDomain||selected?.domain)),listButton=button('Lista',()=>{mode='list';update({mode});U.saved.graphMode=mode;U.persist();draw();});
 const orientationSelect=select('Orientação',[['horizontal','Horizontal'],['vertical','Vertical']],orientation,value=>{orientation=value;changeLayout('layered');});
 const categoryOptions=[...new Set(G.nodes.filter(n=>n.views[r.view]).map(n=>n.domain))].sort();
 const categorySelect=select('Foco de categoria',[['','Todas as categorias'],...categoryOptions.map(domain=>[domain,domainNames[domain]||domain])],focusDomain||'',value=>changeLayout(value?'layered':'radial',value||null));
 graphPanel.append(el('div',{class:'graph-tools'},radialButton,layerButton,listButton,el('span',{class:'spacer'}),button('−',()=>zoom(1.25),'icon-button'),button('+',()=>zoom(.8),'icon-button'),button('Enquadrar',()=>fit()),count),el('div',{class:'graph-layout-bar'},layoutStatus,categorySelect,orientationSelect,button('Voltar ao núcleo',()=>changeLayout('radial',null),'subtle')),surface,list);
 graphPanel.querySelectorAll('.icon-button')[0].setAttribute('aria-label','Diminuir zoom');
 graphPanel.querySelectorAll('.icon-button')[1].setAttribute('aria-label','Aumentar zoom');
 graphPanel.append(el('div',{class:'graph-legend'},el('span',{},el('i',{class:'legend-dot'}),'Domínios'),el('span',{},'→ Relação documentada'),el('span',{},'··· Agrupamento visual')),el('p',{class:'graph-tip'},'Arraste para mover · + / − para zoom · Enter para selecionar · Esc volta às órbitas. Setas tracejadas indicam evidência parcial, proposta ou relatada. Agrupamentos não concedem permissões.'));
 const focus=el('div',{class:'path-controls'},el('label',{class:'check-label'},focusCheck,'Focar vizinhança'),select('Profundidade',[['1','1 salto'],['2','2 saltos']],String(r.hops),v=>{update({hops:v});draw();}));
 const resize=typeof ResizeObserver==='undefined'?null:new ResizeObserver(()=>{
  if(mode!=='map'||!positions.size)return;
  const size=[surface.clientWidth||900,surface.clientHeight||455];
  if(lastSize&&lastSize[0]===size[0]&&lastSize[1]===size[1])return;
  lastSize=size;cameraFrom=null;cameraTo=null;camera=fitted(positions,true);cameraUpdate();
 });resize?.observe(surface);
 // ── Live agent event feed ──
 const E=window.BrainGraphEvents;
 let unsub=null;
 if(E){
  const livePanel=el('section',{class:'panel','aria-label':'Atividade em tempo real'});
  const liveHeader=el('div',{class:'panel-head'},el('div',{},el('h2',{},'Atividade dos Agentes'),el('p',{class:'muted small'},'Conectando…')));
  const statusDot=el('span',{class:'live-dot','aria-hidden':'true'});liveHeader.querySelector('h2').prepend(statusDot);
  const liveLog=el('div',{class:'live-event-log','aria-label':'Log de eventos','aria-live':'polite'});
  const simToggle=el('label',{class:'check-label'},el('input',{type:'checkbox',checked:true,onchange:e=>{if(e.target.checked)E.connect();else{E.disconnect();liveLog.replaceChildren();}}}),'Atividade ao vivo');
  livePanel.append(liveHeader,simToggle,liveLog);
  const liveCSS=document.createElement('style');
  liveCSS.textContent='.live-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;background:var(--muted);vertical-align:middle}.live-dot.connected{background:var(--good)}.live-dot.simulated{background:var(--warn)}.live-dot.disconnected{background:var(--muted)}.live-event-log{max-height:320px;overflow-y:auto;display:grid;gap:4px;margin-top:10px}.live-event-item{display:flex;align-items:flex-start;gap:8px;padding:8px 10px;border-radius:8px;background:var(--panel2);font-size:12px;border-left:3px solid var(--accent);animation:live-fade-in .3s ease;cursor:pointer}.live-event-item:hover{background:var(--border)}.live-event-item .ev-emoji{font-size:16px;flex-shrink:0}.live-event-item .ev-body{flex:1;min-width:0}.live-event-item .ev-agent{font-weight:600;color:var(--text)}.live-event-item .ev-action{color:var(--muted)}.live-event-item .ev-nodes{font-size:11px;color:var(--accent);margin-top:2px}.live-event-item .ev-meta{font-size:11px;color:var(--muted);margin-top:2px}@keyframes live-fade-in{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}';
  document.head.append(liveCSS);
  function renderEvent(event){
   if(event.type==='connection'){
    const st=liveHeader.querySelector('.muted');
    statusDot.className='live-dot '+(event.mode||'disconnected')+(event.connected?' connected':'');
    st.textContent=event.mode==='sse'?'SSE ativo':event.mode==='ws'?'WebSocket ativo':event.mode==='simulated'?'Simulando atividade':'Desconectado';
    return;
   }
   const nodes=event.nodes||[];
   const color=E.agentColor(event.agent);
   for(const nid of nodes)renderer.pulse(nid,color,E.agentEmoji(event.agent));
   const time=new Date(event.timestamp);
   const item=el('div',{class:'live-event-item'},
    el('span',{class:'ev-emoji'},E.agentEmoji(event.agent)),
    el('div',{class:'ev-body'},
     el('span',{class:'ev-agent'},event.agent),
     el('span',{class:'ev-action'},' · '+event.action+(event.tool&&event.tool!=='internal'?' ('+event.tool+')':'')),
     el('div',{class:'ev-nodes'},nodes.join(' → ')),
     el('div',{class:'ev-meta'},time.toLocaleTimeString('pt-BR')+(event.duration_ms?' · '+event.duration_ms+'ms':'')+(event.tokens?' · '+event.tokens+' tok':''))
    )
   );
   item.style.borderLeftColor=color;
   item.addEventListener('click',()=>{for(const nid of nodes)renderer.pulse(nid,color,E.agentEmoji(event.agent));});
   liveLog.prepend(item);
   while(liveLog.children.length>30)liveLog.lastChild.remove();
  }
  unsub=E.subscribe(renderEvent);
  E.connect();
  main.append(focus,el('div',{class:'graph-layout'},graphPanel,el('div',{},inspector,livePanel)));
 }else{
  main.append(focus,el('div',{class:'graph-layout'},graphPanel,inspector));
 }
 const pathPanel=el('section',{class:'panel',style:null});pathPanel.classList.add('path-panel');
 const endpoints=G.nodes.filter(n=>n.views[r.view]).map(n=>[n.id,n.label]);
 let from=endpoints.some(([id])=>id===r.from)?r.from:endpoints[0]?.[0],to=endpoints.some(([id])=>id===r.to)?r.to:endpoints.at(-1)?.[0],directed=r.directed!=='0';
 const pathStatus=el('p',{class:'path-result',role:'status','aria-live':'polite'});
 pathPanel.append(U.panelTitle('Como essas entidades se conectam?','Caminho mínimo entre relações registradas. Nenhuma ligação é inferida.'));
 const pathControls=el('div',{class:'path-controls'},select('Origem',endpoints,from,v=>{from=v;update({from:v});}),select('Destino',endpoints,to,v=>{to=v;update({to:v});}),el('label',{class:'check-label'},el('input',{type:'checkbox',checked:directed,onchange:e=>{directed=e.target.checked;update({directed:directed?'1':'0'});}}),'Seguir direção'),button('Encontrar caminho',()=>{
  path=C.shortestPath(G,from,to,{directed,view:r.view});
  focusDomain=null;update({from,to,q:'',evidence:'all',domain:null,focus:null,relation:null,categoryFocus:null});q.value='';focusCheck.checked=false;
  main.querySelector('[aria-label="Evidência"]').value='all';main.querySelector('[aria-label="Domínio"]').value='all';main.querySelector('[aria-label="Relação"]').value='all';
  pathStatus.textContent=path.found?path.nodes.map(id=>G.nodes.find(n=>n.id===id).label).join(' → ')+' · '+path.edges.length+' relações documentadas.':'Nenhum caminho registrado nesta perspectiva. Isso não prova ausência de ligação no negócio.';
  draw();
 },'primary'));
 pathPanel.append(pathControls,pathStatus);
 const relationTable=el('details',{class:'toc'},el('summary',{},'Tabela de relações · fonte e direção'));
 const table=el('table',{class:'data-table'},el('caption',{class:'sr-only'},'Relações documentadas desta perspectiva'),el('thead',{},el('tr',{},...['Origem → destino','Relação','Evidência','Fonte'].map(s=>el('th',{scope:'col'},s)))));
 const tbody=el('tbody');
 for(const edge of G.edges.filter(e=>e.view===r.view)){
  tbody.append(el('tr',{},el('td',{},G.nodes.find(n=>n.id===edge.source).label+' → '+G.nodes.find(n=>n.id===edge.target).label),el('td',{},edge.relation),el('td',{},evidence[edge.evidence]),el('td',{},button('Abrir fonte',()=>U.openDoc(edge.source_file),'subtle'))));
 }
 table.append(tbody);relationTable.append(el('div',{class:'table-wrap'},table));pathPanel.append(relationTable);main.append(pathPanel);
 let drag=null;
 surface.addEventListener('pointerdown',e=>{if(e.target.closest('[role=button]')||e.button>0)return;cameraFrom=null;cameraTo=null;drag={x:e.clientX,y:e.clientY,cx:camera.x,cy:camera.y};surface.setPointerCapture(e.pointerId);});
 surface.addEventListener('pointermove',e=>{if(!drag)return;camera.x=drag.cx-(e.clientX-drag.x)*camera.width/surface.clientWidth;camera.y=drag.cy-(e.clientY-drag.y)*camera.height/surface.clientHeight;cameraUpdate();});
 surface.addEventListener('pointerup',()=>drag=null);surface.addEventListener('pointercancel',()=>drag=null);
 surface.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();changeLayout('radial',null);radialButton.focus();}});
 cleanup=()=>{renderer.dispose();resize?.disconnect();if(unsub)unsub();if(E)E.disconnect();};
 draw();
}
window.BrainGraphUI=Object.freeze({render,dispose});
})();

