'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),{dom,find}=require('./topology-dom.cjs');
let UI;
try { UI=require('../hub-topology-ui.js'); } catch(error) { if(error.code!=='MODULE_NOT_FOUND')throw error;UI={}; }
function model(environment='production') {
 return {environment,nodes:[
  {id:'process',label:'Hub / processo PM2',status:'green',reason:'Processo online nas duas amostras.',observedAt:1000,ageSeconds:5,checks:[{label:'Estado PM2',value:'online / online',expected:'online',ok:true}]},
  {id:'internal',label:'HTTP interno',status:'green',reason:'HTTP interno respondeu.',observedAt:1000,ageSeconds:5,checks:[]},
  {id:'external',label:'HTTP público',status:'red',reason:'Resposta pública incompatível.',observedAt:1000,ageSeconds:5,checks:[{label:'Resposta',value:503,expected:200,ok:false}]},
  {id:'database',label:'SQLite / fila',status:'unknown',reason:'Banco sem evidência suficiente.',observedAt:1000,ageSeconds:5,checks:[]}
 ],edges:[{source:'internal',target:'process',relation:'atendido pelo Hub',sourceRef:'hub-logistico/server.js:25'},{source:'external',target:'process',relation:'atendido pelo Hub',sourceRef:'hub-logistico/server.js:25'},{source:'process',target:'database',relation:'usa SQLite',sourceRef:'hub-logistico/health.js:19'}],observation:{id:4,collectedAt:1000,source:'MCP'},collection:{status:'ok',lastAttemptAt:1000},summary:{status:'red',reason:'Há falha na janela observada.'}};
}
function nodeButton(root,id,view='map') { return find(root,item=>item.tagName==='button'&&item.getAttribute('data-node-id')===id&&item.getAttribute('data-view')===view)[0]; }
function details(root) { return find(root,item=>item.getAttribute('data-topology-details')==='true')[0]; }
test('map and equivalent list expose four aspects with text statuses',()=>{
 const {U,main}=dom();assert.equal(typeof UI.render,'function','Topology renderer is missing');const root=UI.render(model(),U);main.append(root);
 for(const id of ['process','internal','external','database']){assert.ok(nodeButton(root,id));assert.ok(nodeButton(root,id,'list'));}
 assert.match(root.textContent,/Saudável/);assert.match(root.textContent,/Falha observada/);assert.match(root.textContent,/Desconhecido/);
 assert.equal(find(root,'a').length,0);
});
test('native keyboard selection reveals checks and directed dependencies',()=>{
 const {U,main}=dom();assert.equal(typeof UI.render,'function','Topology renderer is missing');const root=UI.render(model(),U);main.append(root);
 const button=nodeButton(root,'process');button.focus();button.press('Enter');
 assert.equal(button.getAttribute('aria-pressed'),'true');assert.equal(nodeButton(root,'process','list').getAttribute('aria-pressed'),'true');
 const panel=details(root);assert.match(panel.textContent,/Estado PM2/);assert.match(panel.textContent,/online/);assert.match(panel.textContent,/Última tentativa/);
 const depends=find(panel,item=>item.getAttribute('data-dependencies')==='dependsOn')[0];
 const dependents=find(panel,item=>item.getAttribute('data-dependencies')==='dependents')[0];
 assert.match(depends.textContent,/SQLite/);assert.doesNotMatch(depends.textContent,/HTTP/);
 assert.match(dependents.textContent,/HTTP interno/);assert.match(dependents.textContent,/HTTP público/);
 assert.match(panel.textContent,/hub-logistico\/health.js:19/);
 nodeButton(root,'external','list').press(' ');assert.match(details(root).textContent,/Resposta pública incompatível/);assert.match(details(root).textContent,/503/);
});
test('selection stays local to its environment and returns the selected aspect',()=>{
 const {U,main}=dom();assert.equal(typeof UI.render,'function','Topology renderer is missing');const selections=[];const prod=UI.render(model(),U,{selectedId:'process',onSelect:id=>selections.push(id)}),hml=UI.render(model('hml'),U);main.append(prod,hml);
 nodeButton(prod,'database','list').click();assert.deepEqual(selections,['database']);assert.equal(nodeButton(hml,'database').getAttribute('aria-pressed'),'false');
 const ids=find(main,item=>item.getAttribute('id')).map(item=>item.getAttribute('id'));assert.equal(new Set(ids).size,ids.length);
});
test('server-like text and relationship sources stay inert',()=>{
 const {U,main}=dom();assert.equal(typeof UI.render,'function','Topology renderer is missing');const value=model();value.nodes[0].reason='<img src=x onerror=evil()>';value.edges[2].sourceRef='javascript:evil()';
 const root=UI.render(value,U,{selectedId:'process'});main.append(root);assert.match(details(root).textContent,/<img src=x onerror=evil\(\)>/);assert.equal(find(root,'img').length,0);assert.equal(find(root,'script').length,0);assert.equal(find(root,'a').length,0);
});
module.exports={model};
