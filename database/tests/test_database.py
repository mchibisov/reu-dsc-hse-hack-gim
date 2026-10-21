import os
from pathlib import Path
import psycopg
import pytest

DSN = os.environ.get('TEST_DATABASE_URL', 'postgresql://maxchibisov@127.0.0.1:55432/postgres')


def test_twelve_private_tables():
    with psycopg.connect(DSN) as c:
        tables = c.execute("SELECT tablename FROM pg_tables WHERE schemaname='gim'").fetchall()
        assert {r[0] for r in tables} == {'users','staff_members','recruitments','question_templates','applications','dialog_questions','answers','evaluations','files','inbox_events','outbox_events','audit_log'}


def test_no_public_or_staff_table_access():
    with psycopg.connect(DSN) as c:
        assert not c.execute("SELECT has_schema_privilege('public','gim','USAGE')").fetchone()[0]
        assert not c.execute("SELECT has_table_privilege('gim_staff','gim.answers','SELECT')").fetchone()[0]

import asyncio
import time
import uuid
from datetime import date
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool


@pytest.fixture
async def env():
    from gim_db.repository import Repository
    group = int(uuid.uuid4().int % 1000000000) + 1
    rubric = {'criteria':[{'code':'motivation','max_points':3}], 'approval':'synthetic-test-only'}
    with psycopg.connect(DSN, row_factory=dict_row) as c:
        r = c.execute("INSERT INTO gim.recruitments(group_id,title,questionnaire_version,rubric_version,rubric) VALUES(%s,'Synthetic test','test','test',%s) RETURNING *",(group,Jsonb(rubric))).fetchone()
        t = c.execute("INSERT INTO gim.question_templates(recruitment_id,code,kind,text,position,required,target_slot) VALUES(%s,'experience','base','Опишите опыт',1,true,'experience') RETURNING *",(r['id'],)).fetchone()
        c.execute("UPDATE gim.recruitments SET status='active',opened_at=now() WHERE id=%s",(r['id'],))
        u = c.execute('INSERT INTO gim.users(vk_id) VALUES(%s) RETURNING id',(group+10000000000,)).fetchone()
        s = c.execute("INSERT INTO gim.staff_members(user_id,group_id,role) VALUES(%s,%s,'admin') RETURNING id",(u['id'],group)).fetchone()
    async with AsyncConnectionPool(DSN, min_size=1,max_size=8,open=False,kwargs={'autocommit':True,'row_factory':dict_row,'prepare_threshold':None,'options':'-c role=gim_bot'}) as bp:
        async with AsyncConnectionPool(DSN, min_size=1,max_size=4,open=False,kwargs={'autocommit':True,'row_factory':dict_row,'prepare_threshold':None,'options':'-c role=gim_worker'}) as wp:
            async with AsyncConnectionPool(DSN, min_size=1,max_size=2,open=False,kwargs={'autocommit':True,'row_factory':dict_row,'prepare_threshold':None,'options':'-c role=gim_staff'}) as sp:
                yield Repository(bp),Repository(wp),Repository(sp),r,t,group+10000000000,s['id']


async def complete_draft(env, suffix=0):
    bot,worker,staff,r,t,vk,sid = env
    a = await bot.start_application(r['id'],r['group_id']+suffix)
    await bot.set_consent(a['id'],'test-policy')
    q = await bot.prepare_question(a['id'],request_key='q1',expected_revision=0,template_id=t['id'])
    ans = await bot.record_answer(a['id'],q['id'],group_id=r['group_id'],event_id=f'a{suffix}',text='Снимал концерты',value=None,expected_revision=0)
    await bot.set_profile(a['id'],expected_revision=1,birth_date=date(2000,1,1),selected_directions=['media'],undecided=False,facts={})
    return a,q,ans


