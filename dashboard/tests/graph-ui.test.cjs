'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {dom,find}=require('./topology-dom.cjs');
function setup(extraCount=0){
 const {document,U,main}=dom(),proto=Object.getPrototypeOf(main);
 if(!proto.querySelectorAll)proto.querySelectorAll=function(selector){return find(this,n=>n.matches(selector));};
 if(!Object.getOwnPropertyDescriptor(proto,'dataset'))Object.defineProperty(proto,'dataset',{get(){return Object.fromEntries(Object.entries(this.attributes).filter(([k])=>k.startsWith('data-')).map(([k,v])=>[k.slice(5),v]));}});
 if(!Object.getOwnPropertyDescriptor(proto,'classList'))Object.defineProperty(proto,'classList',{get(){return {add:name=>this.className+=' '+name,toggle:(name,on)=>{const classes=new Set(this.className.split(' '));if(on)classes.add(name);else classes.delete(name);this.className=[...classes].join(' ');}};}});
 document.createElementNS=(_,tag)=>document.createElement(tag);
 const nodes=['a','b'].map((id,i)=>({id,label:'Entidade '+id,type:'Sistema',domain:i?'platform':'infra',evidence:'documentado',document:'source.md',views:{ontology:[i*240,0]}}));
 for(let i=0;i<extraCount;i++)nodes.push({id:'extra'+i,label:'Extra '+i,type:'Sistema',domain:'infra',evidence:'documentado',document:'source.md',views:{ontology:[0,0]}});
 const graph={nodes,edges:[{id:'ab',source:'a',target:'b',relation:'depende de',view:'ontology',evidence:'documentado',source_file:'source.md'}],documents:{'source.md':{text:'Fonte.'}},views:[{id:'ontology',label:'Ontologia'}]};
 const route={page:'graph',view:'ontology',q:'',evidence:'all',hops:1};let calls=[],hooks,disposed=false,resizeCallback;
 Object.assign(U,{graph,route,core:require('../core.js'),evidence:{documentado:'Documentado'},saved:{graphMode:'map'},persist(){},notify(){},update:changes=>Object.assign(route,changes),navigate:changes=>Object.assign(route,changes),openDoc(){},empty:(title,description,action)=>U.el('div',{},title,description,action),panelTitle:(title,description)=>U.el('header',{},title,description)});
 U.select=(label,options,value,change)=>{const select=U.el('select',{'aria-label':label,onchange:e=>change(e.target.value)});select.value=value;return U.el('label',{},label,select);};
 const context=vm.createContext({window:{BrainGraphLayout:fs.existsSync(path.join(__dirname,'../graph-layout.js'))?require('../graph-layout.js'):undefined,BrainGraphScene:{mount(svg,options){hooks=options;return {update(scene,positions,opts){calls.push({scene,positions,opts});options.onFrame?.({positions,progress:1,options:opts});},select(){},dispose(){disposed=true;}};}}},document,matchMedia:()=>({matches:false}),requestAnimationFrame:fn=>{fn();return 1;},cancelAnimationFrame(){},ResizeObserver:class {constructor(callback){resizeCallback=callback;}observe(){}disconnect(){}},CSS:{escape:s=>s},Map,Set});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../graph-ui.js'),'utf8'),context);context.window.BrainGraphUI.render(main,U);
 return {U,main,calls,route,resize:()=>resizeCallback(),get hooks(){return hooks;},api:context.window.BrainGraphUI,get disposed(){return disposed;}};
}
test('category click transitions the full graph to layers while keeping semantic edges separate',()=>{
 const h=setup();assert.ok(h.calls.length,'graph uses the animated scene renderer');
 assert.equal(h.calls.at(-1).opts.layout,'radial');
 const category=h.calls.at(-1).scene.nodes.find(n=>n.kind==='category'&&n.domain==='infra');h.hooks.onNode(category);
 assert.equal(h.route.layout,'layered');assert.equal(h.route.categoryFocus,'infra');assert.equal(h.calls.at(-1).opts.layout,'layered');
 assert.equal(h.calls.at(-1).scene.edges.length,1);assert.equal(h.calls.at(-1).scene.nodes.filter(n=>n.kind==='entity').length,2);
 const reset=find(h.main,n=>n.tagName==='button'&&n.textContent==='Voltar ao núcleo')[0];reset.click();assert.equal(h.route.layout,'radial');
 h.api.dispose();assert.ok(h.disposed);
});
test('entity selection still opens the inspector and zero-result filters clear the scene',()=>{
 const h=setup();assert.ok(h.calls.length,'animated scene mounted');h.hooks.onNode({id:'a',entityId:'a',kind:'entity',domain:'infra'});
 assert.equal(h.route.node,'a');assert.match(h.main.textContent,/Fonte: source.md/);
 const input=find(h.main,n=>n.getAttribute('aria-label')==='Buscar entidades')[0];input.dispatch('input',{target:{value:'no-such-node'}});
 assert.match(h.main.textContent,/Nenhuma entidade nesta seleção/);assert.equal(h.calls.at(-1).scene.nodes.length,0);
});
test('category focus frames its hierarchy and a full-frame control restores the surrounding graph',()=>{
 const h=setup();assert.ok(h.calls.length);const svg=find(h.main,'svg')[0];
 const initialWidth=Number(svg.getAttribute('viewBox').split(' ')[2]);
 h.hooks.onNode(h.calls.at(-1).scene.nodes.find(n=>n.kind==='category'&&n.domain==='infra'));
 const focusedWidth=Number(svg.getAttribute('viewBox').split(' ')[2]);assert.ok(focusedWidth<initialWidth,'focusing a category zooms into its visible subtree');
 find(h.main,n=>n.tagName==='button'&&n.textContent==='Enquadrar')[0].click();
 assert.ok(Number(svg.getAttribute('viewBox').split(' ')[2])>focusedWidth,'full frame includes surrounding domains');
 assert.ok(find(h.main,n=>n.getAttribute('aria-label')==='Foco de categoria')[0],'full-size category control remains accessible on dense overview');
});
test('dense category focus keeps text legible while preserving offscreen context for pan and full frame',()=>{
 const h=setup(53);assert.ok(h.calls.length);h.hooks.onNode(h.calls.at(-1).scene.nodes.find(n=>n.kind==='category'&&n.domain==='infra'));
 const bounds=find(h.main,'svg')[0].getAttribute('viewBox').split(' ').map(Number);
 assert.ok(bounds[2]<=900*12/11+1,'12px labels retain at least 11px apparent size in focus');
 assert.ok(bounds[3]<=455*12/11+1);assert.equal(h.calls.at(-1).scene.nodes.filter(n=>n.kind==='entity').length,55);
});
test('choosing an orbit view persists map preference after the equivalent list was active',()=>{
 const h=setup();find(h.main,n=>n.tagName==='button'&&n.textContent==='Lista')[0].click();assert.equal(h.U.saved.graphMode,'list');
 find(h.main,n=>n.tagName==='button'&&n.textContent==='Órbitas')[0].click();assert.equal(h.U.saved.graphMode,'map');
});
test('path finding releases category camera focus so a cross-domain path can be framed',()=>{
 const h=setup();h.hooks.onNode(h.calls.at(-1).scene.nodes.find(n=>n.kind==='category'&&n.domain==='infra'));
 find(h.main,n=>n.tagName==='button'&&n.textContent==='Encontrar caminho')[0].click();assert.equal(h.route.categoryFocus,null);
 assert.match(h.main.textContent,/Entidade a → Entidade b/);assert.equal(h.calls.at(-1).opts.focusDomain,null);
});
test('explicit full framing includes the whole graph on a narrow viewport',()=>{
 const h=setup(30),surface=find(h.main,n=>n.className==='graph-surface')[0];surface.clientWidth=375;surface.clientHeight=390;
 find(h.main,n=>n.tagName==='button'&&n.textContent==='Enquadrar')[0].click();
 const [x,y,width,height]=find(h.main,'svg')[0].getAttribute('viewBox').split(' ').map(Number);
 for(const point of h.calls.at(-1).positions.values())assert.ok(point.x>=x&&point.x<=x+width&&point.y>=y&&point.y<=y+height,'all retained nodes fit on explicit overview');
});
test('resize observer preserves readable category focus and ignores its initial delivery',()=>{
 const h=setup(53),svg=find(h.main,'svg')[0];h.hooks.onNode(h.calls.at(-1).scene.nodes.find(n=>n.kind==='category'&&n.domain==='infra'));
 const initial=svg.getAttribute('viewBox');h.resize();assert.equal(svg.getAttribute('viewBox'),initial,'initial size delivery must not override focus');
 const surface=find(h.main,n=>n.className==='graph-surface')[0];surface.clientWidth=640;surface.clientHeight=400;h.resize();
 assert.ok(Number(svg.getAttribute('viewBox').split(' ')[2])<=640*12/11+1);assert.equal(h.route.categoryFocus,'infra');
});
