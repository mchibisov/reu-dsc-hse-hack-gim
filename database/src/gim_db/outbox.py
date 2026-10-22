"""Durable PostgreSQL executor. Network handlers never hold SQL transactions."""
import asyncio
from contextlib import suppress
import importlib
import logging
import os
import sys

from .repository import Repository, create_pool, one, emit, all_rows

log = logging.getLogger('gim.tasks')
TOPICS = ('question.send', 'application.analyze', 'staff.notify', 'file.export', 'vk.incoming', 'vk.send')


class LeaseLostError(RuntimeError):
    pass


class SQLQueue:
    def __init__(self, pool, group_id=None, *, lease_seconds=60):
        if lease_seconds <= 0:
            raise ValueError('Lease must be positive')
        self.pool = pool
        self.group_id = group_id
        self.lease_seconds = lease_seconds

    async def claim(self, topics=None):
        topics = list(TOPICS if topics is None else topics)
        # Scope by persisted application/file first, payload only for gateway events.
        scope = '''(%s::text IS NULL OR COALESCE(r.group_id::text,fr.group_id::text,e.payload->>'group_id')=%s)'''
        joins = '''LEFT JOIN gim.applications a ON a.id=e.application_id
                   LEFT JOIN gim.users recipient ON recipient.id=a.user_id
                   LEFT JOIN gim.recruitments r ON r.id=a.recruitment_id
                   LEFT JOIN gim.files f ON f.id=e.file_id
                   LEFT JOIN gim.recruitments fr ON fr.id=f.recruitment_id'''
        group = None if self.group_id is None else str(self.group_id)
        async with self.pool.connection() as c, c.transaction():
            # A process dying on its final attempt must become terminal too.
            expired=await all_rows(c,f'''UPDATE gim.outbox_events SET failed_at=now(),lease_token=NULL,lease_until=NULL,
                last_error_code=COALESCE(last_error_code,'lease_expired') WHERE id IN (
                SELECT e.id FROM gim.outbox_events e {joins}
                WHERE e.completed_at IS NULL AND e.failed_at IS NULL AND e.attempts>=e.max_attempts
                AND (e.lease_until IS NULL OR e.lease_until<=now()) AND {scope}
                FOR UPDATE OF e SKIP LOCKED) RETURNING *''', (group, group))
            for event in expired:await _notify_failed_analysis(c,event)
            return await one(c, f'''WITH candidate AS (
                SELECT e.id FROM gim.outbox_events e {joins}
                WHERE e.completed_at IS NULL AND e.failed_at IS NULL AND e.attempts<e.max_attempts
                AND e.available_at<=now() AND (e.lease_until IS NULL OR e.lease_until<=now())
                AND e.topic=ANY(%s::text[]) AND {scope}
                AND (e.topic<>'vk.incoming' OR e.payload->>'serial_key' IS NULL OR NOT EXISTS (
                    SELECT 1 FROM gim.outbox_events older WHERE older.topic='vk.incoming'
                    AND older.payload->>'serial_key'=e.payload->>'serial_key'
                    AND older.payload->>'group_id'=e.payload->>'group_id'
                    AND older.vk_random_id<e.vk_random_id
                    AND older.completed_at IS NULL AND older.failed_at IS NULL))
                AND (e.topic NOT IN ('vk.send','question.send') OR NOT EXISTS (
                    SELECT 1 FROM gim.outbox_events older
                    LEFT JOIN gim.applications oa ON oa.id=older.application_id
                    LEFT JOIN gim.users ou ON ou.id=oa.user_id
                    LEFT JOIN gim.recruitments obr ON obr.id=oa.recruitment_id
                    WHERE older.topic IN ('vk.send','question.send')
                    AND COALESCE(older.payload->>'peer_id',ou.vk_id::text)
                        =COALESCE(e.payload->>'peer_id',recipient.vk_id::text)
                    AND COALESCE(obr.group_id::text,older.payload->>'group_id')
                        =COALESCE(r.group_id::text,e.payload->>'group_id')
                    AND older.vk_random_id<e.vk_random_id
                    AND older.completed_at IS NULL AND older.failed_at IS NULL))
                ORDER BY e.vk_random_id LIMIT 1 FOR UPDATE OF e SKIP LOCKED)
                UPDATE gim.outbox_events e SET lease_token=gen_random_uuid(),
                lease_until=now()+(%s * interval '1 second'),attempts=attempts+1
                FROM candidate WHERE e.id=candidate.id RETURNING e.*''',
                (topics, group, group, self.lease_seconds))

    async def renew(self, event_id, token):
        async with self.pool.connection() as c:
            row = await one(c, '''UPDATE gim.outbox_events SET lease_until=now()+(%s * interval '1 second')
                WHERE id=%s AND lease_token=%s AND lease_until>now()
                AND completed_at IS NULL AND failed_at IS NULL RETURNING id''',
                (self.lease_seconds, event_id, token))
            return row is not None

    async def finish(self, event_id, token, success, error_code=None):
        async with self.pool.connection() as c, c.transaction():
            event = await one(c, '''UPDATE gim.outbox_events SET
                completed_at=CASE WHEN %s THEN now() ELSE NULL END,
                failed_at=CASE WHEN NOT %s AND attempts>=max_attempts THEN now() ELSE NULL END,
                available_at=CASE WHEN %s THEN available_at ELSE now()+(
                    CASE WHEN topic IN ('vk.send','question.send','staff.notify') AND attempts<=2
                        AND %s IN ('ConnectTimeout','ConnectError') THEN 0.5
                        ELSE LEAST(60,attempts*5) END * interval '1 second') END,
                last_error_code=%s,lease_token=NULL,lease_until=NULL
                WHERE id=%s AND lease_token=%s AND lease_until>now()
                AND completed_at IS NULL AND failed_at IS NULL RETURNING *''',
                (success, success, success, error_code, error_code, event_id, token))
            if event and success and error_code is None and event['topic'] == 'question.send':
                await c.execute('UPDATE gim.dialog_questions SET asked_at=COALESCE(asked_at,now()) WHERE id=%s AND application_id=%s',
                                (event['payload']['question_id'], event['application_id']))
            if event and event['failed_at'] is not None:await _notify_failed_analysis(c,event)
            return event is not None


