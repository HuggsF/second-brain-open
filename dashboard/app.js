/* Offline UI adapter. Source documents are data, never instructions or executable HTML. */
(function () {
'use strict';
if(typeof window!=='undefined'&&!window.BrainBridge&&typeof document!=='undefined'&&document.head&&document.createElement){const s=document.createElement('script');s.src='post-message-bridge.js';s.defer=true;document.head.appendChild(s);}
const $ = id => document.getElementById(id);
const G = window.KIOSK_GRAPH, C = window.BrainCore, M = window.BrainMarkdown;
const dataOK=window.BrainSchema?.validateSnapshot(G).ok||false;
const pages = {overview:['◈','Visão geral'],knowledge:['▤','Conhecimento'],playbooks:['📋','Playbooks'],graph:['◎','Grafo'],queries:['⌕','Consultas'],workflows:['🔀','Workflows de IA'],architecture:['🏛','System Design'],product:['🎯','Produto & OKRs'],teams:['⚙','Times'],observability:['◉','Observabilidade'],nexus:['🏢','Nexus Office'],jev:['📊','JEV']};
const NAV_GROUPS = [
  { icon: '◈', label: 'Visão Geral', page: 'overview' },
  { icon: '🧠', label: 'Conhecimento', children: ['knowledge','graph','queries'] },
  { icon: '📋', label: 'Operação', children: ['playbooks','workflows'] },
  { icon: '🏗️', label: 'Arquitetura', children: ['architecture','product','teams'] },
  { icon: '📡', label: 'Observabilidade', page: 'observability' },
  { icon: '🤖', label: 'Agentes', children: ['nexus','jev'] },
];
const evidence = {implementado:'Implementado no código',local:'Implementado localmente',documentado:'Documentado',relatado:'Relatado',parcial:'Parcial',proposto:'Proposto'};
const categories = {all:'Todas as fontes',architecture:'Arquitetura · System Design',playbooks:'Playbooks',systems:'Sistemas',adrs:'Decisões · ADRs',product:'Produto',domain:'Domínio',daily:'Memória diária',general:'Geral'};
let storageOK = true, noticeTimer;
let knowledgeProduct=null;
const defaults = {version:1,theme:'dark',favorites:[],recent:[],history:[],graphMode:'map',plan:null};
let saved = {...defaults};
try {
 const parsed = JSON.parse(localStorage.getItem('kiosk.brain.v1') || 'null');
 if (parsed && parsed.version === 1) {
  for (const k of ['favorites','recent']) if (Array.isArray(parsed[k])) saved[k] = parsed[k].filter(x=>typeof x === 'string' && x.length<500).slice(0,100);
  if (Array.isArray(parsed.history)) saved.history=parsed.history.filter(x=>x && typeof x.query==='string').slice(0,12).map(x=>({query:x.query.slice(0,500),at:String(x.at).slice(0,50)}));
  if (['dark','light'].includes(parsed.theme)) saved.theme=parsed.theme;
  if (['map','list'].includes(parsed.graphMode)) saved.graphMode=parsed.graphMode;
  if (parsed.plan?.version===1 && Array.isArray(parsed.plan.steps) && parsed.plan.steps.length<=100 && parsed.plan.steps.every(s=>s && typeof s.id==='string' && typeof s.name==='string' && s.name.length<=160 && ['researcher','reviewer','writer'].includes(s.role) && Array.isArray(s.dependsOn) && s.dependsOn.every(x=>typeof x==='string') && Array.isArray(s.tools) && s.tools.every(x=>['search','read_graph','read_sources'].includes(x)) && Number.isFinite(s.budgetSeconds))) saved.plan=parsed.plan;
 }
} catch (_) {storageOK=false;}
document.documentElement.dataset.theme=saved.theme;
$('theme').setAttribute('aria-label',saved.theme==='dark'?'Ativar tema claro':'Ativar tema escuro');
function el(tag, attrs, ...children) {
 const node=document.createElement(tag);
 for (const [k,v] of Object.entries(attrs||{})) {
  if (v==null || v===false) continue;
  if (k==='class') node.className=v;
  else if (k==='text') node.textContent=v;
  else if (k==='style') node.style.cssText=String(v); // CSSOM: the BFF CSP (style-src 'self') drops style attributes
  else if (k.startsWith('on') && typeof v==='function') node.addEventListener(k.slice(2),v);
  else if (k==='value') node.value=v;
  else if (k==='checked') node.checked=!!v;
  else node.setAttribute(k,v===true?'':String(v));
 }
 for (const child of children.flat(Infinity)) if (child!=null && child!==false) node.append(child instanceof Node?child:document.createTextNode(String(child)));
 return node;
}
function button(text, action, cls='') {return el('button',{type:'button',class:cls,onclick:action},text);}
function badge(text, cls='') {return el('span',{class:'pill '+cls},text);}
function empty(title,description,action) {return el('div',{class:'empty'},el('h2',{},title),el('p',{},description),action||null);}
function confirmAction({title,description,confirmLabel}) {
 // Modal <dialog>; focus starts on Cancel and Esc cancels, so a stray Enter never confirms.
 return new Promise(resolve=>{
  const box=el('dialog',{class:'confirm-dialog','aria-labelledby':'confirm-title','aria-describedby':'confirm-description'});
  const cancel=button('Cancelar',()=>box.close('cancel'),'subtle');
  box.append(el('h2',{id:'confirm-title'},title),el('p',{id:'confirm-description'},description),el('div',{class:'action-row'},cancel,button(confirmLabel,()=>box.close('confirm'),'danger')));
  box.addEventListener('close',()=>{resolve(box.returnValue==='confirm');box.remove();});
  document.body.append(box);box.showModal();cancel.focus();
 });
}
function notify(message) {
 $('notice').textContent=message; $('notice').classList.add('visible');
 clearTimeout(noticeTimer); noticeTimer=setTimeout(()=>$('notice').classList.remove('visible'),6000);
}
function persist() {
 try {localStorage.setItem('kiosk.brain.v1',JSON.stringify(saved));storageOK=true;}
 catch (_) {storageOK=false;notify('O navegador não permitiu salvar. Seu contexto continua disponível nesta sessão.');}
}
function readRoute() {
 const p=new URLSearchParams(location.hash.slice(1)), r=Object.fromEntries(p);
 if(r.page==='agents')r.page='workflows'; // "Agentes em Ação" was a second entry for the same Arena
 r.page=Object.hasOwn(pages,r.page)?r.page:'overview';
 r.view=(dataOK?G.views:[]).some(v=>v.id===r.view)?r.view:(dataOK?G.views[0].id:'flow');
 r.q=(r.q||'').slice(0,500);
 r.category=Object.hasOwn(categories,r.category)?r.category:'all';
 r.evidence=Object.hasOwn(evidence,r.evidence)?r.evidence:'all';
 if(!['map','list'].includes(r.mode))delete r.mode;
 if(!['radial','layered'].includes(r.layout))delete r.layout;
 if(!['horizontal','vertical'].includes(r.orientation))delete r.orientation;
 if(!dataOK||!G.nodes.some(n=>n.domain===r.categoryFocus))delete r.categoryFocus;
 if(!dataOK||!G.nodes.some(n=>n.domain===r.domain))delete r.domain;
  const isProduct=r.page==='graph'&&r.experience==='product'&&!!window.BrainKnowledgeView;
  if(!dataOK||!(isProduct?G.nodes.some(n=>n.id===r.node):G.nodes.some(n=>n.id===r.node&&n.views[r.view])))delete r.node;
 if(!dataOK||!G.edges.some(e=>e.id===r.edge&&e.view===r.view))delete r.edge;
 if(!dataOK||!G.edges.some(e=>e.relation===r.relation&&e.view===r.view))delete r.relation;
 r.hops=r.hops==='2'?2:1;
 return r;
}
let route=readRoute();
function navigate(values,replace=false) {
 const next={...route,...values};
 if ('page' in values && values.page!==route.page) for (const key of ['q','doc','node','edge','section','lineStart','lineEnd','favorites','focus','from','to']) if (!(key in values)) delete next[key];
 const p=new URLSearchParams();
 for (const [k,v] of Object.entries(next)) if(v!=null && v!=='' && v!==false && v!=='all') p.set(k,String(v));
 const hash='#'+p.toString();
 if(replace){history.replaceState(null,'',hash);route=readRoute();}else if(location.hash===hash){route=readRoute();render();}else location.hash=hash;
}
function update(values){navigate(values,true);}
function head(eyebrow,title,description,actions) {
 return el('div',{class:'page-heading'},el('div',{},el('span',{class:'eyebrow'},eyebrow),el('h1',{},title),el('p',{},description)),actions?el('div',{class:'action-row'},actions):null);
}
function panelTitle(title,description,action){return el('div',{class:'panel-head'},el('div',{},el('h2',{},title),description?el('p',{},description):null),action||null);}
function select(label,options,value,onchange) {
 const s=el('select',{'aria-label':label,onchange:e=>onchange(e.target.value)});
 for (const [val,text] of options) s.append(el('option',{value:val},text));
 s.value=value;return el('label',{},label,s);
}
function exportJSON(value,name) {
 const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'});
 const href=URL.createObjectURL(blob);const a=el('a',{href,download:name});
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(href),1000);
 notify('Arquivo preparado para download local.');
}
async function copy(text) {
 try {await navigator.clipboard.writeText(text);notify('Copiado.');}
 catch (_) {const area=el('textarea',{'aria-label':'Conteúdo para copiar manualmente',readonly:true,value:text});const box=el('dialog',{'aria-label':'Copiar manualmente'},panelTitle('Copiar manualmente','Selecione o texto e use Ctrl / ⌘ + C.'),area);box.append(button('Fechar',()=>box.close()));box.addEventListener('close',()=>box.remove());document.body.append(box);box.showModal();area.select();}
}
function documentTitle(ref){return G.documents[ref]?.title || ref?.split('/').pop()?.replace(/\.md$/,'') || 'Fonte desconhecida';}
function openDoc(ref,section,lines) {
 if(!Object.hasOwn(G.documents,ref)){notify('Esta fonte não está no snapshot. Refaça a busca ou atualize o catálogo.');return;}
 saved.recent=[ref,...saved.recent.filter(x=>x!==ref)].slice(0,12);persist();
 navigate({page:'knowledge',doc:ref,q:'',category:'all',favorites:null,section:section||null,lineStart:lines?.[0]||null,lineEnd:lines?.[1]||null});
}
function resolveWiki(ref) {
 const normalized=ref.replace(/\\/g,'/').replace(/\.md$/,'');
 const exact=Object.keys(G.documents).find(path=>path.replace(/\.md$/,'')===normalized);
 if(exact)return [exact];
 return Object.keys(G.documents).filter(path=>path.split('/').pop().replace(/\.md$/,'')===normalized);
}
function row(title,meta,onclick){return el('button',{class:'row-link',type:'button',onclick},el('span',{},el('span',{class:'row-title'},title),el('span',{class:'row-meta'},meta)),el('span',{class:'row-arrow','aria-hidden':true},'↗'));}
function renderReader(ref,options={}) {
 const source=Object.hasOwn(G.documents,ref)?G.documents[ref]:null, reader=el('article',{class:'panel reader','aria-label':'Leitor de fonte',tabindex:-1});
 if(!source){reader.append(empty(ref?'Fonte não encontrada no snapshot':'Escolha uma fonte',ref?'A referência pode ter sido removida. Use a busca ou selecione outra fonte.':'Selecione um documento para ler seu conteúdo e verificar a origem.'));return reader;}
 const favorite=()=>{saved.favorites=saved.favorites.includes(ref)?saved.favorites.filter(x=>x!==ref):[ref,...saved.favorites];persist();const active=saved.favorites.includes(ref);fav.textContent=active?'★ Favorito':'☆ Favoritar';fav.setAttribute('aria-pressed',String(active));notify(active?'Fonte adicionada aos favoritos.':'Fonte removida dos favoritos.');};
 const fav=button(saved.favorites.includes(ref)?'★ Favorito':'☆ Favoritar',favorite,'subtle');
 fav.setAttribute('aria-pressed',String(saved.favorites.includes(ref)));
 const actions=el('div',{class:'action-row'},fav,button('Copiar referência',()=>copy('vault/'+ref+' · SHA-256 '+source.sha256),'subtle'),button('Exportar fonte',()=>exportJSON({document:ref,...source,snapshot_id:G.snapshot_id},ref.split('/').pop().replace(/\.md$/,'.json')),'subtle'));
 reader.append(el('header',{class:'reader-head'},el('span',{class:'eyebrow'},categories[source.category]||'FONTE LOCAL'),el('h2',{},documentTitle(ref)),el('p',{class:'path'},'vault/'+ref),actions));
 const provenance=el('details',{class:'provenance'},el('summary',{},'Origem verificável · '+source.lines+' linhas · SHA-256 '+source.sha256.slice(0,12)+'…'),el('p',{},'SHA-256 ',el('code',{},source.sha256)),el('p',{},'Arquivo modificado em '+formatDate(source.modified_at)+' · data do arquivo, não confirmação do conteúdo.'),el('p',{},'Snapshot '+G.snapshot_id.slice(0,16)+' · gerado em '+formatDate(G.built_at)));
 reader.append(provenance);
 if(options.lineStart){
  const rawStart=Math.floor(Number(options.lineStart)||1),rawEnd=Math.floor(Number(options.lineEnd)||rawStart);
  const start=Math.min(Math.max(1,source.lines),Math.max(1,rawStart)), end=Math.max(start,Math.min(source.lines,rawEnd));
  if(start!==rawStart||end!==rawEnd)reader.append(el('p',{class:'callout warn'},'O intervalo solicitado excedia a fonte. Abaixo está o intervalo válido ajustado.'));
  reader.append(el('section',{class:'citation-highlight','aria-label':'Trecho citado'},badge('Linhas '+start+'–'+end,'blue'),el('pre',{},source.text.split(/\r?\n/).slice(start-1,end).join('\n'))));
 }
 const content=el('div',{class:'markdown'});
 const rendered=M.render(content,source.text,{onWikiLink:(wiki,heading)=>{
  const refs=resolveWiki(wiki);
  if(refs.length===1)openDoc(refs[0],heading);
  else {navigate({page:'knowledge',q:wiki,doc:null,category:'all'});notify(refs.length?'Mais de uma fonte tem esse nome. Escolha a referência completa.':'Wikilink sem fonte neste snapshot. A busca foi aberta.');}
 }});
 if(rendered.truncated)reader.append(el('p',{class:'callout warn'},'A visualização foi limitada pelo tamanho do documento ou de um bloco. “Exportar fonte” contém o texto original completo.'));
 if(rendered.headings.length>1) {
  const toc=el('details',{class:'toc'},el('summary',{},'Nesta fonte · '+rendered.headings.length+' seções'));
  for(const heading of rendered.headings) {
   const a=el('a',{href:'#page=knowledge&doc='+encodeURIComponent(ref)+'&section='+encodeURIComponent(heading.id),onclick:e=>{e.preventDefault();update({section:heading.id});content.querySelector('#'+CSS.escape(heading.id))?.scrollIntoView({block:'start',behavior:'auto'});}},heading.text);
   toc.append(a);
  } reader.append(toc);
 }
 reader.append(content);
 const related=G.nodes.filter(n=>n.document===ref);
 const backlinks=Object.entries(G.documents).filter(([path,d])=>path!==ref && (d.text.includes('[['+ref.replace(/\.md$/,'')) || d.text.includes('[['+ref.split('/').pop().replace(/\.md$/,'')))).slice(0,12);
 if(related.length || backlinks.length){
  const links=el('section',{class:'backlinks'},el('h3',{},'Conexões desta fonte'));
  for(const n of related) links.append(row(n.label,'Entidade · '+n.type,()=>navigate({page:'graph',node:n.id,view:Object.keys(n.views)[0],q:'',evidence:'all',focus:null})));
  for(const [path] of backlinks) links.append(row(documentTitle(path),'Menciona esta fonte',()=>openDoc(path)));
  reader.append(links);
 }
 if(options.section)requestAnimationFrame(()=>{
  const found=rendered.headings.find(h=>h.id===options.section)||rendered.headings.find(h=>C.normalize(h.text)===C.normalize(options.section) || h.id===M.slug(options.section) || C.normalize(h.text).includes(C.normalize(options.section)));
  if(found)content.querySelector('#'+CSS.escape(found.id))?.scrollIntoView({block:'start'});else notify('A seção não foi encontrada. A fonte completa está disponível.');
 });
 return reader;
}
function formatDate(value){try {return new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short'}).format(new Date(value));}catch(_){return 'data indisponível';}}
function overview(main){
 main.append(head('WORKSPACE / KIOSK BRANDS','Seu conhecimento, conectado.','Explore decisões, sistemas e evidências. Encontre a fonte antes de dar o próximo passo.',[button('◎ Explorar grafo',()=>navigate({page:'graph'}),'primary')]));
 const pending=G.nodes.filter(n=>['parcial','proposto'].includes(n.evidence)).length;
 const stats=el('div',{class:'stats'});
 for(const [value,title,foot] of [[Object.keys(G.documents).length,'Fontes no vault','Documentos com origem e hash'],[G.nodes.length,'Entidades mapeadas','Sistemas, conceitos e infraestrutura'],[G.edges.length,'Relações documentadas','Com fonte e nível de evidência'],[pending,'Entidades a definir','Contratos e regras ainda pendentes']]){
  stats.append(el('div',{class:'panel stat'},el('div',{class:'stat-value'},value),el('div',{class:'stat-title'},title),el('div',{class:'stat-foot'},foot)));
 }
 main.append(stats);
 const map=el('section',{class:'panel'},panelTitle('O mapa do seu negócio','Três perspectivas. Uma base de conhecimento.',button('Ver todas →',()=>navigate({page:'graph'}),'subtle')));
 map.append(el('div',{class:'scope-map'},...G.views.map(v=>el('button',{class:'scope-node',onclick:()=>navigate({page:'graph',view:v.id})},el('strong',{},v.id==='flow'?'Fluxo logístico':v.id==='infra'?'Infraestrutura':'Entidades'),el('small',{},G.nodes.filter(n=>n.views[v.id]).length+' entidades')))));
 map.append(el('p',{class:'callout'},'Relações tracejadas mostram hipóteses ou contratos parciais. Evidência de código e implantação têm rótulos próprios; consulte sempre a fonte.'));
 const recent=el('section',{class:'panel'},panelTitle('Retome uma fonte','Favoritos e leituras recentes',button('Abrir biblioteca →',()=>navigate({page:'knowledge'}),'subtle')));
 const refs=[...new Set([...saved.favorites,...saved.recent,'systems/deploy-validacao-hub-2026-10-08.md','systems/rate-limiting-bling-producao.md','systems/backlog-analise-hub-logistico.md'])].filter(r=>G.documents[r]).slice(0,4);
 for(const ref of refs)recent.append(row(documentTitle(ref),saved.favorites.includes(ref)?'★ Favorito':'Fonte do vault',()=>openDoc(ref)));
 main.append(el('div',{class:'grid-2'},map,recent));
 const env=el('section',{class:'panel'},panelTitle('Produção e homologação','Documentação separada por ambiente'));
 for(const [title,ref,meta] of [['Produção','systems/hub-producao.md','hub.db · worker ativo · Espírito Santo automático'],['Homologação','systems/hub-homologacao.md','hub-homolog.db · emissão bloqueada · worker desligado']]){
  if(G.documents[ref])env.append(row(title,meta+' · conforme snapshot de 08/10',()=>openDoc(ref)));
 }
 env.append(el('p',{class:'legend-note'},'O dashboard lê documentação local. Saúde, fila e logs em tempo real exigem conexão de observabilidade.'));
 const next=el('section',{class:'panel'},panelTitle('Prepare a próxima evolução','Conhecimento → contexto → decisão'));
 const checklist=[['✓','Fontes verificáveis','Hashes, linhas e relações acompanham cada consulta.'],['✓','Planos de agentes','Modele dependências, papéis, ferramentas e orçamento.'],['→','Backend GraphRAG e execução','Contratos definidos; API, SSE e execução ainda não conectados.']];
 next.append(el('div',{class:'progress-list'},...checklist.map(([mark,title,description])=>el('div',{class:'progress-item'},el('span',{class:'progress-mark'},mark),el('div',{},el('strong',{},title),el('p',{},description))))));
 next.append(el('div',{class:'action-row'},button('Preparar um plano →',()=>navigate({page:'workflows'}),'subtle')));
 main.append(el('div',{class:'grid-2'},env,next));
}
function knowledge(main){
 main.append(head('BIBLIOTECA / FONTES','Conhecimento que você pode verificar.','Leia o vault, siga as conexões e mantenha as fontes importantes por perto.'));
 const results=el('div',{class:'source-list panel','aria-label':'Lista de fontes'}),count=el('div',{class:'result-count',role:'status','aria-live':'polite'});
 let reader=renderReader(route.doc,{section:route.section,lineStart:route.lineStart,lineEnd:route.lineEnd});
 const layout=el('div',{class:'knowledge-layout'},el('section',{'aria-label':'Fontes do vault'},count,results),reader);
 function list(){
  results.replaceChildren();
  let refs=route.q?C.search(G,route.q,{kind:'document',category:route.category,limit:50}):Object.entries(G.documents).filter(([ref])=>route.category==='all'||ref.split('/')[0]===route.category).map(([ref,d])=>({document:ref,label:d.title,snippet:C.stripFrontmatter(d.text).split(/\r?\n/).find(l=>l.trim()&&!l.startsWith('#'))||'',lineStart:1,lineEnd:1}));
  if(route.favorites==='1')refs=refs.filter(r=>saved.favorites.includes(r.document));
  count.textContent=refs.length+' fontes'+(route.q?' encontradas':'')+(route.favorites==='1'?' favoritas':'');
  if(!refs.length){results.append(empty('Nenhuma fonte encontrada','Tente outro termo ou remova os filtros.',button('Limpar filtros',()=>navigate({q:'',category:'all',favorites:null,doc:null}),'subtle')));return;}
  for(const hit of refs){
   const b=el('button',{class:'source-card','aria-pressed':String(route.doc===hit.document),onclick:()=>{
    update({doc:hit.document,section:null,lineStart:route.q?hit.lineStart:null,lineEnd:route.q?hit.lineEnd:null});
    saved.recent=[hit.document,...saved.recent.filter(r=>r!==hit.document)].slice(0,12);persist();
    const old=reader;reader=renderReader(hit.document,{lineStart:route.q?hit.lineStart:null,lineEnd:route.q?hit.lineEnd:null});old.replaceWith(reader);list();
    if(matchMedia('(max-width:650px)').matches){reader.focus({preventScroll:true});reader.scrollIntoView({block:'start'});}else results.querySelector('[aria-pressed=true]')?.focus({preventScroll:true});
   }},el('span',{class:'row-title'},(saved.favorites.includes(hit.document)?'★ ':'')+documentTitle(hit.document)),el('span',{class:'row-meta'},hit.document),el('span',{class:'snippet'},hit.snippet.slice(0,135)+(hit.snippet.length>135?'…':'')));
   results.append(b);
  }
 }
 const q=el('input',{type:'search',value:route.q,placeholder:'Buscar no texto completo…','aria-label':'Buscar fontes',oninput:e=>{update({q:e.target.value});list();}});
 const favorite=el('label',{class:'check-label'},el('input',{type:'checkbox',checked:route.favorites==='1',onchange:e=>{update({favorites:e.target.checked?'1':null});list();}}),'Só favoritos');
 main.append(el('div',{class:'filters'},el('label',{},'Texto completo',q),select('Categoria',Object.entries(categories),route.category,v=>{update({category:v});list();}),favorite),layout);
 list();
}
function globalSearch(){
 const results=$('global-results');results.replaceChildren();
 const q=$('global-query').value;
 if(!dataOK||!C){results.append(empty('Busca indisponível','Recarregue o snapshot para voltar a pesquisar.'));return;}
 if(!q.trim()){results.append(empty('O que você quer encontrar?','Busque entidades ou termos presentes nas fontes.'));return;}
 const hits=C.search(G,q,{limit:16});
 if(!hits.length){results.append(empty('Nenhum resultado','Tente palavras mais curtas ou busque na biblioteca completa.'));return;}
 results.append(el('p',{class:'small muted',role:'status'},hits.length+' resultados'));
 for(const hit of hits){
  results.append(el('button',{class:'search-result',onclick:()=>{$('search-dialog').close();if(hit.kind==='entity')navigate({page:'graph',node:hit.nodeId||hit.id,view:Object.keys(G.nodes.find(n=>n.id===(hit.nodeId||hit.id)).views)[0],q:'',evidence:'all',domain:null,focus:null,relation:null});else openDoc(hit.document,null,[hit.lineStart,hit.lineEnd]);}},el('strong',{},hit.label),badge(hit.kind==='entity'?'Entidade':'Fonte'),el('span',{class:'snippet'},hit.snippet.slice(0,180)),el('span',{class:'row-meta'},hit.document+' · linhas '+hit.lineStart+'–'+hit.lineEnd)));
 }
}
function render(){
 knowledgeProduct?.dispose();knowledgeProduct=null;
 window.BrainObservability?.dispose();
 window.BrainGraphUI?.dispose();
 const main=$('main');main.replaceChildren();route=readRoute();$('page-name').textContent=pages[route.page][1];
 document.body.classList.toggle('knowledge-product-mode',route.page==='graph'&&route.experience==='product'&&!!window.BrainKnowledgeView);
 $('navigation').replaceChildren(...NAV_GROUPS.map(group=>{
   if(group.page){const p=pages[group.page];return el('a',{class:'nav-item',href:'#page='+group.page,'aria-current':route.page===group.page?'page':null},el('span',{class:'nav-icon','aria-hidden':true},group.icon),group.label);}
   const active=group.children.includes(route.page);
   const details=el('details',{class:'nav-group',open:active||null});
   details.append(el('summary',{class:'nav-item nav-group-toggle','aria-expanded':String(active)},el('span',{class:'nav-icon','aria-hidden':true},group.icon),group.label));
   for(const id of group.children){const[icon,name]=pages[id];details.append(el('a',{class:'nav-item nav-sub',href:'#page='+id,'aria-current':route.page===id?'page':null},el('span',{class:'nav-icon','aria-hidden':true},icon),name));}
   return details;
  }));
 document.title=pages[route.page][1]+' · KIOSK Second Brain';
 if(!dataOK || !C || !M){main.append(empty('Não foi possível carregar o snapshot','Verifique graph-data.js e gere novamente o catálogo.',button('Tentar novamente',()=>location.reload(),'primary')));return;}
 if(route.page==='product'){if(window.BrainProductUI)window.BrainProductUI.render(main,api);else main.append(empty('Módulo de produto indisponível','Recarregue a página.',button('Tentar novamente',()=>location.reload())));}
  if(route.page==='architecture'){if(window.BrainArchitecture)window.BrainArchitecture.render(main,api);else main.append(empty('Módulo de arquitetura indisponível','Recarregue a página e verifique architecture-ui.js.',button('Tentar novamente',()=>location.reload())));}
 if(route.page==='observability')window.BrainObservability.render(main,api);
 if(route.page==='overview')overview(main);
 if(route.page==='knowledge')knowledge(main);
 if(route.page==='graph'){
  if(route.experience==='product'&&window.BrainKnowledgeView)knowledgeProduct=window.BrainKnowledgeView.mount(main,{graph:G,core:C,markdown:M,initialNode:route.node,initialQuery:route.q,onTechnical:()=>navigate({experience:null}),onStateChange:state=>update({node:state.nodeId,q:state.q})});
  else if(window.BrainGraphUI){if(window.BrainKnowledgeView)main.append(button('Explorar como produto',()=>navigate({experience:'product'}),'subtle'));window.BrainGraphUI.render(main,api);}
  else main.append(empty('Módulo do grafo indisponível','Recarregue a página e verifique graph-ui.js.',button('Tentar novamente',()=>location.reload())));
 }
 if(route.page==='teams'){if(window.BrainTeams)window.BrainTeams.render(main,api);else main.append(empty('Módulo de times indisponível','Recarregue a página e verifique teams-ui.js.',button('Tentar novamente',()=>location.reload())));}

  if(route.page==='playbooks'){
    main.append(head('PLAYBOOKS','Playbooks consolidados no JEV.','Gerencie e visualize playbooks diretamente na experiência do JEV.',[
      button('Abrir JEV em nova aba ↗',()=>window.open('./jev/index.html','_blank','noopener'),'subtle')
    ]));
    const frame=el('iframe',{src:'jev/index.html#tab=playbooks',title:'JEV — Playbooks',class:'jev-frame'});
    const unavailable=()=>frame.replaceWith(empty('JEV indisponível','O módulo de playbooks foi consolidado no JEV. Inicie o BFF ou rode npm run build em jev-app.',button('Tentar novamente',()=>render())));
    frame.addEventListener('load',()=>{if(window.BrainBridge)window.BrainBridge.registerIframe('jev-playbooks',frame);try{const doc=frame.contentDocument;if(!doc||!doc.getElementById('root')||doc.querySelector('meta[name=application-name]')?.content!=='jev-app')unavailable();}catch(_){unavailable();}});
    frame.onerror=unavailable;
    main.append(frame);
  }
  if(route.page==='queries'){if(window.BrainWorkbench)window.BrainWorkbench.render(main,api);else main.append(empty('Módulo de consultas indisponível','Recarregue a página e verifique workbench.js.',button('Tentar novamente',()=>location.reload())));}
  if(route.page==='workflows'){if(window.BrainAgentArena)window.BrainAgentArena.render(main,api);else if(window.BrainWorkbench)window.BrainWorkbench.render(main,api);else main.append(empty('Módulo de workflows e agentes indisponível','Recarregue a página.',button('Tentar novamente',()=>location.reload())));}
  if(route.page==='nexus'){
    main.append(head('NEXUS OFFICE','Escritório de agentes em tempo real.','Agentes executando tarefas reais com busca vetorial, queries SQL e aprovação humana.',[
      button('Abrir em nova aba ↗',()=>window.open('http://127.0.0.1:5173','_blank'),'subtle')
    ]));
    const frame=el('iframe',{src:'http://127.0.0.1:5173',style:'width:100%;height:calc(100vh - 180px);border:none;border-radius:8px;background:#0a0a0a;'});
    frame.addEventListener('load',()=>{if(window.BrainBridge)window.BrainBridge.registerIframe('nexus',frame);});
    frame.onerror=()=>{frame.replaceWith(empty('Nexus não está rodando','Inicie o servidor: .venv\\Scripts\\python.exe -m backend.ws_server e cd nexus && npm run dev',button('Tentar novamente',()=>render())));};
    main.append(frame);
  }
  if(route.page==='jev'){
    main.append(head('JEV','Evidência, luzes de teste e saúde do ambiente.','Regras com luz de teste e saúde separadas, playbooks e execuções do ambiente.',[
      button('Abrir em nova aba ↗',()=>window.open('./jev/index.html','_blank','noopener'),'subtle')
    ]));
    const frame=el('iframe',{src:'jev/index.html',title:'JEV',class:'jev-frame'});
    const unavailable=()=>frame.replaceWith(empty('JEV indisponível','Inicie o BFF com um link de sessão (python -m backend.server --issue-link) ou rode npm run build em jev-app.',button('Tentar novamente',()=>render())));
    frame.addEventListener('load',()=>{
      if(window.BrainBridge)window.BrainBridge.registerIframe('jev',frame);
      // Same-origin: a 401/404 body from the BFF loads fine in the frame, so inspect what actually loaded.
      try{
        const doc=frame.contentDocument;
        if(!doc||!doc.getElementById('root')||doc.querySelector('meta[name=application-name]')?.content!=='jev-app')unavailable();
      }catch(_){unavailable();}
    });
    frame.onerror=unavailable;
    main.append(frame);
  }
 if(route.page==='knowledge'&&route.doc&&!route.section&&matchMedia('(max-width:650px)').matches)requestAnimationFrame(()=>{const reader=main.querySelector('.reader');reader?.focus({preventScroll:true});reader?.scrollIntoView({block:'start'});});
 $('snapshot-label').textContent='Snapshot '+G.snapshot_id.slice(0,8)+' · '+formatDate(G.built_at);
 if(!storageOK)notify('Persistência indisponível. Alterações permanecem apenas nesta sessão.');
}
const api={el,button,badge,empty,confirmAction,notify,persist,navigate,update,head,panelTitle,select,exportJSON,copy,documentTitle,openDoc,renderReader,row,formatDate,graph:G,core:C,markdown:M,saved,categories,evidence,get route(){return route;}};
window.BrainUI=api;
document.querySelector('.skip').addEventListener('click',e=>{e.preventDefault();$('main').focus();$('main').scrollIntoView({block:'start'});});
window.addEventListener('hashchange',()=>{if(location.hash==='#main')return;render();$('main').focus({preventScroll:true});if(!route.section)window.scrollTo({top:0});});
$('search-open').addEventListener('click',()=>{$('search-dialog').showModal();globalSearch();$('global-query').focus();});
$('search-close').addEventListener('click',()=>$('search-dialog').close());
$('global-query').addEventListener('input',globalSearch);
$('help-open').addEventListener('click',()=>$('help-dialog').showModal());
$('help-close').addEventListener('click',()=>$('help-dialog').close());
$('theme').addEventListener('click',()=>{
  saved.theme=saved.theme==='dark'?'light':'dark';
  document.documentElement.dataset.theme=saved.theme;
  persist();
  $('theme').setAttribute('aria-label',saved.theme==='dark'?'Ativar tema claro':'Ativar tema escuro');
  if(window.BrainBridge){
    window.BrainBridge.send('nexus','THEME_SYNC',{theme:saved.theme});
    window.BrainBridge.send('jev','THEME_SYNC',{theme:saved.theme});
    window.BrainBridge.send('jev-playbooks','THEME_SYNC',{theme:saved.theme});
  }
});
document.addEventListener('keydown',e=>{if(knowledgeProduct)return;if(e.key==='Escape'){const open=document.querySelector('dialog[open]');if(open){e.preventDefault();open.close();}}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(!$('search-dialog').open)$('search-dialog').showModal();globalSearch();$('global-query').focus();}});
render();
})();
