'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {dom,find}=require('./topology-dom.cjs');

function setup(reduced=false){
 const {document,main}=dom();document.createElementNS=(_,tag)=>document.createElement(tag);document.head=document.createElement('head');
 const svg=document.createElementNS('', 'svg');main.append(svg);
 let now=0,id=0;const frames=new Map();
 const context=vm.createContext({window:{},document,Map,Set,performance:{now:()=>now},matchMedia:()=>({matches:reduced}),requestAnimationFrame:fn=>{frames.set(++id,fn);return id;},cancelAnimationFrame:key=>frames.delete(key)});
 const file=path.join(__dirname,'../graph-scene.js');
 if(fs.existsSync(file))vm.runInContext(fs.readFileSync(file,'utf8'),context);
 return {svg,main,frames,api:context.window.BrainGraphScene,tick(time){now=time;const callbacks=[...frames.values()];frames.clear();callbacks.forEach(fn=>fn(time));}};
}
const scene={nodes:[{id:'@core',kind:'core',label:'AI-OS'},{id:'a',kind:'entity',label:'Fonte A',domain:'infra'},{id:'b',kind:'entity',label:'Fonte B',domain:'infra'}],links:[{id:'member',source:'@core',target:'a',kind:'membership'}],edges:[{id:'ab',source:'a',target:'b',relation:'depends_on'},{id:'ba',source:'b',target:'a',relation:'reports_to'}]};
const positions=x=>new Map([['@core',{x:0,y:0}],['a',{x,y:0}],['b',{x:x+240,y:0}]]);

test('scene keeps the same focused node while interpolating nodes and directed edges',()=>{
 const h=setup();assert.equal(typeof h.api?.mount,'function','SVG scene renderer is available');
 const renderer=h.api.mount(h.svg,{});renderer.update(scene,positions(100),{animate:false});
 const node=find(h.svg,n=>n.getAttribute('data-scene-node')==='a')[0];node.focus();
 const edge=find(h.svg,n=>n.getAttribute('data-scene-edge')==='ab')[0];
 assert.equal(node.getAttribute('transform'),'translate(100 0)');assert.equal(edge.getAttribute('marker-end'),'url(#brain-scene-arrow)');
 const initialPath=edge.getAttribute('d');renderer.update(scene,positions(500),{duration:650});h.tick(325);
 assert.equal(node.getAttribute('transform'),'translate(300 0)');assert.notEqual(edge.getAttribute('d'),initialPath);
 assert.equal(node.ownerDocument.activeElement,node);assert.equal(find(h.svg,n=>n.getAttribute('data-scene-node')==='a')[0],node);
 h.tick(650);assert.equal(node.getAttribute('transform'),'translate(500 0)');assert.equal(h.frames.size,0);
});

test('rapid layout change starts from the visible frame and dispose cancels animation',()=>{
 const h=setup();assert.ok(h.api,'renderer exists');const renderer=h.api.mount(h.svg,{});
 renderer.update(scene,positions(100),{animate:false});renderer.update(scene,positions(500),{duration:650});h.tick(325);
 renderer.update(scene,positions(700),{duration:650});h.tick(650);
 const node=find(h.svg,n=>n.getAttribute('data-scene-node')==='a')[0];assert.equal(node.getAttribute('transform'),'translate(500 0)');
 renderer.dispose();assert.equal(h.frames.size,0);h.tick(975);assert.equal(node.getAttribute('transform'),'translate(500 0)');
});

test('reduced motion jumps to target; categories and semantic edges are keyboard selectable',()=>{
 const h=setup(true);assert.ok(h.api,'renderer exists');let chosen=null,edgeId=null;
 const renderer=h.api.mount(h.svg,{onNode:node=>chosen=node.id,onEdge:edge=>edgeId=edge.id});
 renderer.update(scene,positions(500));assert.equal(h.frames.size,0);
 find(h.svg,n=>n.getAttribute('data-scene-node')==='a')[0].press('Enter');assert.equal(chosen,'a');
 find(h.svg,n=>n.getAttribute('data-scene-edge-target')==='ab')[0].press(' ');assert.equal(edgeId,'ab');
 const member=find(h.svg,n=>n.getAttribute('data-scene-link')==='member')[0];assert.equal(member.getAttribute('marker-end'),null);
 const reverse=find(h.svg,n=>n.getAttribute('data-scene-edge')==='ba')[0];
 assert.notEqual(reverse.getAttribute('d'),find(h.svg,n=>n.getAttribute('data-scene-edge')==='ab')[0].getAttribute('d'),'reciprocal edges have separate curves');
 renderer.select('a',['ab']);assert.match(find(h.svg,n=>n.getAttribute('data-scene-node')==='a')[0].getAttribute('class'),/selected/);
});

test('filter updates remove old nodes and disconnected surfaces do not keep animating',()=>{
 const h=setup();assert.ok(h.api,'renderer exists');const renderer=h.api.mount(h.svg,{});
 renderer.update(scene,positions(100),{animate:false});renderer.update({...scene,nodes:scene.nodes.slice(0,2),edges:[]},positions(500));
 assert.equal(find(h.svg,n=>n.getAttribute('data-scene-node')==='b').length,0);
 h.main.remove();h.tick(325);assert.equal(h.frames.size,0);
});
