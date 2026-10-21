import uuid
import psycopg
import pytest
from test_database import env,DSN,complete_draft
pytestmark=pytest.mark.skipif(not DSN,reason='disposable PostgreSQL required')

async def test_reset_requires_admin_preserves_attempt_and_is_idempotent(env):
    bot,worker,staff,r,t,admin,sid=env
    app,_,_=await complete_draft(env)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with staff.pool.connection() as c:
            await c.execute('SELECT gim.reset_own_application(%s,%s,%s)',(r['group_id'],r['id'],'denied'))
    own=await bot.start_application(r['id'],admin)
    async with staff.pool.connection() as c:
        first=await (await c.execute('SELECT gim.reset_own_application(%s,%s,%s) id',(admin,r['id'],'reset-1'))).fetchone()
        replay=await (await c.execute('SELECT gim.reset_own_application(%s,%s,%s) id',(admin,r['id'],'reset-1'))).fetchone()
    assert first['id']==replay['id'] and first['id']!=own['id']
    assert (await bot.start_application(r['id'],admin))['id']==first['id']
    with psycopg.connect(DSN) as c:
        assert c.execute('SELECT archived FROM gim.applications WHERE id=%s',(own['id'],)).fetchone()[0]
        assert c.execute('SELECT count(*) FROM gim.answers WHERE application_id=%s',(app['id'],)).fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM gim.staff_members WHERE id=%s AND active',(sid,)).fetchone()[0]==1
    bundle=await staff.export_bundle(admin,r['id'])
    assert str(own['id']) not in [x['application_id'] for x in bundle['Анкеты']]

async def test_expectation_check_does_not_consume_ai_followup_budget(env):
    bot,worker,staff,r,t,admin,sid=env
    a=await bot.start_application(r['id'],r['group_id']+123)
    q=await bot.prepare_question(a['id'],request_key='expectation',expected_revision=0,
        text='Совпадают ли задачи?',target_slot='expectations_match',purpose='expectations')
    await bot.record_answer(a['id'],q['id'],group_id=r['group_id'],event_id='e-'+str(uuid.uuid4()),text='Да',value=None,expected_revision=0)
    for i in range(5):
        q2=await bot.prepare_question(a['id'],request_key='actual-followup-'+str(i),expected_revision=i+1,
            text='Какие задачи выполняли лично? '+str(i),target_slot='experience_detail_'+str(i),purpose='clarify')
        await bot.record_answer(a['id'],q2['id'],group_id=r['group_id'],event_id='f-'+str(uuid.uuid4()),text='Работал',value=None,expected_revision=i+1)
    assert q2['id']!=q['id']

async def test_archived_attempt_rejects_delayed_write(env):
    from gim_db.repository import Conflict
    bot,worker,staff,r,t,admin,sid=env
    own=await bot.start_application(r['id'],admin)
    await staff.reset_own_application(admin,r['id'],request_key='late')
    with pytest.raises(Conflict):
        await bot.prepare_question(own['id'],request_key='late-question',expected_revision=0,text='Устаревший вопрос',target_slot='old')

async def test_rubric_pinned_once_before_answers_keeps_recruitment_unchanged(env):
    bot,worker,staff,r,t,admin,sid=env
    a=await bot.start_application(r['id'],r['group_id']+987)
    rubric={'criteria':[{'code':'motivation','max_points':3}],'version':'new','approved_by':'test'}
    await bot.pin_rubric(a['id'],rubric,'new')
    await bot.pin_rubric(a['id'],{'different':True},'wrong')
    snapshot=await worker.evaluation_snapshot(a['id'])
    assert snapshot['rubric_version']=='new' and snapshot['rubric']==rubric
    with psycopg.connect(DSN) as c:
        assert c.execute('SELECT rubric_version FROM gim.recruitments WHERE id=%s',(r['id'],)).fetchone()[0]=='test'

async def test_delivery_lane_does_not_claim_slow_analysis(env):
    from gim_db.repository import emit
    from gim_db.outbox import SQLQueue,run_once
    bot,worker,staff,r,t,admin,sid=env
    async with worker.pool.connection() as c:
        await emit(c,None,'application.analyze','slow-'+str(uuid.uuid4()),{'group_id':r['group_id']})
        await emit(c,None,'vk.send','fast-'+str(uuid.uuid4()),{'group_id':r['group_id'],'peer_id':admin,'text':'Готово'})
    delivered=[]
    async def send(event):delivered.append(event['payload']['text'])
    ctx={'repository':worker,'handlers':{'vk.send':send}}
    await run_once(ctx,SQLQueue(worker.pool,r['group_id']),limit=1,topics=['vk.send'])
    assert delivered==['Готово']

