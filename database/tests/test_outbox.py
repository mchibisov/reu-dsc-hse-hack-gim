"""Real SQL lease tests, only against explicit disposable TEST_DATABASE_URL."""
import asyncio
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from test_database import DSN, env, complete_draft

from gim_db.outbox import SQLQueue, run_once, send_staff_notification


def enqueue(group, serial='candidate', topic='vk.incoming'):
    with psycopg.connect(DSN, row_factory=dict_row) as c:
        return c.execute('''INSERT INTO gim.outbox_events(topic,payload,dedupe_key)
            VALUES(%s,%s,%s) RETURNING *''',
            (topic, Jsonb({'group_id': group, 'serial_key': serial}), str(uuid.uuid4()))).fetchone()


async def test_claim_is_exclusive_and_serial_fifo(env):
    _, repo, _, recruitment, *_ = env
    group = recruitment['group_id']
    first, second = enqueue(group), enqueue(group)
    queue = SQLQueue(repo.pool, group)
    claims = await asyncio.gather(queue.claim(), queue.claim())
    assert sum(event is not None for event in claims) == 1
    event = next(event for event in claims if event)
    assert event['id'] == first['id']
    assert await queue.renew(event['id'], event['lease_token'])
    assert await queue.finish(event['id'], event['lease_token'], True)
    assert (await queue.claim())['id'] == second['id']


async def test_expired_lease_recovers_with_fencing(env):
    _, repo, _, recruitment, *_ = env
    row = enqueue(recruitment['group_id'])
    queue = SQLQueue(repo.pool, recruitment['group_id'])
    old = await queue.claim()
    with psycopg.connect(DSN) as c:
        c.execute("UPDATE gim.outbox_events SET lease_until=now()-interval '1 second' WHERE id=%s", (row['id'],))
    new = await queue.claim()
    assert new['id'] == old['id'] and new['lease_token'] != old['lease_token']
    assert new['attempts'] == 2
    assert not await queue.finish(old['id'], old['lease_token'], True)
    assert not await queue.renew(old['id'], old['lease_token'])
    assert await queue.finish(new['id'], new['lease_token'], True)
    assert await queue.claim() is None


async def test_serial_retry_blocks_next_message_but_not_another_candidate(env):
    _, repo, _, recruitment, *_ = env
    group = recruitment['group_id']
    first, second = enqueue(group), enqueue(group)
    other = enqueue(group, 'another-candidate')
    queue = SQLQueue(repo.pool, group)
    event = await queue.claim()
    assert event['id'] == first['id']
    assert await queue.finish(event['id'], event['lease_token'], False, 'synthetic')
    assert (await queue.claim())['id'] == other['id']
    assert await queue.claim() is None
    with psycopg.connect(DSN) as c:
        c.execute('UPDATE gim.outbox_events SET available_at=now() WHERE id=%s', (first['id'],))
    retry = await queue.claim()
    assert retry['id'] == first['id']
    assert await queue.finish(retry['id'], retry['lease_token'], True)
    assert (await queue.claim())['id'] == second['id']


async def test_failure_and_crash_have_finite_attempts(env):
    _, repo, _, recruitment, *_ = env
    row = enqueue(recruitment['group_id'])
    queue = SQLQueue(repo.pool, recruitment['group_id'])
    for attempt in range(1, 6):
        event = await queue.claim()
        assert event['attempts'] == attempt
        assert await queue.finish(event['id'], event['lease_token'], False, 'synthetic')
        with psycopg.connect(DSN) as c:
            c.execute("UPDATE gim.outbox_events SET available_at=now() WHERE id=%s", (row['id'],))
    assert await queue.claim() is None
    crashed = enqueue(recruitment['group_id'], 'other')
    with psycopg.connect(DSN) as c:
        c.execute("UPDATE gim.outbox_events SET attempts=5,lease_token=gen_random_uuid(),lease_until=now()-interval '1 second' WHERE id=%s", (crashed['id'],))
    assert await queue.claim() is None
    with psycopg.connect(DSN) as c:
        assert c.execute('SELECT failed_at IS NOT NULL FROM gim.outbox_events WHERE id=%s', (crashed['id'],)).fetchone()[0]


async def test_worker_group_never_claims_another_community(env):
    _, repo, _, recruitment, *_ = env
    group = recruitment['group_id']
    enqueue(group + 10000000000)
    own = enqueue(group)
    queue = SQLQueue(repo.pool, group)
    assert (await queue.claim())['id'] == own['id']
    assert await queue.claim() is None