async def test_question_saved_and_reused_before_answer(env):
    bot,worker,staff,r,t,*_=env
    a=await bot.start_application(r['id'],r['group_id'])
    q=await bot.prepare_question(a['id'],request_key='first',expected_revision=0,text='Покажете портфолио?',target_slot='portfolio',context={'answer_ids':[]})
    q2=await bot.prepare_question(a['id'],request_key='first',expected_revision=0,text='Другая генерация',target_slot='portfolio')
    assert q['id']==q2['id'] and q2['text']=='Покажете портфолио?'
    history=await bot.dialog_context(a['id'])
    assert history['questions'][0]['text']=='Покажете портфолио?' and history['answers']==[]
    with psycopg.connect(DSN) as c:
        assert c.execute("SELECT count(*) FROM gim.outbox_events WHERE application_id=%s AND topic='question.send'",(a['id'],)).fetchone()[0]==1
    with pytest.raises(Exception):
        await bot.prepare_question(a['id'],request_key='other',expected_revision=0,text='Ещё вопрос',target_slot='portfolio')


async def test_duplicate_and_concurrent_events(env):
    bot,worker,staff,r,t,*_=env
    a=await bot.start_application(r['id'],r['group_id'])
    q=await bot.prepare_question(a['id'],request_key='q1',expected_revision=0,template_id=t['id'])
    async def write(event='same',text='Один ответ'):
        return await bot.record_answer(a['id'],q['id'],group_id=r['group_id'],event_id=event,text=text,expected_revision=0)
    results=await asyncio.gather(*[write() for _ in range(10)])
    assert len({x['id'] for x in results})==1
    with pytest.raises(Exception): await write(text='Подменённый ответ')
    with pytest.raises(Exception): await write(event='other')
    with psycopg.connect(DSN) as c:
        assert c.execute('SELECT answers_revision FROM gim.applications WHERE id=%s',(a['id'],)).fetchone()[0]==1


async def test_submission_checks_required_consent_age(env):
    bot,_,_,r,t,*_=env
    a=await bot.start_application(r['id'],r['group_id'])
    with pytest.raises(Exception): await bot.submit(a['id'])
    await bot.set_consent(a['id'],'test')
    with pytest.raises(Exception): await bot.submit(a['id'])
    q=await bot.prepare_question(a['id'],request_key='q',expected_revision=0,template_id=t['id'])
    await bot.record_answer(a['id'],q['id'],group_id=r['group_id'],event_id='a',text='Ответ',expected_revision=0)
    await bot.set_profile(a['id'],expected_revision=1,birth_date=date.today(),selected_directions=['media'],undecided=False,facts={})
    with pytest.raises(Exception): await bot.submit(a['id'])
    await bot.set_profile(a['id'],expected_revision=1,birth_date=date(2000,1,1),selected_directions=['media'],undecided=False,facts={})
    await bot.submit(a['id']); await bot.submit(a['id'])
    with psycopg.connect(DSN) as c:
        topics=c.execute('SELECT topic FROM gim.outbox_events WHERE application_id=%s',(a['id'],)).fetchall()
        assert [x[0] for x in topics].count('application.analyze')==1
        assert [x[0] for x in topics].count('staff.notify')==1


async def test_evidence_manual_priority_and_staff_revocation(env):
    bot,worker,staff,r,t,vk,sid=env
    a,q,answer=await complete_draft(env)
    await bot.submit(a['id'])
    snapshot=await worker.evaluation_snapshot(a['id'])
    criteria=[{'code':'motivation','points':2,'reason':'Есть опыт','evidence':[{'source_type':'answer','source_id':str(answer['id']),'quote':'Снимал концерты'}]}]
    await worker.save_evaluation(a['id'],snapshot=snapshot,score=2,criteria=criteria,summary='Опыт',request_key='model1')
    manual=await staff.curator_evaluation(vk,a['id'],revision=1,score=3,criteria=criteria,summary='Уточнено сотрудником',request_key='human1')
    await worker.save_evaluation(a['id'],snapshot=snapshot,score=1,criteria=criteria,summary='Поздний ответ',request_key='model2')
    bundle=await staff.export_bundle(vk,r['id'])
    assert bundle['Анкеты'][0]['evaluation_id']==str(manual) and bundle['Анкеты'][0]['score']==3
    assert bundle['Ответы'][0]['answer_text']=='Снимал концерты'
    assert bundle['Сводка']['unscored']==0
    bad=[{**criteria[0],'evidence':[{'source_type':'answer','source_id':str(answer['id']),'quote':'выдуманная цитата'}]}]
    with pytest.raises(Exception): await worker.save_evaluation(a['id'],snapshot=snapshot,score=2,criteria=bad,summary='X',request_key='bad')
    with pytest.raises(Exception): await staff.export_bundle(vk+1,r['id'])
    with psycopg.connect(DSN) as c: c.execute('UPDATE gim.staff_members SET active=false,revoked_at=now() WHERE id=%s',(sid,))
    with pytest.raises(Exception): await staff.export_bundle(vk,r['id'])
    assert not await worker.notification_allowed(sid,a['id'])