async def _notify_failed_analysis(c,event):
    if event['topic']!='application.analyze' or not event.get('application_id'):return
    recipients=await all_rows(c,'''SELECT s.id FROM gim.staff_members s JOIN gim.recruitments r ON r.group_id=s.group_id
      JOIN gim.applications a ON a.recruitment_id=r.id WHERE a.id=%s AND NOT a.archived AND s.active AND s.notify_new_applications''',(event['application_id'],))
    for recipient in recipients:
        await emit(c,event['application_id'],'staff.notify',f'analysis-unavailable:{event["id"]}:{recipient["id"]}',
                   {'kind':'analysis_unavailable'},staff_id=recipient['id'])


async def _handle(ctx, event):
    repo = ctx['repository']
    topic = event['topic']
    if topic == 'staff.notify' and not await repo.notification_allowed(event['recipient_staff_id'], event['application_id']):
        return 'recipient_revoked_or_unsubscribed'
    if topic == 'question.send':
        async with repo.pool.connection() as c:
            question = await one(c, '''SELECT q.*,u.vk_id,r.group_id,a.status AS application_status,
                a.current_question_id,
                (SELECT count(*) FROM gim.question_templates t WHERE t.recruitment_id=a.recruitment_id
                 AND t.kind='base' AND COALESCE(t.validation->>'retired','false')<>'true') AS base_total,
                (SELECT count(*) FROM gim.question_templates t JOIN gim.question_templates current ON current.id=q.template_id
                 WHERE t.recruitment_id=a.recruitment_id AND t.kind='base' AND t.position<=current.position
                 AND COALESCE(t.validation->>'retired','false')<>'true') AS base_position
                FROM gim.dialog_questions q
                JOIN gim.applications a ON a.id=q.application_id JOIN gim.users u ON u.id=a.user_id
                JOIN gim.recruitments r ON r.id=a.recruitment_id WHERE q.id=%s AND q.application_id=%s''',
                (event['payload']['question_id'], event['application_id']))
        if question is None:
            raise LookupError('Missing persisted question')
        if (question['status']!='active' or question['application_status']!='draft'
                or question['current_question_id']!=question['id']):
            return 'question_no_longer_active'
        event['question'] = question
    if topic == 'application.analyze':
        event['snapshot'] = await repo.evaluation_snapshot(event['application_id'], revision=event['payload']['revision'])
    handler = ctx['handlers'].get(topic)
    if handler is None:
        raise LookupError('Handler not configured')
    result = await handler(event)
    if topic == 'application.analyze':
        if result is None:
            return 'analysis_disabled'
        await repo.save_evaluation(event['application_id'], snapshot=event['snapshot'], request_key=str(event['id']),
                                   source_event_id=event['id'], source_lease_token=event['lease_token'], **result)
    if topic == 'file.export':
        async with repo.pool.connection() as c:
            file = await one(c, 'SELECT status FROM gim.files WHERE id=%s', (event['file_id'],))
        if not file or file['status'] != 'ready':
            raise ValueError('Export handler must finish file before acknowledgement')
    return None


