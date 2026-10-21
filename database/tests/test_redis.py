"""Optional genuine Redis/ARQ integration; never uses a production Redis URL."""
import os
import uuid
from arq import create_pool
from arq.connections import RedisSettings
from arq.worker import Worker
from test_database import DSN,env,complete_draft
import psycopg
import pytest


@pytest.mark.skipif(not os.getenv('TEST_REDIS_URL'),reason='set TEST_REDIS_URL to disposable Redis')
async def test_real_arq_retry_and_redis_loss(env):
    from gim_db.outbox import Publisher,dispatch
    bot,repo,staff,r,t,vk,sid=env
    a,q,ans=await complete_draft(env)
    redis=await create_pool(RedisSettings.from_dsn(os.environ['TEST_REDIS_URL']))
    # Dedicated namespace queue; FLUSHDB is never used.
    namespace='test:'+str(uuid.uuid4())
    real_enqueue=redis.enqueue_job
    class Queue:
        async def enqueue_job(self,*args,**kw):
            return await real_enqueue(*args,_queue_name=namespace,**kw)
    p=Publisher(repo.pool,republish_seconds=0)
    with psycopg.connect(DSN) as c:
        own=[str(x[0]) for x in c.execute('SELECT id FROM gim.outbox_events WHERE application_id=%s',(a['id'],))]
        # Keep this test focused on its question. Other durable jobs are safe in their own queue.
    await p.publish_pending(Queue(),limit=100000)
    # Simulated Redis loss: remove this test queue and own jobs, then prove PG restores them.
    await redis.delete(namespace,*['arq:job:gim:'+x for x in own])
    await p.publish_pending(Queue(),limit=100000)
    sent=[]
    async def sender(event):
        sent.append((event['question']['text'],event['vk_random_id']))
    worker=Worker([dispatch],redis_pool=redis,queue_name=namespace,burst=True,max_jobs=5,keep_result=0,
        ctx={'repository':repo,'handlers':{'question.send':sender}},handle_signals=False)
    try:
        await worker.async_run()
        assert any(x[0]=='Опишите опыт' for x in sent)
        with psycopg.connect(DSN) as c:
            assert c.execute('SELECT completed_at IS NOT NULL FROM gim.outbox_events WHERE id=%s',(own[0],)).fetchone()[0]
        # Re-executing completed event is a no-op even if Redis forgets it.
        before=len(sent)
        await dispatch({'repository':repo,'handlers':{'question.send':sender}},own[0])
        assert len(sent)==before
    finally:
        await redis.delete(namespace)
        await worker.close()