async def test_code_export_excludes_archived_attempts(env):
    from gim.shared_export_access import EXPORT_QUERY
    bot,worker,staff,r,t,admin,sid=env
    own=await bot.start_application(r['id'],admin)
    await staff.reset_own_application(admin,r['id'],request_key='private-code-archive')
    async with worker.pool.connection() as c:
        bundle=await (await c.execute(EXPORT_QUERY,(r['id'],r['id']))).fetchone()
    data=next(iter(bundle.values()))
    assert str(own['id']) not in [a['application_id'] for a in data['Анкеты']]

async def test_gateway_captures_same_prompt_for_rapid_fragments(env):
    from gim.shared_gateway import GatewayLedger
    bot,worker,staff,r,t,admin,sid=env
    a=await bot.start_application(r['id'],admin)
    q=await bot.prepare_question(a['id'],request_key='receipt-q',expected_revision=0,template_id=t['id'])
    with psycopg.connect(DSN) as c:c.execute('UPDATE gim.dialog_questions SET asked_at=now() WHERE id=%s',(q['id'],))
    ledger=GatewayLedger(bot.pool,r['group_id']);await ledger.acquire()
    events=[{'group_id':r['group_id'],'type':'message_new','event_id':str(uuid.uuid4()),'object':{'message':{'from_id':admin,'peer_id':admin,'text':text}}} for text in ('Первый фрагмент','Второй фрагмент')]
    await ledger.ingest_batch(events,r['group_id'],'2');await ledger.release()
    with psycopg.connect(DSN) as c:
        rows=c.execute("SELECT payload->'receipt' FROM gim.outbox_events WHERE payload->>'serial_key'=%s",(f"vk:{r['group_id']}:{admin}",)).fetchall()
    assert len(rows)==2 and all(row[0]['question_id']==str(q['id']) for row in rows)

async def test_postgres_exports_are_private_immutable_and_retry_safe(env):
    from gim.serverless import PostgresPrivateStorage
    bot,worker,staff,r,t,admin,sid=env
    fid=await staff.request_export(admin,r['id'],kind='xlsx',request_key='bytes')
    async with worker.pool.connection() as c:meta=await (await c.execute('SELECT * FROM gim.files WHERE id=%s',(fid,))).fetchone()
    store=PostgresPrivateStorage(worker.pool)
    await store.upload(meta,b'test-xlsx');await store.upload(meta,b'test-xlsx')
    assert await store.read(meta)==b'test-xlsx'
    with pytest.raises(ValueError):await store.upload(meta,b'changed')
    async with bot.pool.connection() as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):await c.execute('SELECT * FROM gim.file_contents')

async def test_delayed_callback_uses_vk_order_not_arrival_time(env):
    from gim.shared_gateway import enqueue_events
    bot,worker,staff,r,t,admin,sid=env
    a=await bot.start_application(r['id'],admin)
    old=await bot.prepare_question(a['id'],request_key='old-visible',expected_revision=0,template_id=t['id'])
    await bot.record_answer(a['id'],old['id'],group_id=r['group_id'],event_id='first-fragment',text='Первый фрагмент',value=None,expected_revision=0)
    new=await bot.prepare_question(a['id'],request_key='new-visible',expected_revision=1,text='Следующий вопрос',target_slot='details')
    with psycopg.connect(DSN) as c:
        c.execute('UPDATE gim.dialog_questions SET asked_at=now(),sent_cmid=40 WHERE id=%s',(old['id'],))
        c.execute('UPDATE gim.dialog_questions SET asked_at=now(),sent_cmid=50 WHERE id=%s',(new['id'],))
    event={'group_id':r['group_id'],'type':'message_new','event_id':'delayed','object':{'message':{'from_id':admin,'peer_id':admin,'conversation_message_id':49,'text':'Второй фрагмент'}}}
    async with bot.pool.connection() as c,c.transaction():await enqueue_events(c,[event],r['group_id'],'')
    with psycopg.connect(DSN) as c:
        receipt=c.execute("SELECT payload->'receipt' FROM gim.outbox_events WHERE dedupe_key=%s",(f"vk-in:{r['group_id']}:message:{admin}:49",)).fetchone()[0]
    assert receipt['question_id']==str(old['id'])