async def test_cross_candidate_and_stale_answer_rejected(env):
    bot,worker,staff,r,t,*_=env
    a,q,ans=await complete_draft(env)
    other,_,foreign=await complete_draft(env,1)
    snap=await worker.evaluation_snapshot(a['id'])
    cr=[{'code':'motivation','points':1,'reason':'x','evidence':[{'source_type':'answer','source_id':str(foreign['id']),'quote':'Снимал концерты'}]}]
    with pytest.raises(Exception): await worker.save_evaluation(a['id'],snapshot=snap,score=1,criteria=cr,summary='x',request_key='cross')
    await bot.record_answer(a['id'],q['id'],group_id=r['group_id'],event_id='edit',text='Теперь другой ответ',expected_revision=1)
    new_snap=await worker.evaluation_snapshot(a['id'])
    cr[0]['evidence'][0]['source_id']=str(ans['id'])
    with pytest.raises(Exception): await worker.save_evaluation(a['id'],snapshot=new_snap,score=1,criteria=cr,summary='x',request_key='oldanswer')


async def test_50_concurrent_candidates(env):
    bot,worker,staff,r,t,vk,sid=env
    start=time.perf_counter()
    async def candidate(i):
        a,q,ans=await complete_draft(env,i)
        await bot.submit(a['id'])
        return a['id']
    ids=await asyncio.gather(*[candidate(i) for i in range(50)])
    elapsed=time.perf_counter()-start
    assert len(set(ids))==50
    bundle=await staff.export_bundle(vk,r['id'])
    assert len(bundle['Анкеты'])==50 and bundle['Сводка']['unscored']==50
    assert all(x['score'] is None for x in bundle['Анкеты'])
    print(f'50 candidates: {elapsed:.3f}s; bot pool max=8, worker=4, staff=2; local PostgreSQL')

async def test_export_request_freezes_data(env):
    bot,worker,staff,r,t,vk,sid=env
    a,q,answer=await complete_draft(env)
    fid=await staff.request_export(vk,r['id'],request_key='frozen')
    await bot.record_answer(a['id'],q['id'],group_id=r['group_id'],event_id='later',text='Исправленный ответ',expected_revision=1)
    with psycopg.connect(DSN) as c:
        payload=c.execute("SELECT payload FROM gim.outbox_events WHERE file_id=%s",(fid,)).fetchone()[0]
        assert payload['snapshot']['Ответы'][0]['answer_text']=='Снимал концерты'
        assert len(payload['snapshot']['Ответы'])==1


async def test_cannot_submit_with_unfinished_resume(env):
    from gim_db.storage import FileRepository
    bot,worker,*_=env
    a,q,answer=await complete_draft(env)
    await FileRepository(worker.pool).reserve_resume(a['id'],mime_type='application/pdf')
    with pytest.raises(Exception): await bot.submit(a['id'])

async def test_bot_cannot_reopen_submitted_application(env):
    bot,*_=env
    a,_,_=await complete_draft(env)
    await bot.submit(a['id'])
    async with bot.pool.connection() as c:
        with pytest.raises(Exception): await c.execute("UPDATE gim.applications SET status='draft' WHERE id=%s",(a['id'],))
