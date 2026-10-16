'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {dom,find}=require('./topology-dom.cjs');
const DIR=path.join(__dirname,'..');
const graph=JSON.parse(fs.readFileSync(path.join(DIR,'graph-data.js'),'utf8').slice('window.KIOSK_GRAPH = '.length).trim().replace(/;$/,''));
function setup(storage={getItem(){return null;},setItem(){}}){
 const {document,main}=dom(),proto=Object.getPrototypeOf(main);document.createElementNS=(_,tag)=>document.createElement(tag);document.addEventListener=()=>{};document.removeEventListener=()=>{};
 if(!proto.showModal)proto.showModal=function(){this.open=true;};if(!proto.close)proto.close=function(){this.open=false;this.dispatch('close');};
 if(!proto.querySelectorAll)proto.querySelectorAll=function(selector){return find(this,n=>n.matches(selector));};
 let hooks,scene,dead=false,lastZoom=null;
 const modelPath=path.join(DIR,'knowledge-model.js');const window={BrainCore:require('../core.js'),BrainKnowledgeModel:fs.existsSync(modelPath)?require(modelPath):null,BrainMarkdown:{render(container,text){container.textContent=text;return {truncated:false};}},BrainKnowledgeMotion:{mount(svg,callbacks){hooks=callbacks;return {update(value){scene=value;},select(){},zoom(factor){lastZoom=factor;},fit(){},dispose(){dead=true;}};}}};
 const context=vm.createContext({window,document,localStorage:storage,navigator:{},matchMedia:()=>({matches:false}),Map,Set,Date,JSON,URLSearchParams,location:{hash:''}});
 const viewPath=path.join(DIR,'knowledge-view.js');if(fs.existsSync(viewPath))vm.runInContext(fs.readFileSync(viewPath,'utf8'),context);
 return {document,main,window,context,mount(){assert.ok(window.BrainKnowledgeView?.mount,'product view is implemented');return window.BrainKnowledgeView.mount(main,{graph,storage});},get hooks(){return hooks;},get scene(){return scene;},get dead(){return dead;},get lastZoom(){return lastZoom;}};
}
function button(root,label){const result=find(root,n=>n.tagName==='button'&&n.textContent.includes(label))[0];assert.ok(result,'button '+label);return result;}
test('product starts with a readable grouped overview and truthful development context',()=>{
 const h=setup(),app=h.mount();assert.match(h.main.textContent,/Em desenvolvimento/);assert.match(h.main.textContent,/85/);
 assert.ok(h.scene.nodes.length<=6,'overview progressively reveals categories, not 84 tiny labels');
 assert.match(h.main.textContent,/Explorar/);assert.match(h.main.textContent,/Biblioteca/);app.dispose();assert.ok(h.dead);
});
test('real query leads to a readable source and returns without changing the canonical graph',()=>{
 const before=JSON.stringify(graph),h=setup();h.mount();const input=find(h.main,n=>n.getAttribute('aria-label')==='Buscar no conhecimento')[0];assert.ok(input);
 input.dispatch('input',{target:{value:'NF real'}});assert.match(h.main.textContent,/RULE-001|PB-002|nota fiscal/i);
 const result=find(h.main,n=>n.tagName==='button'&&n.getAttribute('data-kp-source'))[0];assert.ok(result,'actual result opens a source');result.click();
 const dialog=find(h.main,'dialog')[0];assert.ok(dialog.open);assert.match(dialog.textContent,/NF|nota fiscal/i);assert.match(dialog.textContent,/Origem e referência/);
 button(dialog,'Fechar').click();assert.ok(!dialog.open);assert.equal(JSON.stringify(graph),before);
});
test('a category reveals real entities and an entity can be saved to a useful local collection',()=>{
 const h=setup(),app=h.mount();h.hooks.onNode(h.scene.nodes.find(n=>n.kind==='category'&&n.groupId==='agents'));
 const entity=h.scene.nodes.find(n=>n.kind==='entity');assert.ok(entity);h.hooks.onNode(entity);
 button(h.main,'Salvar item').click();button(h.main,'Salvos').click();assert.match(h.main.textContent,new RegExp(entity.label.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
 assert.equal(app.getState().section,'saved');
});
test('documented connection journey uses actual edges and no simulated agent activity',()=>{
 const h=setup(),app=h.mount();button(h.main,'Bling chega à transportadora').click();
 assert.ok(h.scene.edges.length>=2);assert.match(h.main.textContent,/Bling/);assert.match(h.main.textContent,/J&T/);
 assert.ok(h.scene.edges.every(e=>graph.edges.some(raw=>raw.id===e.id)),'shown path has real documented edge identities');
 assert.equal(app.getState().path.found,true);assert.doesNotMatch(h.main.textContent,/executou|tok\/s|agentes trabalhando/i);
});
test('blocked browser storage keeps local saving usable with a clear session-only notice',()=>{
 const h=setup({getItem(){throw new Error('denied');},setItem(){throw new Error('denied');}});h.mount();h.hooks.onNode(h.scene.nodes.find(n=>n.kind==='category'));
 h.hooks.onNode(h.scene.nodes.find(n=>n.kind==='entity'));button(h.main,'Salvar item').click();assert.match(h.main.textContent,/nesta sessão/i);
});
test('zoom controls pass magnification in the documented direction',()=>{
 const h=setup();h.mount();find(h.main,n=>n.getAttribute('aria-label')==='Aumentar zoom')[0].click();assert.ok(h.lastZoom>1,'plus zooms in');
 find(h.main,n=>n.getAttribute('aria-label')==='Diminuir zoom')[0].click();assert.ok(h.lastZoom<1,'minus zooms out');
});
test('search within saved items never expands into unsaved global matches',()=>{
 const h=setup({getItem(){return '["entity:maia"]';},setItem(){}});h.mount();button(h.main,'Salvos').click();
 find(h.main,n=>n.getAttribute('aria-label')==='Buscar no conhecimento')[0].dispatch('input',{target:{value:'NF real'}});
 assert.match(h.main.textContent,/Nenhum resultado/);assert.equal(find(h.main,n=>n.tagName==='button'&&n.getAttribute('data-kp-source')).length,0);
});
test('expanded card collections return to a bounded readable map without losing the full count',()=>{
 const h=setup();h.mount();h.hooks.onNode(h.scene.nodes.find(n=>n.kind==='category'&&n.groupId==='systems'));
 button(h.main,'Cartões').click();button(h.main,'Mostrar mais itens').click();assert.ok(h.scene.nodes.filter(n=>n.kind==='entity').length>12);
 button(h.main,'Mapa').click();assert.ok(h.scene.nodes.filter(n=>n.kind==='entity').length<=12);assert.equal(h.scene.total,37);
});
