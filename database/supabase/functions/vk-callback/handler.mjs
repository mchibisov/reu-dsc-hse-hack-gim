// Authenticated ingress only. Python remains the sole durable event consumer.
const MAX_BODY=131072;
const reply=(status,text)=>new Response(text,{status,headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'}});
export function createHandler(config,forward=fetch){
 if(!Number.isSafeInteger(config.groupId)||config.groupId<=0||!/^[a-f0-9]{64}$/.test(config.secretSha256)||
    !/^https:\/\/[a-z0-9-]+\.vercel\.app\/callback$/.test(config.upstream))throw Error('Invalid ingress configuration');
 return async function(request){
  if(request.method!=='POST')return reply(405,'method not allowed');
  if(Number(request.headers.get('content-length')||0)>MAX_BODY)return reply(413,'invalid body size');
  let body,event;
  try{
   const reader=request.body?.getReader();if(!reader)return reply(400,'invalid request');
   const chunks=[];let size=0;
   try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;
     if(size>MAX_BODY){await reader.cancel();return reply(413,'invalid body size');}chunks.push(value);}}
   finally{reader.releaseLock();}
   const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
   body=new TextDecoder().decode(bytes);event=JSON.parse(body);
  }catch{return reply(400,'invalid request');}
  if(!event||typeof event!=='object'||event.group_id!==config.groupId||typeof event.secret!=='string'||event.secret.length>256)return reply(403,'forbidden');
  const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(event.secret)));
  const hash=Array.from(digest,b=>b.toString(16).padStart(2,'0')).join('');
  let diff=0;for(let i=0;i<hash.length;i++)diff|=hash.charCodeAt(i)^config.secretSha256.charCodeAt(i);
  if(diff)return reply(403,'forbidden');
  if(event.type==='confirmation')return typeof config.confirmation==='string'&&config.confirmation?reply(200,config.confirmation):reply(503,'not configured');
  try{
   const response=await forward(config.upstream,{method:'POST',body,headers:{'Content-Type':'application/json'},
     redirect:'error',signal:AbortSignal.timeout(2500)});
   const text=await response.text();
   // Never acknowledge an event until Python has committed it to PostgreSQL.
   if(response.status!==200||(event.type!=='confirmation'&&text!=='ok'))return reply(503,'temporarily unavailable');
   return reply(200,text);
  }catch{return reply(503,'temporarily unavailable');}
 };
}