async def test_bounded_dispatcher_hands_off_slow_work_without_idle_spin(env):
    import time
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import patch,AsyncMock
    from gim.serverless import drain
    from gim_db.repository import emit
    bot,worker,staff,r,t,admin,sid=env
    with psycopg.connect(DSN) as c:
        c.execute("""CREATE OR REPLACE FUNCTION gim.wake_worker(bigint) RETURNS bigint LANGUAGE sql AS $$
          INSERT INTO gim.audit_log(action,details) VALUES('test.cloud_wake',jsonb_build_object('group',$1)) RETURNING 1::bigint $$""")
        c.execute('REVOKE ALL ON FUNCTION gim.wake_worker(bigint) FROM PUBLIC')
        c.execute('GRANT EXECUTE ON FUNCTION gim.wake_worker(bigint) TO gim_bot')
    async with worker.pool.connection() as c:await emit(c,None,'application.analyze','handoff-'+str(uuid.uuid4()),{'group_id':r['group_id']})
    @asynccontextmanager
    async def existing(dsn,**kwargs):yield {'bot':bot.pool,'worker':worker.pool,'staff':staff.pool}[dsn]
    settings=SimpleNamespace(database_bot_url='bot',database_worker_url='worker',database_staff_url='staff',group_id=r['group_id'])
    started=time.monotonic()
    with patch('gim.serverless.create_pool',existing),patch('gim.serverless.VK',return_value=SimpleNamespace(close=AsyncMock())):
        assert await drain(settings,budget=10)=='drained'
    assert time.monotonic()-started<3
    with psycopg.connect(DSN) as c:
        assert c.execute("SELECT count(*) FROM gim.audit_log WHERE action='test.cloud_wake' AND details->>'group'=%s",(str(r['group_id']),)).fetchone()[0]==1
        assert c.execute('SELECT expires_at<=now() FROM gim.runtime_leases WHERE group_id=%s',(r['group_id'],)).fetchone()[0]

async def test_terminal_analysis_failure_notifies_once_without_fake_score(env):
    from gim_db.outbox import SQLQueue
    from gim_db.repository import emit
    bot,worker,staff,r,t,admin,sid=env
    a,_,_=await complete_draft(env)
    async with worker.pool.connection() as c:
        e=await emit(c,a['id'],'application.analyze','terminal-'+str(uuid.uuid4()),{'revision':1})
        await c.execute("UPDATE gim.outbox_events SET max_attempts=1 WHERE application_id=%s AND topic='application.analyze'",(a['id'],))
    queue=SQLQueue(worker.pool,r['group_id'])
    event=await queue.claim(['application.analyze'])
    assert await queue.finish(event['id'],event['lease_token'],False,'ModelUnavailable')
    assert not await queue.finish(event['id'],event['lease_token'],False,'ModelUnavailable')
    with psycopg.connect(DSN) as c:
        n=c.execute("SELECT count(*) FROM gim.outbox_events WHERE application_id=%s AND topic='staff.notify' AND payload->>'kind'='analysis_unavailable'",(a['id'],)).fetchone()[0]
        assert n==1
        assert c.execute('SELECT count(*) FROM gim.evaluations WHERE application_id=%s',(a['id'],)).fetchone()[0]==0

async def test_final_expired_analysis_lease_notifies_once(env):
    from gim_db.outbox import SQLQueue
    from gim_db.repository import emit
    bot,worker,staff,r,t,admin,sid=env
    a,_,_=await complete_draft(env)
    async with worker.pool.connection() as c:
        await emit(c,a['id'],'application.analyze','expired-'+str(uuid.uuid4()),{'revision':1})
        await c.execute("UPDATE gim.outbox_events SET max_attempts=1,attempts=1,lease_token=gen_random_uuid(),lease_until=now()-interval '1 second' WHERE application_id=%s AND topic='application.analyze'",(a['id'],))
    q=SQLQueue(worker.pool,r['group_id'])
    assert await q.claim(['application.analyze']) is None
    assert await q.claim(['application.analyze']) is None
    with psycopg.connect(DSN) as c:
        assert c.execute("SELECT count(*) FROM gim.outbox_events WHERE application_id=%s AND payload->>'kind'='analysis_unavailable'",(a['id'],)).fetchone()[0]==1
