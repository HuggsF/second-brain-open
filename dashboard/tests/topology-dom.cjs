'use strict';
class Element {
 constructor(tagName, ownerDocument, text='') { this.tagName=tagName;this.ownerDocument=ownerDocument;this.parentNode=null;this.children=[];this.attributes={};this.listeners={};this.text=String(text); }
 set textContent(value) { this.replaceChildren();this.text=String(value); }
 get textContent() { return this.text+this.children.map(child=>child.textContent).join(''); }
 set className(value) { this.setAttribute('class',value); }
 get className() { return this.getAttribute('class')||''; }
 get open() { return this.getAttribute('open')!==null; }
 set open(value) { if(value)this.setAttribute('open','');else delete this.attributes.open; }
 contains(other) { return this===other||this.children.some(child=>child.contains(other)); }
 matches(selector) { if(selector.startsWith('.'))return this.className.split(' ').includes(selector.slice(1));if(selector.startsWith('[')){const fields=[...selector.matchAll(/\[([^=\]]+)(?:="([^"]*)")?\]/g)];return fields.length>0&&fields.every(([,key,value])=>value===undefined?this.getAttribute(key)!==null:this.getAttribute(key)===value);}return this.tagName===selector; }
 querySelector(selector) { return find(this,item=>item.matches(selector))[0]||null; }
 get isConnected() { return this===this.ownerDocument.body||!!this.parentNode?.isConnected; }
 setAttribute(key,value) { this.attributes[key]=String(value); }
 getAttribute(key) { return this.attributes[key]??null; }
 addEventListener(type,handler) { (this.listeners[type]??=[]).push(handler); }
 append(...children) { for (let child of children.flat(Infinity)) { if(child==null||child===false)continue;if(!(child instanceof Element))child=this.ownerDocument.createTextNode(child);if(child.parentNode)child.remove();child.parentNode=this;this.children.push(child); } }
 appendChild(child) { this.append(child);return child; }
 replaceChildren(...children) { for(const child of this.children)child.parentNode=null;this.children=[];this.text='';this.append(...children); }
 remove() { if(!this.parentNode)return;this.parentNode.children=this.parentNode.children.filter(child=>child!==this);this.parentNode=null; }
 focus() { this.ownerDocument.activeElement=this; }
 click() { this.dispatch('click'); }
 dispatch(type,properties={}) { const event={target:this,key:'',defaultPrevented:false,preventDefault(){this.defaultPrevented=true;},...properties};for(const listener of this.listeners[type]||[])listener(event);return event; }
 press(key) { const event=this.dispatch('keydown',{key});if(!event.defaultPrevented&&this.tagName==='button'&&(key==='Enter'||key===' '))this.click(); }
 set innerHTML(_) { throw new Error('Unsafe HTML assignment'); }
}
function walk(node) { return [node,...node.children.flatMap(walk)]; }
function find(node,predicate) { return walk(node).filter(typeof predicate==='string'?item=>item.tagName===predicate:predicate); }
function dom() {
 const document={createElement:tag=>new Element(tag,document),createTextNode:text=>new Element('#text',document,text),activeElement:null,querySelector:()=>null};
 document.body=document.createElement('body');
 const el=(tag,attrs={},...children)=>{const node=document.createElement(tag);for(const [key,value]of Object.entries(attrs||{})){if(value==null||value===false)continue;if(key.startsWith('on')&&typeof value==='function')node.addEventListener(key.slice(2),value);else node.setAttribute(key,value===true?'':value);}node.append(...children);return node;};
 const U={el,button:(text,action,cls='')=>el('button',{type:'button',class:cls,onclick:action},text),badge:(text,cls='')=>el('span',{class:'pill '+cls},text),head:(eyebrow,title,description)=>el('header',{},el('span',{},eyebrow),el('h1',{},title),el('p',{},description))};
 const main=el('main');document.body.append(main);
 return {document,U,main};
}
module.exports={dom,find,walk};
