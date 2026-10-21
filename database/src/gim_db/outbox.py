"""ARQ is the only executor. PostgreSQL stores intentions and completion receipts."""
import asyncio
import importlib
import logging
import os
from arq import Retry, create_pool as create_redis_pool
from arq.connections import RedisSettings
from .repository import Repository, create_pool, one, all_rows

log=logging.getLogger('gim.tasks')


class Publisher:
    def __init__(self,pool,*,republish_seconds=90):
        self.pool=pool
        self.republish_seconds=republish_seconds

    async def publish_pending(self,redis,*,limit=100):
        count=0
        async with self.pool.connection() as c, c.transaction():
            rows=await all_rows(c,'''SELECT id FROM gim.outbox_events WHERE completed_at IS NULL AND available_at<=now()
                AND (last_published_at IS NULL OR last_published_at<=now()-(%s * interval '1 second'))
                ORDER BY available_at,id LIMIT %s FOR UPDATE SKIP LOCKED''',(self.republish_seconds,limit))
            for row in rows:
                event_id=str(row['id'])
                # Only an opaque identifier enters Redis. A crash before PG commit is a safe retry.
                try:
                    await asyncio.wait_for(redis.enqueue_job('dispatch',event_id,_job_id=f'gim:{event_id}'),timeout=3)
                except Exception:
                    await c.execute("UPDATE gim.outbox_events SET publish_attempts=publish_attempts+1,last_error_code='redis_unavailable',available_at=now()+interval '10 seconds' WHERE id=%s",(row['id'],))
                    log.warning('outbox_publish_failed event_id=%s code=redis_unavailable',event_id)
                    continue
                await c.execute('UPDATE gim.outbox_events SET last_published_at=now(),publish_attempts=publish_attempts+1,last_error_code=NULL WHERE id=%s',(row['id'],))
                count+=1
        return count


async def dispatch(ctx,event_id):
    repo=ctx['repository']
    async with repo.pool.connection() as c:
        event=await one(c,'SELECT * FROM gim.outbox_events WHERE id=%s',(event_id,))
    if not event or event['completed_at'] is not None: return
    try:
        if event['topic']=='staff.notify' and not await repo.notification_allowed(event['recipient_staff_id'],event['application_id']):
            async with repo.pool.connection() as c:
                await c.execute("UPDATE gim.outbox_events SET completed_at=now(),last_error_code='recipient_revoked_or_unsubscribed' WHERE id=%s",(event_id,))
            return
        if event['topic']=='question.send':
            async with repo.pool.connection() as c:
                q=await one(c,'''SELECT q.*,u.vk_id,r.group_id FROM gim.dialog_questions q JOIN gim.applications a ON a.id=q.application_id
                    JOIN gim.users u ON u.id=a.user_id JOIN gim.recruitments r ON r.id=a.recruitment_id
                    WHERE q.id=%s AND q.application_id=%s''',(event['payload']['question_id'],event['application_id']))
            if not q: raise ValueError('Missing persisted question')
            event['question']=q
        if event['topic']=='application.analyze':
            event['snapshot']=await repo.evaluation_snapshot(event['application_id'],revision=event['payload']['revision'])
        handlers=ctx['handlers']
        handler=handlers.get(event['topic'])
        if handler is None: raise LookupError('Handler not configured')
        # LLM, file generation, VK calls are outside database transactions.
        # External sends must use event.vk_random_id and recheck permissions at this boundary.
        result=await handler(event)
        if event['topic']=='application.analyze':
            await repo.save_evaluation(event['application_id'],snapshot=event['snapshot'],
                request_key=str(event['id']),source_event_id=event['id'],**result)
        else:
            async with repo.pool.connection() as c, c.transaction():
                if event['topic']=='question.send':
                    await c.execute('UPDATE gim.dialog_questions SET asked_at=COALESCE(asked_at,now()) WHERE id=%s',(event['question']['id'],))
                if event['topic']=='file.export':
                    f=await one(c,'SELECT status FROM gim.files WHERE id=%s',(event['file_id'],))
                    if not f or f['status']!='ready': raise ValueError('Export handler must persist ready file before acknowledgement')
                await c.execute('UPDATE gim.outbox_events SET completed_at=now(),last_error_code=NULL WHERE id=%s',(event_id,))
    except Exception as exc:
        # Never log exception text/traceback: an upstream error may contain personal data/secrets.
        code=type(exc).__name__
        async with repo.pool.connection() as c:
            await c.execute('UPDATE gim.outbox_events SET last_error_code=%s WHERE id=%s',(code,event_id))
        log.warning('outbox_execution_failed event_id=%s code=%s',event_id,code)
        raise Retry(defer=min(60,ctx.get('job_try',1)*5)) from None


async def startup(ctx):
    pool=create_pool(os.environ['DATABASE_WORKER_URL'])
    await pool.open(wait=True)
    ctx['repository']=Repository(pool)
    module=importlib.import_module(os.environ['GIM_HANDLERS_MODULE'])
    ctx['handlers']=module.HANDLERS


async def shutdown(ctx):
    await ctx['repository'].pool.close()


class WorkerSettings:
    functions=[dispatch]
    on_startup=startup
    on_shutdown=shutdown
    redis_settings=RedisSettings.from_dsn(os.environ.get('REDIS_URL','redis://localhost:6379/0'))
    max_jobs=10
    max_tries=5
    job_timeout=180
    keep_result=0
    # ARQ logs args (opaque event IDs only); Retry prevents upstream exception content from being logged.
    log_results=False


async def publish_forever():
    async with create_pool(os.environ['DATABASE_WORKER_URL'],max_size=2) as pool:
        redis=await create_redis_pool(RedisSettings.from_dsn(os.environ['REDIS_URL']))
        try:
            while True:
                await Publisher(pool).publish_pending(redis)
                await asyncio.sleep(2)
        finally:
            await redis.aclose()




async def send_staff_notification(repository,event,send_vk):
    """Use inside staff.notify handler immediately before VK messages.send.

    send_vk(recipient_vk, group_id, random_id) performs the actual network call.
    Revocation cannot cancel an HTTP request already in flight.
    """
    async with repository.pool.connection() as c:
        recipient=await one(c,'''SELECT u.vk_id,s.group_id FROM gim.staff_members s JOIN gim.users u ON u.id=s.user_id
            JOIN gim.recruitments r ON r.group_id=s.group_id JOIN gim.applications a ON a.recruitment_id=r.id
            WHERE s.id=%s AND a.id=%s AND s.active AND s.notify_new_applications''',
            (event['recipient_staff_id'],event['application_id']))
    if recipient is None:return False
    await send_vk(recipient['vk_id'],recipient['group_id'],event['vk_random_id'])
    return True


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(publish_forever())