async def _heartbeat(queue, event):
    while True:
        await asyncio.sleep(queue.lease_seconds / 3)
        if not await queue.renew(event['id'], event['lease_token']):
            raise LeaseLostError('Lease no longer owned')


async def _execute(ctx, queue, event):
    handler = asyncio.create_task(_handle(ctx, event))
    heartbeat = asyncio.create_task(_heartbeat(queue, event))
    try:
        try:
            async with asyncio.timeout(ctx.get('job_timeout', 180)):
                done, _ = await asyncio.wait((handler, heartbeat), return_when=asyncio.FIRST_COMPLETED)
                if heartbeat in done:
                    await heartbeat
                error_code = await handler
        finally:
            # Stop in-flight work before releasing its lease, including shutdown/timeout.
            for task in (handler, heartbeat):
                task.cancel()
            for task in (handler, heartbeat):
                with suppress(asyncio.CancelledError, Exception):
                    await task
        await queue.finish(event['id'], event['lease_token'], True, error_code)
    except asyncio.CancelledError:
        # If shutdown interrupts this receipt too, the durable lease still expires.
        with suppress(Exception):
            await asyncio.shield(queue.finish(event['id'], event['lease_token'], False, 'cancelled'))
        raise
    except Exception as exc:
        code = getattr(exc,'code',type(exc).__name__)
        await queue.finish(event['id'], event['lease_token'], False, code)
        log.warning('outbox_execution_failed event_id=%s code=%s', event['id'], code)


async def run_once(ctx, queue, limit=10, *, topics=None):
    """Process at most limit events, one claim at a time; return claimed count."""
    count = 0
    for _ in range(limit):
        event = await queue.claim(topics) if topics is not None else await queue.claim()
        if event is None:
            break
        count += 1
        await _execute(ctx, queue, event)
    return count


async def run_forever():
    module = importlib.import_module(os.environ['GIM_HANDLERS_MODULE'])
    group = os.environ.get('VK_GROUP_ID')
    async with create_pool(os.environ['DATABASE_WORKER_URL']) as pool:
        queue = SQLQueue(pool, int(group) if group else None)
        ctx = {'repository': Repository(pool), 'handlers': module.HANDLERS}
        while True:
            if not await run_once(ctx, queue):
                await asyncio.sleep(1)


async def send_staff_notification(repository, event, send_vk):
    """Recheck staff permissions immediately before send_vk(vk_id, group_id, random_id)."""
    async with repository.pool.connection() as c:
        recipient = await one(c, '''SELECT u.vk_id,s.group_id FROM gim.staff_members s JOIN gim.users u ON u.id=s.user_id
            JOIN gim.recruitments r ON r.group_id=s.group_id JOIN gim.applications a ON a.recruitment_id=r.id
            WHERE s.id=%s AND a.id=%s AND s.active AND s.notify_new_applications''',
            (event['recipient_staff_id'], event['application_id']))
    if recipient is None:
        return False
    await send_vk(recipient['vk_id'], recipient['group_id'], event['vk_random_id'])
    return True


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_forever())
