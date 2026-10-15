/* Local presentation model. Group membership is never a semantic relationship. */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./core.js'));
  else root.BrainKnowledgeModel = factory(root.BrainCore);
})(typeof window !== 'undefined' ? window : globalThis, function (Core) {
  'use strict';

  const GROUPS = [
    {id:'agents',label:'Agentes de IA',description:'Papéis e agentes presentes no catálogo.',token:'accent'},
    {id:'governance',label:'Governança e skills',description:'Políticas, verificações e capacidades documentadas.',token:'blue'},
    {id:'systems',label:'Sistemas e dados',description:'Sistemas, serviços, ambientes e armazenamento.',token:'warn'},
    {id:'interfaces',label:'Interfaces e integrações',description:'Interfaces e pontos de conexão entre sistemas.',token:'good'},
    {id:'knowledge',label:'Conhecimento e modelos',description:'Protocolos, modelos e estruturas de conhecimento.',token:'violet'}
  ];
  const STOP = new Set('a ao aos as o os um uma de da das do dos e em no na nos nas para por com que qual quais como quando onde porque se ou sobre pelo pela pelos pelas the of and to in on for is are what how why'.split(' '));
  const WINDOWS_BYTES = {'€':128,'‚':130,'ƒ':131,'„':132,'…':133,'†':134,'‡':135,'ˆ':136,'‰':137,'Š':138,'‹':139,'Œ':140,'Ž':142,'‘':145,'’':146,'“':147,'”':148,'•':149,'–':150,'—':151,'˜':152,'™':153,'š':154,'›':155,'œ':156,'ž':158,'Ÿ':159};
  const byId = (a,b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  const bounded = (value,fallback,min,max) => Number.isFinite(Number(value)) ? Math.max(min,Math.min(max,Math.floor(Number(value)))) : fallback;

  // Decode only recognizable byte sequences; ordinary Portuguese and literal replacement characters survive.
  function readable(value) {
    let text=String(value == null ? '' : value);
    for(let pass=0;pass<2;pass++) {
      const next=text.replace(/[\u00c2-\u00f4](?:[\u0080-\u00bf]|[€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ]){1,3}/g, part => {
        const bytes=Array.from(part,c=>WINDOWS_BYTES[c] ?? c.charCodeAt(0));
        try {return decodeURIComponent(bytes.map(n=>'%'+n.toString(16).padStart(2,'0')).join(''));} catch(_) {return part;}
      });
      if(next===text)break;
      text=next;
    }
    return text;
  }
  function normalize(value) {return Core.normalize(readable(value));}
  function tokens(query) {return [...new Set((normalize(query).match(/[a-z0-9]+/g)||[]).filter(t=>t.length>1&&!STOP.has(t)))].slice(0,32);}
  function groupFor(node) {
    const type=normalize(node.type),id=String(node.id);
    if(type.includes('agente') || /^(?:maia|noah|theo|lia|eva|persona_)/.test(id))return 'agents';
    if(/quality gate|policy|skill/.test(type) || /^(?:policy_|skill_|.*_gate$|gate_pipeline$)/.test(id) || ['evidence_tree','work_orders'].includes(id))return 'governance';
    if(/template|protocolo|dominio/.test(type))return 'knowledge';
    if(/frontend|integracao|adapter|fastmcp/.test(type) || /^mcp_/.test(id))return 'interfaces';
    return 'systems';
  }
  function bodyLines(document) {
    const lines=String(document?.text||'').split(/\r?\n/);
    let first=0;
    if(lines[0]?.replace(/^\uFEFF/,'')==='---') {
      const end=lines.findIndex((line,index)=>index>0&&line.trim()==='---');
      first=end<0?lines.length:end+1;
    }
    const body=[];
    for(let i=first;i<lines.length;i++) {
      const text=lines[i];
      if(!text.trim() || /^\s{0,3}(?:#{1,6}\s|`{3,}|~{3,}|[-*_]{3,}\s*$)/.test(text))continue;
      body.push({text,line:i+1});
    }
    return {lines,body};
  }
  function brief(document) {
    const text=bodyLines(document).body.map(line=>line.text).join(' ');
    return (text.match(/[\p{L}\p{N}]+/gu)||[]).length<40;
  }
  function passage(document,query) {
    const parsed=bodyLines(document),words=tokens(query),phrase=normalize(query);
    if(!words.length)return null;
    let best=null;
    for(const item of parsed.body) {
      const line=normalize(item.text),found=words.filter(word=>line.includes(word));
      if(!found.length)continue;
      const score=found.length*10+(phrase&&line.includes(phrase)?20:0);
      if(!best||score>best.score)best={...item,score};
    }
    if(!best)return null;
    return {snippet:best.text,lineStart:best.line,lineEnd:best.line};
  }
  function build(snapshot={}) {
    const documents=snapshot.documents && typeof snapshot.documents==='object' && !Array.isArray(snapshot.documents)?snapshot.documents:{};
    const ids=new Set(),nodes=[];
    for(const raw of Array.isArray(snapshot.nodes)?snapshot.nodes:[]) {
      if(!raw || typeof raw.id!=='string' || ids.has(raw.id))continue;
      ids.add(raw.id);
      const label=readable(raw.label||raw.id),type=readable(raw.type||'Item'),groupId=groupFor(raw);
      const sourcePresent=Object.hasOwn(documents,raw.document)&&typeof documents[raw.document]?.text==='string';
      const doc=sourcePresent?documents[raw.document]:null;
      // A linked document may describe a whole subsystem without mentioning this particular entity.
      const excerpt=doc?passage(doc,label.replace(/\([^)]*\)/g,'')):null;
      const description=excerpt?readable(excerpt.snippet).slice(0,260):type+' presente no catálogo. '+(sourcePresent?'Consulte a fonte vinculada para ler o contexto.':'A fonte vinculada não está neste snapshot.');
      nodes.push({raw,id:raw.id,label,type,groupId,document:raw.document||null,evidence:raw.evidence||'documentado',description,sourceBrief:sourcePresent&&brief(doc),sourcePresent});
    }
    nodes.sort(byId);
    const canonical=new Map();
    for(const raw of (Array.isArray(snapshot.edges)?snapshot.edges:[]).filter(e=>e&&typeof e.id==='string').slice().sort(byId)) {
      if(!ids.has(raw.source)||!ids.has(raw.target))continue;
      const signature=JSON.stringify([raw.source,raw.target,raw.relation,raw.source_file]);
      if(canonical.has(signature)) {
        const edge=canonical.get(signature);
        if(raw.view&&!edge.occurrenceViews.includes(raw.view))edge.occurrenceViews.push(raw.view);
      }else canonical.set(signature,{...raw,raw,relation:readable(raw.relation),occurrenceViews:raw.view?[raw.view]:[]});
    }
    const edges=[...canonical.values()];for(const edge of edges)edge.occurrenceViews.sort();
    const groups=GROUPS.map(group=>({...group,count:nodes.filter(n=>n.groupId===group.id).length}));
    return {nodes,edges,groups,documents,stats:{nodes:nodes.length,relations:edges.length,documents:Object.keys(documents).length,briefSources:Object.values(documents).filter(brief).length},snapshotId:snapshot.snapshot_id||null,builtAt:snapshot.built_at||null};
  }
  function search(model,query,{limit=16,kind='all'}={}) {
    limit=bounded(limit,16,0,50);
    if(!limit || !tokens(query).length || !['all','entity','document'].includes(kind))return [];
    const graph={nodes:model.nodes.map(n=>({...n.raw,label:n.label,type:n.type,aliases:(n.raw.aliases||[]).map(readable)})),edges:model.edges,documents:model.documents};
    return Core.search(graph,readable(query),{limit:50,kind}).map(hit=>{
      const node=hit.nodeId?model.nodes.find(n=>n.id===hit.nodeId):null;
      const source=model.documents[hit.document],excerpt=source?passage(source,query):null;
      const label=readable(node?.label||source?.title||hit.label);
      if(!excerpt && hit.kind==='document' && !tokens(query).some(word=>normalize(label+' '+hit.document).includes(word)))return null;
      return {...hit,label,matchKind:excerpt?'source':'catalog',snippet:excerpt?excerpt.snippet:(node?.description||'Correspondência no título ou na referência. Abra a fonte para ler o contexto.'),lineStart:excerpt?.lineStart||0,lineEnd:excerpt?.lineEnd||0,sourceBrief:source?brief(source):false};
    }).filter(Boolean).slice(0,limit);
  }
  function category(group) {return {id:'@group:'+group.id,kind:'category',label:group.label,subtitle:group.count+' itens',count:group.count,groupId:group.id,token:group.token};}
  function entity(node,model) {return {...node,kind:'entity',subtitle:node.type,entityId:node.id,token:model.groups.find(g=>g.id===node.groupId).token};}
  function membership(source,target) {return {id:'@membership:'+JSON.stringify([source,target]),source,target,kind:'membership'};}
  function overview(model) {
    return {nodes:[{id:'@core',kind:'core',label:'Seu segundo cérebro',subtitle:model.nodes.length+' itens'},...model.groups.map(category)],edges:[],links:model.groups.map(group=>membership('@core','@group:'+group.id))};
  }
  function focus(model,{groupId,nodeId,limit=12}={}) {
    const empty={nodes:[],edges:[],links:[],total:0,shown:0};
    if(nodeId) {
      const selected=model.nodes.find(node=>node.id===nodeId);if(!selected)return empty;
      const adjacent=new Set();
      for(const edge of model.edges) {if(edge.source===nodeId)adjacent.add(edge.target);if(edge.target===nodeId)adjacent.add(edge.source);}
      adjacent.delete(nodeId);
      const candidates=model.nodes.filter(node=>adjacent.has(node.id));
      const nodes=[selected,...candidates].slice(0,bounded(limit,12,1,5000)).map(node=>entity(node,model));
      const visible=new Set(nodes.map(node=>node.id));
      return {nodes,edges:model.edges.filter(edge=>visible.has(edge.source)&&visible.has(edge.target)),links:[],total:candidates.length+1,shown:nodes.length};
    }
    const group=model.groups.find(item=>item.id===groupId);if(!group)return empty;
    const candidates=model.nodes.filter(node=>node.groupId===groupId),nodes=candidates.slice(0,bounded(limit,12,0,5000)).map(node=>entity(node,model));
    return {nodes:[category(group),...nodes],edges:[],links:nodes.map(node=>membership('@group:'+groupId,node.id)),total:candidates.length,shown:nodes.length};
  }
  return Object.freeze({build,search,overview,focus});
});
