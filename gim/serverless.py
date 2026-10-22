"""Optional bounded VK Callback adapter; existing SQL queue remains authoritative."""
import asyncio
import hashlib
import hmac
import os
import time
from contextlib import AsyncExitStack,suppress
from uuid import uuid4
from gim.shared_config import SharedSettings
from gim.shared_gateway import enqueue_events
from gim.shared_service import SharedService
from gim.shared_storage import MAX_SIZE
from gim.vk import VK
from gim_db.repository import Repository,create_pool,one
from gim_db.outbox import SQLQueue,run_once

DELIVERY_TOPICS = ('vk.send', 'question.send', 'staff.notify', 'file.export')
FAST_TOPICS = (*DELIVERY_TOPICS, 'vk.incoming')


def callback_allowed(event,settings):
 secret=os.environ.get('VK_CALLBACK_SECRET','')
 return bool(secret) and isinstance(event,dict) and event.get('group_id')==settings.group_id and isinstance(event.get('secret'),str) and hmac.compare_digest(event['secret'],secret)


class PostgresPrivateStorage:
 """Small immutable export objects; never served by a public HTTP route."""
 def __init__(self,pool):self.pool=pool
 async def upload(self,metadata,data):
  if metadata['status']!='pending' or len(data)>MAX_SIZE:raise ValueError('Immutable or oversized object')
  async with self.pool.connection() as c,c.transaction():
   await c.execute('INSERT INTO gim.file_contents(file_id,body) VALUES(%s,%s) ON CONFLICT DO NOTHING',(metadata['id'],data))
   old=await one(c,'SELECT body FROM gim.file_contents WHERE file_id=%s',(metadata['id'],))
   if old is None or bytes(old['body'])!=data:raise ValueError('Immutable object conflict')
 async def read(self,metadata):
  async with self.pool.connection() as c:row=await one(c,'SELECT body FROM gim.file_contents WHERE file_id=%s',(metadata['id'],))
  if row is None:raise FileNotFoundError('Private object unavailable')
  data=bytes(row['body'])
  if len(data)>MAX_SIZE or metadata.get('sha256') and hashlib.sha256(data).hexdigest()!=metadata['sha256']:raise ValueError('File integrity check failed')
  if metadata.get('size_bytes') is not None and metadata['size_bytes']!=len(data):raise ValueError('File size check failed')
  return data
 async def close(self):pass


async def receive(event,settings):
 if not callback_allowed(event,settings):return 403,'forbidden'
 if event.get('type')=='confirmation':return 200,os.environ.get('VK_CONFIRMATION','')
 if event.get('type')!='message_new':return 200,'ok'
 async with create_pool(settings.database_bot_url,max_size=1) as pool:
  async with pool.connection() as c:
   async with c.transaction():
    await enqueue_events(c,[{k:v for k,v in event.items() if k!='secret'}],settings.group_id,settings.excel_access_code)
   # Wake AFTER receipt COMMIT: if a previous owner exits concurrently,
   # either its final scan sees this receipt or this wake sees its released lease.
   # Waking inside the receipt transaction leaves a gap recovered only by Cron.
   await c.execute('SELECT gim.wake_worker(%s)',(settings.group_id,))
 return 200,'ok'


async def drain(settings,*,budget=245):
 """One owner, four existing queue handlers; no detached background tasks."""
 token=uuid4()
 async with AsyncExitStack() as stack:
  pools=[]
  for dsn in (settings.database_bot_url,settings.database_worker_url,settings.database_staff_url):
   pool=await stack.enter_async_context(create_pool(dsn,max_size=2));pools.append(pool)
  async with pools[1].connection() as c:
   lease=await one(c,"""INSERT INTO gim.runtime_leases(group_id,token,expires_at) VALUES(%s,%s,now()+interval '270 seconds')
    ON CONFLICT(group_id) DO UPDATE SET token=EXCLUDED.token,expires_at=EXCLUDED.expires_at
    WHERE gim.runtime_leases.expires_at<=now() RETURNING token""",(settings.group_id,token))
  if not lease:return 'busy'
  try:
   vk=VK(settings);stack.push_async_callback(vk.close)
   service=SharedService(*(Repository(p) for p in pools),vk,settings,PostgresPrivateStorage(pools[1]))
   end=time.monotonic()+budget
   queue=SQLQueue(pools[1],settings.group_id)
   ctx={'repository':service.worker_repo,'handlers':service.handlers}
   async def lane(index):
    while time.monotonic()<end:
     remaining=end-time.monotonic()
     # Reserve delivery and dialog capacity even while analyses occupy the
     # other lanes. Only new analysis needs the full 185-second runway.
     eligible = None if remaining >= 185 else list(FAST_TOPICS)
     topics = DELIVERY_TOPICS if index == 0 else ('vk.incoming',) if index == 1 else eligible
     if not await run_once(ctx,queue,limit=1,topics=topics):
      async with pools[1].connection() as c:
       # Temporary emptiness is not completion: an in-flight handler can
       # receive new callbacks or enqueue replies. Check invocation-wide
       # work, not just this lane, including live leases from sibling lanes.
       pending=await one(c,"""SELECT EXISTS(
        SELECT FROM gim.outbox_events e
        LEFT JOIN gim.applications a ON a.id=e.application_id
        LEFT JOIN gim.recruitments r ON r.id=a.recruitment_id
        LEFT JOIN gim.files f ON f.id=e.file_id
        LEFT JOIN gim.recruitments fr ON fr.id=f.recruitment_id
        WHERE COALESCE(r.group_id,fr.group_id,(e.payload->>'group_id')::bigint)=%s
        AND e.completed_at IS NULL AND e.failed_at IS NULL
        AND (e.lease_until>now() OR (
         e.available_at<=now()+interval '15 seconds' AND (e.lease_until IS NULL OR e.lease_until<=now())
         AND (%s::text[] IS NULL OR e.topic=ANY(%s::text[]))))) pending""",
        (settings.group_id,eligible,eligible))
      if not pending['pending']:return
      await asyncio.sleep(.4)
   async with asyncio.timeout(budget+5):
    async with asyncio.TaskGroup() as tasks:
     for i in range(4):
      tasks.create_task(lane(i))
   return 'drained'
  finally:
   async with pools[1].connection() as c:
    await c.execute('UPDATE gim.runtime_leases SET expires_at=now() WHERE group_id=%s AND token=%s',(settings.group_id,token))
   # Close the final-empty-check/release race and hand off remaining analysis
   # to a fresh time budget. Cron still recovers crashes and delayed retries.
   with suppress(Exception):
    async with pools[0].connection() as c:await c.execute('SELECT gim.wake_worker(%s)',(settings.group_id,))
