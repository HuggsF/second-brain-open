(function(root){
'use strict';
function state(data){
 if(!data.observation)return 'Sem coleta';
 if(data.collection_failed)return 'Falha na coleta';
 if(data.stale)return 'Dados desatualizados';
 return data.observation.report.ok?'Saudável na janela observada':'Requer atenção';
}
async function get(path){
 const response=await fetch('/v1/'+path,{credentials:'same-origin',cache:'no-store'});
 if(!response.ok)throw new Error(response.status===401?'Sessão expirada. Gere um novo link local de conexão.':'BFF indisponível ou acesso negado.');
 const data=await response.json();
 if(data.schema_version!==1||data.space_id!=='kiosk')throw new Error('Contrato HTTP incompatível.');
 return data;
}
const adapter={get,state};root.BrainLive=adapter;
if(typeof module!=='undefined')module.exports=adapter;
})(typeof window==='undefined'?globalThis:window);
