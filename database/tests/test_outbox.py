import uuid
import psycopg
import pytest
from test_database import DSN, env, complete_draft


async def test_outbox_republishes_until_business_completion(env):
    from gim_db.outbox import Publisher
    bot,worker,*_=env
    a,q,answer=await complete_draft(env)
    await bot.submit(a['id'])
    # Redis boundary fake: the recovery invariant itself is stored in real PostgreSQL.
    class RedisBoundary:
        def __init__(self): self.jobs={}
        async def enqueue_job(self,name,event_id,**kw):
            assert name=='dispatch'
            old=self.jobs.get(kw['_job_id']); self.jobs[kw['_job_id']]=event_id
            return None if old else object()
    redis=RedisBoundary(); p=Publisher(worker.pool,republish_seconds=0)
    await p.publish_pending(redis,limit=100000)
    ids=set(redis.jobs)
    with psycopg.connect(DSN) as c:
        own={str(x[0]) for x in c.execute('SELECT id FROM gim.outbox_events WHERE application_id=%s',(a['id'],)).fetchall()}
    assert {f'gim:{x}' for x in own} <= ids
    redis.jobs.clear()  # Complete Redis loss, no PG change.
    await p.publish_pending(redis,limit=100000)
    assert set(redis.jobs)==ids
    with psycopg.connect(DSN) as c:
        c.execute('UPDATE gim.outbox_events SET completed_at=now() WHERE application_id=%s',(a['id'],))
    redis.jobs.clear(); await p.publish_pending(redis,limit=100000)
    assert not own.intersection(redis.jobs.values())
    with psycopg.connect(DSN) as c:
        assert c.execute('SELECT min(publish_attempts) FROM gim.outbox_events WHERE application_id=%s',(a['id'],)).fetchone()[0]>=2

async def test_notification_checks_revocation_at_send_boundary(env):
    from gim_db.outbox import send_staff_notification
    bot,worker,staff,r,t,vk,sid=env
    a,q,ans=await complete_draft(env)
    calls=[]
    async def send(*args):calls.append(args)
    event={'recipient_staff_id':sid,'application_id':a['id'],'vk_random_id':123}
    assert await send_staff_notification(worker,event,send)
    with psycopg.connect(DSN) as c:c.execute('UPDATE gim.staff_members SET active=false,revoked_at=now() WHERE id=%s',(sid,))
    assert not await send_staff_notification(worker,event,send)
    assert len(calls)==1
