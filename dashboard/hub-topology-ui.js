(function(root){
'use strict';
const states={green:{label:'Saudável',mark:'●'},yellow:{label:'Atenção',mark:'▲'},red:{label:'Falha observada',mark:'!'},unknown:{label:'Desconhecido',mark:'?'}};
function state(status){return states[status]||states.unknown;}
function date(value){return Number.isFinite(value)?new Date(value*1000).toLocaleString('pt-BR'):'Ainda não disponível';}
function valueText(value){if(value===null||value===undefined)return 'Não disponível';if(typeof value==='boolean')return value?'Sim':'Não';return String(value);}
function age(value){return Number.isFinite(value)?Math.floor(value)+' s':'Não disponível';}
function render(model,U,options={}){
 const {el,button}=U,environment=model.environment==='hml'?'hml':'production',name=environment==='hml'?'Homologação':'Produção';
 let selected=model.nodes.some(node=>node.id===options.selectedId)?options.selectedId:'process';
 const prefix='hub-topology-'+environment,buttons=[];
 const root=el('section',{class:'hub-topology','aria-label':'Mapa operacional · '+name});
 const heading=el('div',{class:'topology-heading'},el('h3',{},'Mapa operacional'),el('span',{class:'small muted'},'4 aspectos do mesmo Hub'));
 const summaryState=state(model.summary.status);
 const summary=el('p',{class:'topology-summary topology-status-'+model.summary.status},el('span',{'aria-hidden':'true'},summaryState.mark+' '),summaryState.label+' · '+model.summary.reason);
 const map=el('div',{class:'topology-map',role:'group','aria-label':'Dependências internas · '+name});
 const inspector=el('section',{id:prefix+'-details',class:'topology-details','data-topology-details':'true','aria-label':'Detalhes do aspecto selecionado'});
 function select(id,notify=true){
  selected=id;for(const control of buttons)control.setAttribute('aria-pressed',String(control.getAttribute('data-node-id')===id));
  const node=model.nodes.find(item=>item.id===id),nodeState=state(node.status);
  const meta=el('dl',{class:'topology-meta'},el('dt',{},'Observação'),el('dd',{},date(node.observedAt)),el('dt',{},'Idade da evidência'),el('dd',{},age(node.ageSeconds)),el('dt',{},'Última tentativa do coletor'),el('dd',{},date(model.collection.lastAttemptAt)));
  const checks=el('div',{class:'topology-checks'});
  if(node.checks.length){
   const table=el('table',{class:'data-table'},el('caption',{},'Verificações do aspecto'),el('thead',{},el('tr',{},['Verificação','Recebido','Esperado','Resultado'].map(title=>el('th',{scope:'col'},title)))));
   const rows=el('tbody');
   for(const check of node.checks)rows.append(el('tr',{},el('th',{scope:'row'},check.label),el('td',{},valueText(check.value)),el('td',{},valueText(check.expected)),el('td',{},check.ok===true?'Conforme':check.ok===false?'Falhou':'Não comprovado')));
   table.append(rows);checks.append(table);
  }else checks.append(el('p',{class:'small muted'},'Sem verificações suficientes para este aspecto.'));
  const dependencies=el('div',{class:'topology-dependencies'});
  for(const [direction,title]of [['dependsOn','Depende de'],['dependents','Quem depende deste aspecto']]){
   const edges=model.edges.filter(edge=>direction==='dependsOn'?edge.source===id:edge.target===id);
   const list=el('ul',{'data-dependencies':direction});
   for(const edge of edges){const related=model.nodes.find(item=>item.id===(direction==='dependsOn'?edge.target:edge.source));list.append(el('li',{},related?.label||'Aspecto desconhecido'));}
   if(!edges.length)list.append(el('li',{class:'muted'},'Nenhuma dependência direta nesta topologia.'));
   dependencies.append(el('div',{},el('h4',{},title),list));
  }
  const sources=el('ul',{class:'topology-sources'});
  for(const edge of model.edges.filter(item=>item.source===id||item.target===id)){
   const source=model.nodes.find(item=>item.id===edge.source),target=model.nodes.find(item=>item.id===edge.target);
   sources.append(el('li',{},(source?.label||edge.source)+' → '+(target?.label||edge.target)+' · '+edge.relation,el('code',{},edge.sourceRef)));
  }
  inspector.replaceChildren(el('div',{class:'topology-detail-title'},el('h3',{},node.label),el('span',{class:'pill topology-status-'+node.status},nodeState.label)),el('p',{class:'topology-reason'},node.reason),meta,checks,dependencies,el('h4',{},'Fontes das relações'),sources);
  if(notify&&options.onSelect)options.onSelect(id);
 }
 function control(node,view){
  const status=state(node.status);
  const item=button('',()=>select(node.id),'topology-node topology-status-'+node.status+(view==='list'?' topology-list-node':''));
  item.setAttribute('data-node-id',node.id);item.setAttribute('data-view',view);item.setAttribute('aria-controls',prefix+'-details');item.setAttribute('aria-pressed','false');
  item.setAttribute('aria-label',node.label+' · '+status.label);
  item.append(el('strong',{},node.label),el('span',{class:'topology-node-state'},el('span',{'aria-hidden':'true'},status.mark+' '),status.label));
  buttons.push(item);return item;
 }
 const byId=id=>model.nodes.find(node=>node.id===id);
 const endpoints=el('div',{class:'topology-endpoints'},control(byId('internal'),'map'),control(byId('external'),'map'));
 map.append(endpoints,el('div',{class:'topology-access-arrows','aria-hidden':'true'},el('span',{},'↘'),el('span',{},'↙')),el('p',{class:'topology-relation'},'HTTP interno e público → Hub · atendido pelo Hub'),control(byId('process'),'map'),el('div',{class:'topology-database-arrow','aria-hidden':'true'},'↓'),el('p',{class:'topology-relation'},'Hub → SQLite · usa SQLite'),control(byId('database'),'map'));
 const list=el('details',{class:'topology-list'},el('summary',{},'Lista equivalente · selecionar aspecto'));
 const items=el('ul');for(const node of model.nodes)items.append(el('li',{},control(node,'list')));list.append(items);
 const legend=el('p',{class:'topology-legend'},'● Saudável · ▲ Atenção / histórico · ! Falha observada · ? Desconhecido');
 root.append(heading,summary,map,legend,list,inspector);select(selected,false);return root;
}
const api={render};root.BrainHubTopologyUI=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
