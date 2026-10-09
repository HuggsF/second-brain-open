'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const C=require('../core.js'),S=require('../schema.js'),M=require('../markdown.js');
const raw=fs.readFileSync(path.join(__dirname,'../graph-data.js'),'utf8');
const graph=JSON.parse(raw.slice('window.KIOSK_GRAPH = '.length).trim().replace(/;$/,''));
test('generated snapshot validates and environments have distinct sources',()=>{
 assert.equal(S.validateSnapshot(graph).ok,true);
 assert.notEqual(graph.nodes.find(n=>n.id==='prod').document,graph.nodes.find(n=>n.id==='hml').document);
 for(const id of ['hub','hml','job','emissao']){
  const deployment=graph.nodes.find(n=>n.id===id).deployment;
  assert.match(deployment.sha,/^[0-9a-f]{40}$/);
  assert.ok(graph.documents[deployment.source].text.includes(deployment.sha),'Deployment source must substantiate the declared SHA');
 }
});
test('J&T acronym remains searchable without enabling empty/stopword matches',()=>{
 assert.ok(C.search(graph,'J&T',{kind:'entity'}).some(hit=>hit.nodeId==='jt'));
 assert.deepEqual(C.search(graph,'a e o'),[]);
});
test('actual citations match original line ranges and byte hashes',()=>{
 for(const query of ['rastreio cancelado','rollback produção','múltiplos volumes','J&T']){
  const result=C.retrieve(graph,query,{limit:6,hops:2});assert.ok(result.citations.length);
  for(const citation of result.citations){
   const source=graph.documents[citation.document];
   assert.equal(source.sha256,citation.sha256);
   assert.equal(source.text.split(/\r?\n/).slice(citation.lineStart-1,citation.lineEnd).join('\n'),citation.text);
   assert.ok(citation.lineStart>=1&&citation.lineEnd<=source.lines);
   const bytes=fs.readFileSync(path.join(process.env.BRAIN_VAULT||'C:/KIOSK/second-brain/vault',citation.document));
   assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),citation.sha256,citation.document);
  }
  assert.ok(result.nodes.every(id=>graph.nodes.some(n=>n.id===id)));
  assert.ok(result.edges.every(id=>graph.edges.some(e=>e.id===id)));
 }
});
test('malformed snapshots fail without throwing, including nullable/prototype references',()=>{
 for(const change of [
  g=>delete g.documents,g=>g.version=99,g=>g.views=[null],g=>g.nodes[0].views={},g=>g.nodes[0].issues='DEM-01',
  g=>delete g.edges[0].id,g=>g.edges[1].id=g.edges[0].id,g=>g.nodes[0].document='__proto__',
  g=>g.nodes[0].views.flow=[Infinity,0],g=>g.edges[0].target='missing'
 ]){
  const copy=structuredClone(graph);change(copy);assert.equal(S.validateSnapshot(copy).ok,false);
 }
 assert.equal(S.validateSnapshot(null).ok,false);
});
test('runaway budgets, cycles and external tools cannot be exported as valid plans',()=>{
 const plan={version:1,steps:[{id:'one',name:'A',role:'researcher',dependsOn:[],tools:['read_sources'],budgetSeconds:60}]};
 assert.equal(C.validatePlan(plan).ok,true);
 for(const budget of [1e308,86401,0,-1,NaN]){plan.steps[0].budgetSeconds=budget;assert.equal(C.validatePlan(plan).ok,false);}
 plan.steps[0].budgetSeconds=60;plan.steps[0].tools=['ssh'];assert.equal(C.validatePlan(plan).ok,false);
 plan.steps[0].tools=['search'];plan.steps[0].dependsOn=['one'];assert.equal(C.validatePlan(plan).ok,false);
});
test('bounded markdown exposes truncated code, rather than pretending to show complete source',()=>{
 const blocks=M.parseBlocks('~~~js\n'+'x'.repeat(M.limits.code+1)+'\n~~~');
 assert.equal(blocks[0].truncated,true);assert.equal(blocks[0].text.length,M.limits.code);
});
test('disconnected environments and unmatched query do not invent graph context',()=>{
 assert.equal(C.shortestPath(graph,'prod','pedido').found,false);
 const result=C.retrieve(graph,'zzzzqueryneverexists');
 assert.equal(result.citations.length,0);assert.equal(result.nodes.length,0);assert.equal(result.edges.length,0);
 assert.ok(result.gaps.length>0);
});
