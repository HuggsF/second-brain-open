/* Browser-side validation for a versioned static snapshot. No data is executable. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.BrainSchema=factory();})(typeof window!=='undefined'?window:globalThis,function(){
'use strict';
const evidence=new Set(['implementado','local','documentado','relatado','parcial','proposto']);
const isString=(s,max=500)=>typeof s==='string'&&s.length<=max;
const id=s=>isString(s,64)&&/^[a-zA-Z0-9][a-zA-Z0-9_-]*$/.test(s);
const record=r=>r&&typeof r==='object'&&!Array.isArray(r);
function validateSnapshot(g){
 const errors=[],fail=s=>errors.push(s);
 if(!record(g)||!Array.isArray(g.nodes)||!Array.isArray(g.edges)||!Array.isArray(g.views)||!record(g.documents))return {ok:false,errors:['Estrutura de snapshot inválida.']};
 if(g.version!==1)fail('Versão de snapshot não suportada.');
 if(g.nodes.length>5000||g.edges.length>30000||!g.views.length||Object.keys(g.documents).length>2000)fail('Limites do catálogo excedidos.');
 if(!isString(g.snapshot_id,64)||!/^[a-f0-9]{64}$/.test(g.snapshot_id))fail('Identidade de snapshot inválida.');
 const views=new Set(),nodes=new Map(),edges=new Set();
 for(const v of g.views){if(!record(v)||!id(v.id)||!isString(v.label,160)||views.has(v.id)){fail('Vista inválida ou duplicada.');continue;}views.add(v.id);}
 for(const [ref,d] of Object.entries(g.documents)){
  if(!isString(ref,500)||ref.split(/[\\/]/).includes('..')||!ref.endsWith('.md')||!record(d)||!isString(d.text,1000000)||!isString(d.sha256,64)||!/^[a-f0-9]{64}$/.test(d.sha256)||!Number.isInteger(d.lines)||d.lines<0)fail('Fonte inválida.');
 }
 for(const n of g.nodes){
  if(!record(n)||!id(n.id)||nodes.has(n.id)){fail('Entidade inválida ou duplicada.');continue;}nodes.set(n.id,n);
  if(!isString(n.label,240)||!isString(n.type,120)||!isString(n.domain,120)||!evidence.has(n.evidence)||!Object.hasOwn(g.documents,n.document))fail('Metadados de entidade inválidos.');
  for(const key of ['issues','aliases'])if(n[key]!=null&&(!Array.isArray(n[key])||n[key].length>100||!n[key].every(x=>isString(x,160))))fail('Lista de entidade inválida.');
  if(!record(n.views)||!Object.keys(n.views).length||!Object.entries(n.views).every(([view,p])=>views.has(view)&&Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)))fail('Posição de entidade inválida.');
 }
 for(const e of g.edges){
  if(!record(e)||!id(e.id)||edges.has(e.id)){fail('Relação inválida ou duplicada.');continue;}edges.add(e.id);
  if(!nodes.has(e.source)||!nodes.has(e.target)||!views.has(e.view)||!nodes.get(e.source)?.views?.[e.view]||!nodes.get(e.target)?.views?.[e.view]||!Object.hasOwn(g.documents,e.source_file)||!isString(e.relation,500)||!evidence.has(e.evidence))fail('Metadados de relação inválidos.');
 }
 return {ok:errors.length===0,errors:[...new Set(errors)]};
}
return Object.freeze({validateSnapshot});
});
