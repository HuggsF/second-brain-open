'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const Model = require('../knowledge-model.js');

function fixture() {
  return {
    snapshot_id: 'snapshot-test', built_at: '2026-10-15T10:00:00Z',
    nodes: [
      { id:'hub', label:'Hub Log\u00c3\u00adstico', type:'Sistema', domain:'hub', evidence:'implementado', document:'systems/hub.md', aliases:['Central de pedidos'], views:{flow:[0,0]} },
      { id:'maia', label:'Maia', type:'Agente IA', document:'systems/brief.md', evidence:'implementado', views:{agents:[0,0]} },
      { id:'gate', label:'Rule Gate', type:'Quality Gate', document:'systems/missing.md', evidence:'parcial', views:{agents:[0,0]} },
      { id:'ui', label:'Interface operacional', type:'Frontend SPA', document:'systems/hub.md', evidence:'documentado', views:{flow:[0,0]} },
      { id:'tpl', label:'Template ADR', type:'Template', document:'systems/brief.md', evidence:'documentado', views:{flow:[0,0]} }
    ],
    edges: [
      {id:'e1',source:'maia',target:'hub',relation:'consulta',source_file:'systems/hub.md',view:'flow',evidence:'documentado'},
      {id:'e2',source:'maia',target:'hub',relation:'consulta',source_file:'systems/hub.md',view:'ontology',evidence:'documentado'},
      {id:'e3',source:'hub',target:'maia',relation:'consulta',source_file:'systems/hub.md',view:'flow',evidence:'documentado'},
      {id:'e4',source:'maia',target:'hub',relation:'consulta',source_file:'systems/brief.md',view:'agents',evidence:'relatado'},
      {id:'e5',source:'hub',target:'ui',relation:'apresenta',source_file:'systems/hub.md',view:'flow',evidence:'documentado'}
    ],
    documents: {
      'systems/hub.md': {title:'Hub Logístico',text:'---\ntype: system\nstatus: active\n---\n# Hub Logístico\n\nO Hub Logístico organiza os pedidos e preserva a origem dos registros.\n\n## Regras\nToda emissão de etiqueta exige NF real para manter os dados fiscais consistentes. O processo registra a origem da nota, conserva a trilha de auditoria e permite consultar a documentação antes de qualquer operação no ambiente produtivo.\n',sha256:'a'.repeat(64),lines:11},
      'systems/brief.md': {title:'Catálogo',text:'---\ntype: system\nevidence: implementado\n---\n# Catálogo\n\nDocuments core backend services.\n',sha256:'b'.repeat(64),lines:8},
      'systems/title.md': {title:'Rollback',text:'---\nstatus: active\n---\n# Rollback\n\nEste arquivo descreve uma estratégia ainda em estudo.\n',sha256:'c'.repeat(64),lines:7}
    }
  };
}
function freeze(value) {
  if(value && typeof value==='object' && !Object.isFrozen(value)) {Object.freeze(value);for(const child of Object.values(value)) freeze(child);}
  return value;
}

test('build normalizes labels without changing frozen source records or invented proof', () => {
  const source=freeze(fixture()), before=JSON.stringify(source), model=Model.build(source);
  assert.equal(model.nodes.find(n=>n.id==='hub').label,'Hub Logístico');
  assert.strictEqual(model.nodes.find(n=>n.id==='hub').raw,source.nodes[0]);
  assert.strictEqual(model.documents,source.documents);
  assert.equal(model.snapshotId,'snapshot-test');
  assert.equal(model.builtAt,'2026-10-15T10:00:00Z');
  assert.equal(JSON.stringify(source),before);
  assert.doesNotMatch(model.nodes.find(n=>n.id==='maia').description,/Documents core|comprovad|validado|orquestra/i);
});

test('build separates absent sources from brief sources and counts source documents once', () => {
  const model=Model.build(fixture());
  assert.equal(model.nodes.find(n=>n.id==='hub').sourceBrief,false);
  assert.equal(model.nodes.find(n=>n.id==='maia').sourceBrief,true);
  assert.equal(model.nodes.find(n=>n.id==='gate').sourcePresent,false);
  assert.deepEqual(model.stats,{nodes:5,relations:4,documents:3,briefSources:2});
  assert.deepEqual(model.groups.map(g=>[g.id,g.count]),[['agents',1],['governance',1],['systems',1],['interfaces',1],['knowledge',1]]);
});

