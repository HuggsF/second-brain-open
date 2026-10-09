const test=require('node:test'),assert=require('node:assert/strict');
const {state}=require('../live-adapter.js');
test('live state never treats missing, stale or failed collection as healthy',()=>{
 assert.equal(state({}),'Sem coleta');
 const observation={report:{ok:true}};
 assert.equal(state({observation,stale:true}),'Dados desatualizados');
 assert.equal(state({observation,collection_failed:true}),'Falha na coleta');
 assert.equal(state({observation}),'Saudável na janela observada');
 assert.equal(state({observation:{report:{ok:false}}}),'Requer atenção');
});