async def test_outgoing_retry_preserves_order_between_reply_and_question(env):
    bot,repo,_,r,t,*_=env
    app=await bot.start_application(r['id'],r['group_id'])
    with psycopg.connect(DSN,row_factory=dict_row) as c:
        first=c.execute('''INSERT INTO gim.outbox_events(application_id,topic,payload,dedupe_key)
            VALUES(%s,'vk.send',%s,%s) RETURNING *''',
            (app['id'],Jsonb({'group_id':r['group_id'],'peer_id':r['group_id'],'text':'Сначала это'}),str(uuid.uuid4()))).fetchone()
    await bot.prepare_question(app['id'],request_key='ordered',expected_revision=0,template_id=t['id'])
    queue=SQLQueue(repo.pool,r['group_id'])
    event=await queue.claim(['vk.send','question.send'])
    assert event['id']==first['id']
    await queue.finish(event['id'],event['lease_token'],False,'synthetic_timeout')
    assert await queue.claim(['vk.send','question.send']) is None
    with psycopg.connect(DSN) as c:
        c.execute('UPDATE gim.outbox_events SET available_at=now() WHERE id=%s',(first['id'],))
    event=await queue.claim(['vk.send','question.send'])
    assert event['id']==first['id']
    await queue.finish(event['id'],event['lease_token'],True)
    assert (await queue.claim(['vk.send','question.send']))['topic']=='question.send'


async def test_question_dispatch_loads_exact_saved_question_and_marks_asked(env):
    bot, repo, _, recruitment, template, *_ = env
    app = await bot.start_application(recruitment['id'], recruitment['group_id'])
    question = await bot.prepare_question(app['id'], request_key='sql-question', expected_revision=0, template_id=template['id'])
    sent = []
    async def send(event):
        sent.append((event['question']['id'], event['question']['text'], event['vk_random_id']))
    assert await run_once({'repository': repo, 'handlers': {'question.send': send}}, SQLQueue(repo.pool, recruitment['group_id'])) == 1
    assert sent[0][:2] == (question['id'], 'Опишите опыт')
    with psycopg.connect(DSN) as c:
        assert c.execute('SELECT asked_at IS NOT NULL FROM gim.dialog_questions WHERE id=%s', (question['id'],)).fetchone()[0]


async def test_answered_question_is_not_sent_by_delayed_job(env):
    bot,repo,_,r,t,*_=env
    app=await bot.start_application(r['id'],r['group_id'])
    q=await bot.prepare_question(app['id'],request_key='delayed',expected_revision=0,template_id=t['id'])
    await bot.record_answer(app['id'],q['id'],group_id=r['group_id'],event_id='answered-before-send',
                           text='Ответ',expected_revision=0)
    sent=[]
    async def send(event):
        sent.append(event)
    await run_once({'repository':repo,'handlers':{'question.send':send}},SQLQueue(repo.pool,r['group_id']))
    assert sent==[]
    with psycopg.connect(DSN) as c:
        assert c.execute("SELECT last_error_code FROM gim.outbox_events WHERE application_id=%s AND topic='question.send'",(app['id'],)).fetchone()[0]=='question_no_longer_active'


async def test_notification_checks_revocation_at_send_boundary(env):
    bot, worker, staff, r, t, vk, sid = env
    app, _, _ = await complete_draft(env)
    calls = []
    async def send(*args):
        calls.append(args)
    event = {'recipient_staff_id': sid, 'application_id': app['id'], 'vk_random_id': 123}
    assert await send_staff_notification(worker, event, send)
    with psycopg.connect(DSN) as c:
        c.execute('UPDATE gim.staff_members SET active=false,revoked_at=now() WHERE id=%s', (sid,))
    assert not await send_staff_notification(worker, event, send)
    assert len(calls) == 1


async def test_stale_analyzer_cannot_persist_or_acknowledge(env):
    from gim_db.repository import Conflict
    bot, worker, _, recruitment, *_ = env
    app, _, _ = await complete_draft(env)
    await bot.submit(app['id'])
    queue = SQLQueue(worker.pool, recruitment['group_id'])
    event = await queue.claim(['application.analyze'])
    with pytest.raises(Conflict, match='Outbox lease'):
        await worker.save_evaluation(app['id'], snapshot={}, score=0, criteria=[], summary='',
            request_key='stale', source_event_id=event['id'], source_lease_token=uuid.uuid4())
    with psycopg.connect(DSN) as c:
        assert c.execute('SELECT count(*) FROM gim.evaluations WHERE application_id=%s', (app['id'],)).fetchone()[0] == 0
        assert c.execute('SELECT completed_at IS NULL FROM gim.outbox_events WHERE id=%s', (event['id'],)).fetchone()[0]
