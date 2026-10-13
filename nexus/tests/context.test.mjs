import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
let api=null;
try { api=await server.ssrLoadModule('/src/context.jsx').catch(()=>null); } finally {await server.close();}
test('provider fornece mesma façade aos dois consumidores SSR',()=>{assert.ok(api,'Context ainda ausente');let seen=[];function Consumer(){seen.push(api.useSimulationContext());return null;}renderToStaticMarkup(React.createElement(api.SimulationProvider,{now:()=>50},React.createElement(React.Fragment,null,React.createElement(Consumer),React.createElement(Consumer))));assert.equal(seen[0],seen[1]);assert.equal(seen[0].workspace.simulation.logs[0].at,50);assert.equal(typeof seen[0].actions.start,'function');});
test('driver único respeita velocidade/gate e limpa timer',()=>{assert.ok(api,'Context ainda ausente');let callback,period,cleared=0,actions=[];const stop=api.createTickDriver({simulation:{mode:'running',needsApproval:false},speed:2,missionId:3},a=>actions.push(a),{now:()=>99,setInterval(f,p){callback=f;period=p;return 7;},clearInterval(id){assert.equal(id,7);cleared++;}});assert.equal(period,1000);callback();assert.deepEqual(actions,[{type:'TICK',now:99,missionId:3}]);stop();assert.equal(cleared,1);callback();assert.equal(actions.length,1);api.createTickDriver({simulation:{mode:'paused'},speed:1,missionId:3},()=>assert.fail(),{setInterval(){assert.fail();}})();});
test('listener do SO entrega mudanças e desinscreve',()=>{assert.ok(api,'Context ainda ausente');let listener,removed=false,values=[];const media={matches:true,addEventListener(type,fn){assert.equal(type,'change');listener=fn;},removeEventListener(type,fn){assert.equal(fn,listener);removed=true;}};const stop=api.subscribeSystemMotion(v=>values.push(v),()=>media);listener({matches:false});stop();assert.deepEqual(values,[true,false]);assert.equal(removed,true);});
