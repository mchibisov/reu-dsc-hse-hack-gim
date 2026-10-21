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
