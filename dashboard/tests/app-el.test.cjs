'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
// The BFF serves the dashboard under CSP style-src 'self': a style attribute set with setAttribute is
// dropped by the browser, while CSSOM writes (node.style.cssText) are allowed.
function loadEl(){
 const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
 const match=source.match(/function el\(tag, attrs, \.\.\.children\) \{[\s\S]*?\r?\n\}\r?\n/);
 assert.ok(match,'el() not found in app.js');
 const attributes=[];
 const document={createElement:tag=>({tag,style:{cssText:''},attributes,setAttribute(k,v){attributes.push([k,v]);},append(){},addEventListener(){}}),createTextNode:text=>({text})};
 const context=vm.createContext({document,Node:class {}});
 vm.runInContext(match[0]+';globalThis.el=el;',context);
 return {el:context.el,attributes};
}
test('el applies style through CSSOM so a strict CSP does not drop it',()=>{
 const {el,attributes}=loadEl();
 const node=el('div',{style:'display:flex;gap:8px',title:'x'});
 assert.equal(node.style.cssText,'display:flex;gap:8px');
 assert.deepEqual(attributes.filter(([k])=>k==='style'),[]);
 assert.deepEqual(attributes,[['title','x']]);
});
