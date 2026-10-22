import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHandler} from '../database/supabase/functions/vk-callback/handler.mjs';
const secret='synthetic-test-only-secret';
const hash=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(secret))).toString('hex');
const config={groupId:17,secretSha256:hash,upstream:'https://example.vercel.app/callback',confirmation:'synthetic-confirmation'};
const event={type:'message_new',group_id:17,secret,object:{message:{text:'synthetic'}}};
const req=(body=event)=>new Request('https://edge.test/',{method:'POST',body:JSON.stringify(body)});
test('authenticated event acknowledged only after durable upstream acceptance',async()=>{
 let called=false;
 const h=createHandler(config,async(url,options)=>{called=true;assert.equal(url,config.upstream);assert.deepEqual(JSON.parse(options.body),event);return new Response('ok');});
 assert.equal(await (await h(req())).text(),'ok');assert.ok(called);
});
test('invalid secret or group never reaches upstream',async()=>{
 const h=createHandler(config,()=>{throw Error('must not forward');});
 assert.equal((await h(req({...event,secret:'wrong'}))).status,403);
 assert.equal((await h(req({...event,group_id:18}))).status,403);
});
test('upstream errors and wrong acknowledgment stay retryable',async()=>{
 for(const response of [new Response('bad',{status:503}),new Response('not ok')]){
  assert.equal((await createHandler(config,async()=>response)(req())).status,503);
 }
 assert.equal((await createHandler(config,async()=>{throw Error('timeout');})(req())).status,503);
});
test('oversized or invalid input rejected before forwarding',async()=>{
 const h=createHandler(config,()=>{throw Error('must not forward');});
 assert.equal((await h(req({...event,padding:'x'.repeat(131073)}))).status,413);
 assert.equal((await h(new Request('https://edge.test/',{method:'POST',body:'not json'}))).status,400);
 assert.equal((await h(new Request('https://edge.test/'))).status,405);
});
test('confirmation is authenticated and passed through',async()=>{
 const r=await createHandler(config,async()=>{throw Error('confirmation must not depend on upstream');})(req({...event,type:'confirmation'}));
 assert.equal(await r.text(),'synthetic-confirmation');
});
