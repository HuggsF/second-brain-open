/* Curated graph exploration; paths never infer undocumented connections. */
(function(){
'use strict';
function render(main,U){
 const {el,button,badge,head,select,graph:G,core:C,notify,update,navigate,evidence}=U;
 let r=U.route, mode=r.mode||((matchMedia('(max-width:650px)').matches)?'list':U.saved.graphMode), tab='summary';
 let selected=G.nodes.find(n=>n.id===r.node && n.views[r.view]), selectedEdge=G.edges.find(e=>e.id===r.edge && e.view===r.view);
 let path={nodes:[],edges:[],found:false}, camera={x:0,y:0,width:1000,height:460}, first=true;
 const domainNames={ecommerce:'E-commerce',erp:'ERP',hub:'Hub',logistics:'Logística',infra:'Infraestrutura',domain:'Domínio'};
 main.append(head('MAPA / RELAÇÕES','Veja o contexto. Siga a evidência.','Explore uma perspectiva por vez. Expanda conexões sem transformar hipóteses em fatos.'));
 const graphPanel=el('section',{class:'panel graph-panel','aria-label':'Explorador de relações'}),inspector=el('aside',{class:'panel graph-inspector','aria-label':'Detalhes da seleção'});
 const count=el('span',{class:'inline-count',role:'status','aria-live':'polite'});
 const surface=el('div',{class:'graph-surface'}),list=el('div',{class:'graph-list','aria-label':'Lista equivalente ao grafo'});
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
 svg.setAttribute('aria-label','Mapa de entidades e relações');svg.setAttribute('role','group');surface.append(svg);
 const svgEl=(tag,attrs={},text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!=null)n.textContent=text;return n;};
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
  if(tab==='source'){body.append(button('Abrir fonte completa →',()=>U.openDoc(ref),'primary'));const doc=G.documents[ref];body.append(el('p',{class:'legend-note'},doc?doc.text.slice(0,420)+'…':'Fonte indisponível.'));return;}
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
  for(const n of svg.querySelectorAll('.node')){n.classList.toggle('selected',n.dataset.node===node.id);n.setAttribute('aria-pressed',String(n.dataset.node===node.id));}
  for(const n of list.querySelectorAll('[data-node]'))n.setAttribute('aria-pressed',String(n.dataset.node===node.id));
  if(U.route.focus==='1')draw();else inspect();
 }
 function selectEdge(edge){selectedEdge=edge;selected=null;update({edge:edge.id,node:null});inspect();}
 function cameraUpdate(){svg.setAttribute('viewBox',[camera.x,camera.y,camera.width,camera.height].join(' '));}
 function fit(data){
  const width=surface.clientWidth||900,height=surface.clientHeight||455;
  if(!data.nodes.length)return;
  const xs=data.nodes.map(n=>n.views[r.view][0]),ys=data.nodes.map(n=>n.views[r.view][1]);
  const minX=Math.min(...xs)-25,minY=Math.min(...ys)-40,maxX=Math.max(...xs)+205,maxY=Math.max(...ys)+120;
  const scale=Math.max((maxX-minX)/width,(maxY-minY)/height,0.75);
  camera={x:minX-((width*scale)-(maxX-minX))/2,y:minY-((height*scale)-(maxY-minY))/2,width:width*scale,height:height*scale};
  if(width<650){camera.width=width;camera.height=height;camera.x=minX;camera.y=minY;}
  cameraUpdate();
 }
 function zoom(factor){
  const next=Math.max(260,Math.min(2400,camera.width*factor)), ratio=next/camera.width;
  const h=camera.height*ratio;camera.x+=(camera.width-next)/2;camera.y+=(camera.height-h)/2;camera.width=next;camera.height=h;cameraUpdate();
 }
 function draw(){
  const activeId=document.activeElement?.dataset?.node;
  const data=subset();resetSelectionIfHidden(data);svg.replaceChildren();list.replaceChildren();
  count.textContent=data.nodes.length+' entidades · '+data.edges.length+' relações';
  surface.hidden=mode!=='map';list.hidden=mode!=='list';
  mapButton.setAttribute('aria-pressed',String(mode==='map'));listButton.setAttribute('aria-pressed',String(mode==='list'));
  if(!data.nodes.length){list.hidden=false;surface.hidden=true;list.append(U.empty('Nenhuma entidade nesta seleção','Remova os filtros para explorar o mapa.',button('Limpar filtros',()=>navigate({q:'',evidence:'all',domain:null,focus:null}))));inspect();return;}
  const defs=svgEl('defs'),marker=svgEl('marker',{id:'arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});marker.append(svgEl('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'var(--muted)'}));defs.append(marker);svg.append(defs);
  const nodeMap=new Map(data.nodes.map(n=>[n.id,n]));
  for(const edge of data.edges){
   const a=nodeMap.get(edge.source).views[r.view],b=nodeMap.get(edge.target).views[r.view];
   const toRight=b[0]>=a[0], sx=a[0]+(toRight?180:0),tx=b[0]+(toRight?0:180),sy=a[1]+42,ty=b[1]+42,mid=(sx+tx)/2;
   let d='M '+sx+' '+sy+' C '+mid+' '+sy+' '+mid+' '+ty+' '+tx+' '+ty;
   let labelX=mid,labelY=(sy+ty)/2-60,anchor='middle';
   if(Math.abs(a[0]-b[0])<100){const down=b[1]>a[1],vx=a[0]+90,vy=a[1]+(down?84:0),ex=b[0]+90,ey=b[1]+(down?0:84),my=(vy+ey)/2;d='M '+vx+' '+vy+' C '+vx+' '+my+' '+ex+' '+my+' '+ex+' '+ey;labelX=vx-12;labelY=my;anchor='end';}
   else if(Math.abs(a[1]-b[1])<50&&Math.abs(a[0]-b[0])>300){const bx=a[0]+90,ex=b[0]+90,by=a[1]+84,ey=b[1]+84,curve=Math.max(by,ey)+55;d='M '+bx+' '+by+' C '+bx+' '+curve+' '+ex+' '+curve+' '+ex+' '+ey;labelX=(bx+ex)/2;labelY=curve-4;}
   const proposed=['proposto','parcial','relatado'].includes(edge.evidence);
   svg.append(svgEl('path',{d,class:'graph-edge'+(proposed?' proposed':'')+(path.edges.includes(edge.id)?' on-path':''),'marker-end':'url(#arrow)'}));
   const edgeButton=svgEl('path',{d,class:'edge-target',role:'button',tabindex:0,'aria-label':nodeMap.get(edge.source).label+' → '+nodeMap.get(edge.target).label+': '+edge.relation});
   edgeButton.addEventListener('click',()=>selectEdge(edge));edgeButton.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectEdge(edge);}});
   svg.append(edgeButton);
   const text=svgEl('text',{x:labelX,y:labelY,'text-anchor':anchor,class:'edge-label'},edge.relation);text.addEventListener('click',()=>selectEdge(edge));svg.append(text);
  }
  for(const n of data.nodes){
   const [x,y]=n.views[r.view],group=svgEl('g',{transform:'translate('+x+' '+y+')',class:'node domain-'+n.domain+(selected?.id===n.id?' selected':''),role:'button',tabindex:0,'aria-label':n.label+', '+evidence[n.evidence],'aria-pressed':String(selected?.id===n.id)});
   group.dataset.node=n.id;
   group.append(svgEl('title',{},n.label+' · '+evidence[n.evidence]+' · '+n.document),svgEl('rect',{width:180,height:84,rx:12}),svgEl('circle',{cx:16,cy:20,r:3.5,class:'node-dot'}),svgEl('text',{x:27,y:25,'font-size':13,'font-weight':600},n.label.length>22?n.label.slice(0,21)+'…':n.label),svgEl('text',{x:15,y:46,'font-size':11,class:'node-meta'},n.type),svgEl('text',{x:15,y:66,'font-size':10,class:'node-meta'},n.issues?.length?n.issues.join(' · '):evidence[n.evidence]));
   group.addEventListener('click',()=>selectNode(n));group.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectNode(n);}});
   svg.append(group);
   const row=el('button',{class:'row-link','data-node':n.id,'aria-pressed':String(selected?.id===n.id),onclick:()=>selectNode(n)},el('span',{},el('span',{class:'row-title'},n.label),el('span',{class:'row-meta'},n.type+' · '+(domainNames[n.domain]||n.domain))),badge(evidence[n.evidence],['proposto','parcial','relatado'].includes(n.evidence)?'warn':'good'));
   list.append(row);
  }
  if(first&&mode==='map'){requestAnimationFrame(()=>fit(data));first=false;}else cameraUpdate();
  if(activeId)(mode==='map'?svg:list).querySelector('[data-node="'+CSS.escape(activeId)+'"]')?.focus({preventScroll:true});
  inspect();
 }
 const q=el('input',{type:'search',value:r.q,'aria-label':'Buscar entidades',placeholder:'Filtrar por entidade, tipo ou DEM…',oninput:e=>{update({q:e.target.value});draw();}});
 const focusCheck=el('input',{type:'checkbox',checked:r.focus==='1',onchange:e=>{if(e.target.checked&&!selected){e.target.checked=false;notify('Escolha uma entidade antes de focar a vizinhança.');return;}update({focus:e.target.checked?'1':null});draw();}});
 const domains=[...new Set(G.nodes.map(n=>n.domain))];
 main.append(el('div',{class:'filters'},el('label',{},'Entidades',q),select('Perspectiva',G.views.map(v=>[v.id,v.label]),r.view,v=>navigate({view:v,node:null,edge:null,focus:null,q:'',from:null,to:null,relation:null})),select('Evidência',[['all','Todas'],...Object.entries(evidence)],r.evidence,v=>{update({evidence:v});draw();}),select('Domínio',[['all','Todos'],...domains.map(d=>[d,domainNames[d]||d])],r.domain||'all',v=>{update({domain:v});draw();}),select('Relação',[['all','Todas as relações'],...[...new Set(G.edges.filter(e=>e.view===r.view).map(e=>e.relation))].map(v=>[v,v])],r.relation||'all',v=>{update({relation:v});draw();})));
 const mapButton=button('◎ Mapa',()=>{mode='map';first=true;update({mode});U.saved.graphMode=mode;U.persist();draw();}),listButton=button('▤ Lista',()=>{mode='list';update({mode});U.saved.graphMode=mode;U.persist();draw();});
 graphPanel.append(el('div',{class:'graph-tools'},mapButton,listButton,el('span',{class:'spacer'}),button('−',()=>zoom(1.25),'icon-button'),button('+',()=>zoom(.8),'icon-button'),button('Enquadrar',()=>fit(subset())),count),surface,list);
 graphPanel.querySelectorAll('.icon-button')[0].setAttribute('aria-label','Diminuir zoom');
 graphPanel.querySelectorAll('.icon-button')[1].setAttribute('aria-label','Aumentar zoom');
 graphPanel.append(el('div',{class:'graph-legend'},el('span',{},el('i',{class:'legend-dot'}),'Hub / domínio'),el('span',{},el('i',{class:'legend-dot good'}),'E-commerce'),el('span',{},el('i',{class:'legend-dot blue'}),'ERP'),el('span',{},el('i',{class:'legend-dot violet'}),'Infraestrutura'),el('span',{},el('i',{class:'legend-dot warn'}),'Logística')),el('p',{class:'graph-tip'},'Arraste para mover · Tab e Enter para selecionar · tracejado: evidência parcial, proposta ou relatada.'));
 const focus=el('div',{class:'path-controls'},el('label',{class:'check-label'},focusCheck,'Focar vizinhança'),select('Profundidade',[['1','1 salto'],['2','2 saltos']],String(r.hops),v=>{update({hops:v});draw();}));
 main.append(focus,el('div',{class:'graph-layout'},graphPanel,inspector));
 const pathPanel=el('section',{class:'panel',style:null});pathPanel.classList.add('path-panel');
 const endpoints=G.nodes.filter(n=>n.views[r.view]).map(n=>[n.id,n.label]);
 let from=endpoints.some(([id])=>id===r.from)?r.from:endpoints[0]?.[0],to=endpoints.some(([id])=>id===r.to)?r.to:endpoints.at(-1)?.[0],directed=r.directed==='1';
 const pathStatus=el('p',{class:'path-result',role:'status','aria-live':'polite'});
 pathPanel.append(U.panelTitle('Como essas entidades se conectam?','Caminho mínimo entre relações registradas. Nenhuma ligação é inferida.'));
 const pathControls=el('div',{class:'path-controls'},select('Origem',endpoints,from,v=>{from=v;update({from:v});}),select('Destino',endpoints,to,v=>{to=v;update({to:v});}),el('label',{class:'check-label'},el('input',{type:'checkbox',checked:directed,onchange:e=>{directed=e.target.checked;update({directed:directed?'1':null});}}),'Seguir direção'),button('Encontrar caminho',()=>{
  path=C.shortestPath(G,from,to,{directed,view:r.view});
  update({from,to,q:'',evidence:'all',domain:null,focus:null,relation:null});q.value='';focusCheck.checked=false;
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
 surface.addEventListener('pointerdown',e=>{if(e.target.closest('[role=button]')||e.button>0)return;drag={x:e.clientX,y:e.clientY,cx:camera.x,cy:camera.y};surface.setPointerCapture(e.pointerId);});
 surface.addEventListener('pointermove',e=>{if(!drag)return;camera.x=drag.cx-(e.clientX-drag.x)*camera.width/surface.clientWidth;camera.y=drag.cy-(e.clientY-drag.y)*camera.height/surface.clientHeight;cameraUpdate();});
 surface.addEventListener('pointerup',()=>drag=null);surface.addEventListener('pointercancel',()=>drag=null);
 draw();
}
window.BrainGraphUI=Object.freeze({render});
})();
