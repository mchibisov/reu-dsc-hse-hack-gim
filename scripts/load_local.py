"""50 synthetic users through private SQL queue. No external API or production DSN."""
import asyncio,json,os,re,time,uuid
from types import SimpleNamespace
from datetime import date
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from gim_db.repository import Repository,emit,one
from gim_db.outbox import SQLQueue,run_once
from gim.shared_service import SharedService
from psycopg.conninfo import conninfo_to_dict
DSN=os.environ.get('TEST_DATABASE_URL','')
async def main():
 if not DSN or conninfo_to_dict(DSN).get('host') not in {'127.0.0.1','localhost','::1'}:
  raise ValueError('Нужна отдельная локальная TEST_DATABASE_URL, не рабочая БД')
 group=uuid.uuid4().int%1000000000+1000000000
 async with await psycopg.AsyncConnection.connect(DSN,autocommit=True,row_factory=dict_row) as c:
  r=await one(c,"INSERT INTO gim.recruitments(group_id,title,questionnaire_version,rubric_version,rubric,followup_policy) VALUES(%s,'Synthetic 50 users','test','test',%s,%s) RETURNING id",(group,Jsonb({'criteria':[{'code':'synthetic','max_points':3}]}),Jsonb({'max_followups':0})))
  for i,slot in enumerate(['consent','birth_date','directions'],1):await c.execute("INSERT INTO gim.question_templates(recruitment_id,code,kind,text,position,required,target_slot) VALUES(%s,%s,'base',%s,%s,true,%s)",(r['id'],slot,slot,i,slot))
  await c.execute("UPDATE gim.recruitments SET status='active' WHERE id=%s",(r['id'],))
 pools=[]
 for role in ['gim_bot','gim_worker','gim_staff']:
  p=AsyncConnectionPool(DSN,min_size=1,max_size=8,open=False,kwargs={'autocommit':True,'row_factory':dict_row,'options':'-c role='+role,'prepare_threshold':None});await p.open(wait=True);pools.append(p)
 bot,worker,staff=[Repository(p) for p in pools];sent={};received={};latencies=[]
 class VK:
  async def send(self,actor,text,*args,**kw):
   sent.setdefault(actor,asyncio.Queue()).put_nowait(text)
   if actor in received:latencies.append(time.monotonic()-received.pop(actor))
 settings=SimpleNamespace(group_id=group,recruitment_id=r['id'],max_followups=0,llm_api_key='',llm_model='',max_answer_length=2000,consent_version='test-only')
 service=SharedService(bot,worker,staff,VK(),settings,None)
 # Analysis intentionally disabled; LLM cost/rate limits are a separate test.
 async def analysis(event):return None
 service.handlers['application.analyze']=analysis
 ctx={'repository':worker,'handlers':service.handlers};stop=False
 async def loop():
  q=SQLQueue(pools[1],group_id=group)
  while not stop:
   if not await run_once(ctx,q,limit=1):await asyncio.sleep(.01)
 async def enqueue(actor,text):
  uid=str(uuid.uuid4());event={'type':'message_new','group_id':group,'event_id':uid,'object':{'message':{'from_id':actor,'peer_id':actor,'text':text}}}
  received[actor]=time.monotonic()
  async with pools[1].connection() as c:await emit(c,None,'vk.incoming','load:'+uid,{'event':event,'group_id':group,'serial_key':f'{group}:{actor}'})
 async def candidate(i):
  actor=group*100+i;sent[actor]=asyncio.Queue();await enqueue(actor,'/start')
  for answer in ['Согласен','01.01.2000','Медиа']:
   while True:
    message=await asyncio.wait_for(sent[actor].get(),30)
    if re.match(r'^Основная анкета · \d+ из \d+\n',message):break
   await enqueue(actor,answer)
  while True:
   message=await asyncio.wait_for(sent[actor].get(),30)
   if 'Анкета получена' in message:break
 tasks=[asyncio.create_task(loop()) for _ in range(4)];started=time.monotonic()
 try:
  await asyncio.wait_for(asyncio.gather(*(candidate(i) for i in range(50))),60)
  async with pools[1].connection() as c:
   result=await one(c,"SELECT count(*) FILTER(WHERE status='submitted') submitted,count(*) total FROM gim.applications WHERE recruitment_id=%s",(r['id'],))
  times=sorted(latencies);result.update(seconds=round(time.monotonic()-started,3),users=50,workers=4,reply_p50=times[len(times)//2],reply_p95=times[int(len(times)*.95)],scope='Local PostgreSQL queue; synthetic VK transport; no LLM or real VK network')
  print(json.dumps(result));return result
 finally:
  stop=True
  await asyncio.gather(*tasks)
  for p in pools:await p.close()
if __name__=='__main__':
 if os.name=='nt':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
 asyncio.run(main())