test('relations collapse only repeated perspectives while keeping direction and distinct sources', () => {
  const model=Model.build(fixture());
  assert.deepEqual(model.edges.map(e=>e.id),['e1','e3','e4','e5']);
  assert.deepEqual(model.edges[0].occurrenceViews,['flow','ontology']);
  assert.equal(model.edges[0].evidence,'documentado');
  assert.equal(model.edges[0].source_file,'systems/hub.md');
  const reversed=fixture();reversed.edges.reverse();reversed.nodes.reverse();
  assert.deepEqual(Model.build(reversed).edges.map(e=>[e.id,e.occurrenceViews]),model.edges.map(e=>[e.id,e.occurrenceViews]));
});

test('overview uses membership links only and never invents semantic relationships', () => {
  const scene=Model.overview(Model.build(fixture()));
  assert.equal(scene.nodes.length,6);
  assert.equal(scene.nodes[0].id,'@core');
  assert.equal(scene.nodes[0].subtitle,'5 itens');
  assert.equal(scene.nodes[1].id,'@group:agents');
  assert.deepEqual(scene.edges,[]);
  assert.equal(scene.links.length,5);
  assert.ok(scene.links.every(link=>link.kind==='membership' && link.source==='@core'));
});

test('group focus shows a bounded subset and includes only visual membership', () => {
  const source=fixture();source.nodes.push({...source.nodes[0],id:'other',label:'Outro sistema'});
  const scene=Model.focus(Model.build(source),{groupId:'systems',limit:1});
  assert.equal(scene.total,2);assert.equal(scene.shown,1);
  assert.equal(scene.nodes[0].id,'@group:systems');
  assert.equal(scene.nodes.filter(n=>n.kind==='entity').length,1);
  assert.equal(scene.nodes[1].id,'hub');
  assert.deepEqual(scene.edges,[]);
  assert.equal(scene.links[0].target,'hub');
});

test('entity focus retains selected entity and real one-hop relations without membership paths', () => {
  const scene=Model.focus(Model.build(fixture()),{nodeId:'hub',limit:2});
  assert.equal(scene.nodes[0].id,'hub');
  assert.equal(scene.total,3);assert.equal(scene.shown,2);
  assert.deepEqual(scene.nodes.map(n=>n.id),['hub','maia']);
  assert.deepEqual(scene.edges.map(e=>e.id),['e1','e3','e4']);
  assert.deepEqual(scene.links,[]);
  assert.deepEqual(Model.focus(Model.build(fixture()),{nodeId:'absent'}).nodes,[]);
});

test('search preserves Portuguese accent and alias matches without leaking YAML as evidence', () => {
  const model=Model.build(fixture());
  const hit=Model.search(model,'central de pedidos',{kind:'entity'})[0];
  assert.equal(hit.nodeId,'hub');assert.equal(hit.kind,'entity');
  assert.equal(Model.search(model,'logistico',{kind:'entity'})[0].label,'Hub Logístico');
  const maia=Model.search(model,'Maia',{kind:'entity'})[0];
  assert.equal(maia.matchKind,'catalog');
  assert.doesNotMatch(maia.snippet,/type:|status:|evidence:|Documents core/);
  assert.equal(Model.search(model,'zzzinexistente').length,0);
});

test('source search returns matching body lines and labels title-only results as catalog matches', () => {
  const model=Model.build(fixture());
  const hit=Model.search(model,'NF real',{kind:'document'})[0];
  assert.equal(hit.document,'systems/hub.md');assert.equal(hit.matchKind,'source');
  assert.match(hit.snippet,/NF real/);assert.ok(hit.lineStart>=7);
  assert.equal(model.documents[hit.document].text.split('\n').slice(hit.lineStart-1,hit.lineEnd).join('\n'),hit.snippet);
  const title=Model.search(model,'Rollback',{kind:'document'})[0];
  assert.equal(title.matchKind,'catalog');
  assert.doesNotMatch(title.snippet,/status:|^# Rollback/);
});

test('actual snapshot finds NF real in source bodies and builds deterministic scenes without mutation', () => {
  const context={window:{}};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../graph-data.js'),'utf8'),context);
  const snapshot=context.window.KIOSK_GRAPH,before=JSON.stringify(snapshot),model=Model.build(snapshot);
  assert.equal(model.stats.nodes,85);assert.equal(model.stats.documents,151);
  assert.ok(model.stats.relations<131 && model.stats.relations>53);
  assert.ok(model.stats.briefSources>=11);
  const hits=Model.search(model,'NF real',{kind:'document'});
  assert.ok(hits.some(h=>h.matchKind==='source' && /NF real/i.test(h.snippet)));
  assert.ok(hits.every(h=>!/^---\n|\n(?:type|status):/.test(h.snippet)));
  assert.deepEqual(Model.focus(model,{nodeId:'hub'}),Model.focus(Model.build(snapshot),{nodeId:'hub'}));
  assert.equal(JSON.stringify(snapshot),before);
});
