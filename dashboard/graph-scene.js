/* SVG owns presentation only. Semantic edges never come from visual membership. */
(function(){
'use strict';
const NS='http://www.w3.org/2000/svg';
function mount(svg,callbacks={}){
 const make=(tag,attrs={},text)=>{const node=document.createElementNS(NS,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,String(value));if(text!=null)node.textContent=text;return node;};
 const defs=make('defs'),marker=make('marker',{id:'brain-scene-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto'});
 marker.append(make('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'var(--muted)'}));defs.append(marker);
 const guides=make('g',{class:'scene-guides','aria-hidden':'true'}),members=make('g',{'aria-hidden':'true'}),edges=make('g'),nodes=make('g');svg.append(defs,guides,members,edges,nodes);
 const nodeElements=new Map(),edgeElements=new Map(),linkElements=new Map(),rings=new Map();
 let current=new Map(),scene={nodes:[],edges:[],links:[]},frame=0,disposed=false,selectedId=null,pathIds=new Set(),focusDomain=null;
 function activate(element,fn){element.addEventListener('click',fn);element.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();fn();}});}
 function refreshSelection(){
  for(const [id,entry] of nodeElements){
   entry.element.setAttribute('class','scene-node scene-'+entry.node.kind+' domain-'+(entry.node.domain||'platform')+(id===selectedId?' selected':'')+(entry.node.domain===focusDomain?' scene-focused':''));
   entry.element.setAttribute('aria-pressed',String(id===selectedId));
  }
  for(const [id,entry] of edgeElements){
   const selected=pathIds.has(id);entry.path.setAttribute('class','graph-edge scene-edge'+(selected?' on-path':'')+(['proposto','parcial','relatado'].includes(entry.edge.evidence)?' proposed':''));
   entry.label.setAttribute('class','edge-label scene-edge-label'+(selected?' selected':''));
  }
 }
 function reconcile(){
  const keepNodes=new Set(scene.nodes.map(node=>node.id));
  for(const [id,entry] of nodeElements)if(!keepNodes.has(id)){entry.element.remove();nodeElements.delete(id);current.delete(id);}
  for(const node of scene.nodes){
   const existing=nodeElements.get(node.id);if(existing){existing.node=node;continue;}
   const group=make('g',{'data-scene-node':node.id,role:'button',tabindex:0,'aria-label':node.kind==='category'?node.label+' · focar categoria':node.label});
   group.append(make('title',{},node.label+(node.kind==='entity'?' · selecionar e consultar fonte':' · agrupamento visual')));
   if(node.kind==='entity'){
    group.append(make('rect',{x:-68,y:-22,width:136,height:44,rx:10}),make('circle',{cx:-55,cy:0,r:3.5,class:'node-dot'}),make('text',{x:-44,y:4,'font-size':12},node.label.length>17?node.label.slice(0,16)+'…':node.label));
   }else{
    group.append(make('circle',{r:node.kind==='core'?44:32}),make('text',{'text-anchor':'middle',y:node.kind==='core'?4:5,'font-size':node.kind==='core'?14:18,'font-weight':600},node.kind==='core'?'AI-OS':node.label.slice(0,2).toUpperCase()));
    group.append(make('text',{'text-anchor':'middle',y:node.kind==='core'?66:53,'font-size':12,class:'scene-caption'},node.kind==='core'?'SEGUNDO CÉREBRO':node.label));
   }
   activate(group,()=>callbacks.onNode?.(nodeElements.get(node.id).node));nodes.append(group);nodeElements.set(node.id,{element:group,node});
  }
  const keepEdges=new Set(scene.edges.map(edge=>edge.id));
  for(const [id,entry] of edgeElements)if(!keepEdges.has(id)){entry.path.remove();entry.hit.remove();entry.label.remove();edgeElements.delete(id);}
  for(const edge of scene.edges){
   if(edgeElements.has(edge.id)){edgeElements.get(edge.id).edge=edge;continue;}
   const path=make('path',{'data-scene-edge':edge.id,'marker-end':'url(#brain-scene-arrow)'});
   const hit=make('path',{'data-scene-edge-target':edge.id,class:'edge-target',role:'button',tabindex:0,'aria-label':edge.source+' → '+edge.target+': '+edge.relation});
   hit.append(make('title',{},edge.source+' → '+edge.target+' · '+edge.relation));activate(hit,()=>callbacks.onEdge?.(edgeElements.get(edge.id).edge));
   const label=make('text',{'text-anchor':'middle'},edge.relation);edges.append(path,hit,label);edgeElements.set(edge.id,{edge,path,hit,label});
  }
  const keepLinks=new Set(scene.links.map(link=>link.id));
  for(const [id,node] of linkElements)if(!keepLinks.has(id)){node.remove();linkElements.delete(id);}
  for(const link of scene.links)if(!linkElements.has(link.id)){const path=make('path',{class:'scene-membership','data-scene-link':link.id});members.append(path);linkElements.set(link.id,path);}
  const categories=new Set(scene.nodes.filter(node=>node.kind==='category').map(node=>node.id));
  for(const [id,node] of rings)if(!categories.has(id)){node.remove();rings.delete(id);}
  for(const id of categories)if(!rings.has(id)){const ring=make('circle',{class:'scene-orbit'});guides.append(ring);rings.set(id,ring);}
  refreshSelection();
 }
 function clip(node,point,toward){
  const dx=toward.x-point.x,dy=toward.y-point.y,length=Math.hypot(dx,dy)||1;
  const t=node.kind==='entity'?1/Math.max(Math.abs(dx)/72,Math.abs(dy)/25,1):(node.kind==='core'?48:36)/length;
  return {x:point.x+dx*t,y:point.y+dy*t};
 }
 function paint(positions,progress,options){
  current=positions;
  for(const [id,entry] of nodeElements){const p=positions.get(id);entry.element.setAttribute('transform','translate('+p.x+' '+p.y+')');}
  for(const link of scene.links){const a=positions.get(link.source),b=positions.get(link.target);if(a&&b)linkElements.get(link.id).setAttribute('d','M '+a.x+' '+a.y+' L '+b.x+' '+b.y);}
  const groups=new Map();
  for(const edge of scene.edges){const key=JSON.stringify([edge.source,edge.target].sort());if(!groups.has(key))groups.set(key,[]);groups.get(key).push(edge);}
  for(const parallel of groups.values()){
   parallel.sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0);
   parallel.forEach((edge,index)=>{
    const a=positions.get(edge.source),b=positions.get(edge.target),entry=edgeElements.get(edge.id);if(!a||!b)return;
    const source=nodeElements.get(edge.source).node,target=nodeElements.get(edge.target).node;
    const start=clip(source,a,b),end=clip(target,b,a),length=Math.hypot(b.x-a.x,b.y-a.y)||1;
    const direction=edge.source<edge.target?1:-1,offset=(index-(parallel.length-1)/2)*52;
    let mx=(start.x+end.x)/2-(b.y-a.y)/length*offset*direction,my=(start.y+end.y)/2+(b.x-a.x)/length*offset*direction;
    let d='M '+start.x+' '+start.y+' Q '+mx+' '+my+' '+end.x+' '+end.y;
    if(edge.source===edge.target){const bend=84+index*30;d='M '+(a.x+48)+' '+(a.y-20)+' C '+(a.x+bend)+' '+(a.y-bend)+' '+(a.x-bend)+' '+(a.y-bend)+' '+(a.x-48)+' '+(a.y-20);mx=a.x;my=a.y-bend;}
    entry.path.setAttribute('d',d);entry.hit.setAttribute('d',d);entry.label.setAttribute('x',mx);entry.label.setAttribute('y',my-8);
   });
  }
  for(const [id,ring] of rings){const center=positions.get(id),children=scene.links.filter(link=>link.source===id).map(link=>positions.get(link.target)).filter(Boolean);const radius=Math.max(60,...children.map(p=>Math.hypot(p.x-center.x,p.y-center.y)));ring.setAttribute('cx',center.x);ring.setAttribute('cy',center.y);ring.setAttribute('r',radius);}
  callbacks.onFrame?.({positions,progress,options});
 }
 function update(nextScene,positions,options={}){
  if(disposed)return;
  for(const node of nextScene.nodes){const p=positions.get(node.id);if(!p||!Number.isFinite(p.x)||!Number.isFinite(p.y))throw new Error('Coordenadas inválidas para '+node.id);}
  cancelAnimationFrame(frame);scene=nextScene;focusDomain=options.focusDomain||null;reconcile();
  const start=new Map();for(const node of scene.nodes)start.set(node.id,current.get(node.id)||positions.get(node.id));
  guides.setAttribute('visibility',options.layout==='layered'?'hidden':'visible');
  const duration=options.animate===false||matchMedia('(prefers-reduced-motion: reduce)').matches?0:(options.duration??650),started=performance.now();
  if(!duration){paint(new Map(positions),1,options);return;}
  function tick(now){
   if(disposed||!svg.isConnected){frame=0;return;}
   const t=Math.max(0,Math.min(1,(now-started)/duration)),ease=t*t*(3-2*t),next=new Map();
   for(const [id,target] of positions){const from=start.get(id)||target;next.set(id,{x:from.x+(target.x-from.x)*ease,y:from.y+(target.y-from.y)*ease});}
   paint(next,ease,options);frame=t<1?requestAnimationFrame(tick):0;
  }
  paint(start,0,options);frame=requestAnimationFrame(tick);
 }
 // ── Pulse effects for live agent events ──
 const pulseStyle=document.createElement('style');
 pulseStyle.textContent='@keyframes scene-pulse{0%{r:0;opacity:.9}50%{opacity:.6}100%{r:56;opacity:0}}@keyframes scene-glow{0%{r:3.5}50%{r:7}100%{r:3.5}}.scene-pulse-ring{pointer-events:none;fill:none;stroke-width:2.5;animation:scene-pulse 2.2s ease-out forwards}.scene-glow{animation:scene-glow 1.1s ease-in-out}.scene-event-badge{pointer-events:none;font-size:11px;font-weight:700;paint-order:stroke}';
 document.head.append(pulseStyle);
 const pulseGroup=make('g',{class:'scene-pulses','aria-hidden':'true'});svg.append(pulseGroup);
 function pulse(nodeId,color,label){
  const pos=current.get(nodeId);if(!pos)return;
  const ring=make('circle',{cx:pos.x,cy:pos.y,r:0,stroke:color||'var(--accent)',class:'scene-pulse-ring'});
  const txt=make('text',{x:pos.x,y:pos.y-30,'text-anchor':'middle',fill:color||'var(--accent)',class:'scene-event-badge'},label||'');
  pulseGroup.append(ring,txt);
  const nodeEl=nodeElements.get(nodeId);
  if(nodeEl){const dot=nodeEl.element.querySelector('.node-dot');if(dot){dot.setAttribute('class','node-dot scene-glow');dot.style.fill=color||'';setTimeout(()=>{dot.setAttribute('class','node-dot');dot.style.fill='';},1100);}}
  setTimeout(()=>{ring.remove();txt.remove();},2200);
 }
 return Object.freeze({update,select(nodeId,edgeIds=[]){selectedId=nodeId;pathIds=new Set(edgeIds);refreshSelection();},pulse,dispose(){disposed=true;cancelAnimationFrame(frame);frame=0;pulseStyle.remove();}});
}
window.BrainGraphScene=Object.freeze({mount});
})();
