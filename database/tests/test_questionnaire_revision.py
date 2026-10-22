import uuid
from datetime import date
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb
from test_database import DSN, env

pytestmark=pytest.mark.skipif(not DSN,reason='disposable PostgreSQL required')


@pytest.mark.parametrize('answered_old', [False, True])
async def test_revision_keeps_old_answer_skips_pending_question_and_allows_submit(env, answered_old):
    bot,worker,staff,recruitment,_,vk,_=env
    with psycopg.connect(DSN) as c:
        rid=c.execute("""INSERT INTO gim.recruitments(group_id,title,questionnaire_version,rubric_version,rubric)
            VALUES(%s,'Synthetic revision','museum-v1','test',%s) RETURNING id""",
            (recruitment['group_id'],Jsonb(recruitment['rubric']))).fetchone()[0]
        templates={}
        for position,slot,text in [(1,'experience','Опыт'),(8,'university_other','ВУЗ (Другое)'),(9,'faculty','Факультет')]:
            templates[slot]=c.execute("""INSERT INTO gim.question_templates
                (recruitment_id,code,kind,text,position,required,target_slot)
                VALUES(%s,%s,'base',%s,%s,true,%s) RETURNING id""",(rid,slot,text,position,slot)).fetchone()[0]
        c.execute("UPDATE gim.recruitments SET status='active',opened_at=now() WHERE id=%s",(rid,))
    app=await bot.start_application(rid,vk+100)
    await bot.set_consent(app['id'],'test')
    question=await bot.prepare_question(app['id'],request_key='old',expected_revision=0,template_id=templates['experience'])
    await bot.record_answer(app['id'],question['id'],group_id=recruitment['group_id'],event_id=str(uuid.uuid4()),
                            text='Старый ответ сохранён',expected_revision=0)
    pending=await bot.prepare_question(app['id'],request_key='retired',expected_revision=1,template_id=templates['university_other'])
    revision=1
    if answered_old:
        await bot.record_answer(app['id'],pending['id'],group_id=recruitment['group_id'],event_id=str(uuid.uuid4()),
                                text='Сохранённый ответ на прежний вопрос 8',expected_revision=1)
        revision=2
    migration=Path(__file__).parents[1]/'supabase/migrations/20261022030000_questionnaire_revision.sql'
    with psycopg.connect(DSN) as c:
        c.execute(migration.read_text(encoding='utf-8'),prepare=False)
    context=await bot.dialog_context(app['id'])
    assert context['answers'][0]['answer_text']=='Старый ответ сохранён'
    assert context['application']['current_question_id'] is None
    assert next(q for q in context['questions'] if q['id']==pending['id'])['status']==('answered' if answered_old else 'skipped')
    if answered_old:
        assert context['answers'][1]['answer_text']=='Сохранённый ответ на прежний вопрос 8'
    assert 'university_other' not in {t['target_slot'] for t in context['templates']}
    assert next(t for t in context['templates'] if t['target_slot']=='faculty')['text']=='Факультет, направление'
    from gim_db.repository import Conflict
    with pytest.raises(Conflict,match='retired'):
        await bot.prepare_question(app['id'],request_key='stale-old-bank',expected_revision=revision,
                                   template_id=templates['university_other'])
    faculty=await bot.prepare_question(app['id'],request_key='faculty',expected_revision=revision,template_id=templates['faculty'])
    from gim_db.outbox import SQLQueue, run_once
    from gim.shared_service import question_text
    delivered=[]
    async def send(event):
        delivered.append(question_text(event['question'],event['question']['vk_id']))
    await run_once({'repository':worker,'handlers':{'question.send':send}},
                   SQLQueue(worker.pool,recruitment['group_id']),limit=10,topics=['question.send'])
    assert delivered==['Основная анкета · 2 из 2\n\nФакультет, направление']
    await bot.record_answer(app['id'],faculty['id'],group_id=recruitment['group_id'],event_id=str(uuid.uuid4()),
                            text='Исторический, музеология',expected_revision=revision)
    await bot.set_profile(app['id'],expected_revision=revision+1,birth_date=date(2000,1,1),selected_directions=['media'],undecided=False,facts={})
    assert (await bot.submit(app['id']))['status']=='submitted'
    with psycopg.connect(DSN) as c:
        assert c.execute("SELECT tgenabled FROM pg_trigger WHERE tgname='freeze_templates'").fetchone()[0]=='O'


@pytest.mark.parametrize('next_prompt_sent,reply_cmid', [(False,21),(True,23),(True,21)])
async def test_new_receipt_after_retirement_preserves_previous_answer(env, next_prompt_sent, reply_cmid):
    from types import SimpleNamespace
    from gim.shared_gateway import enqueue_events
    from gim.shared_service import SharedService
    from gim_db.outbox import SQLQueue, run_once

    bot,worker,staff,recruitment,_,vk,_=env
    actor=vk+200
    with psycopg.connect(DSN) as c:
        rid=c.execute("""INSERT INTO gim.recruitments(group_id,title,questionnaire_version,rubric_version,rubric)
            VALUES(%s,'Synthetic late receipt','museum-v1','test',%s) RETURNING id""",
            (recruitment['group_id'],Jsonb(recruitment['rubric']))).fetchone()[0]
        templates={}
        for position,slot in [(1,'consent'),(7,'university'),(8,'university_other'),(9,'faculty')]:
            templates[slot]=c.execute("""INSERT INTO gim.question_templates
                (recruitment_id,code,kind,text,position,required,target_slot)
                VALUES(%s,%s,'base',%s,%s,true,%s) RETURNING id""",(rid,slot,slot,position,slot)).fetchone()[0]
        c.execute("UPDATE gim.recruitments SET status='active',opened_at=now() WHERE id=%s",(rid,))
    app=await bot.start_application(rid,actor)
    await bot.set_consent(app['id'],'test')
    for revision,slot,text in [(0,'consent','Согласен'),(1,'university','Сохранённый университет')]:
        question=await bot.prepare_question(app['id'],request_key=slot,expected_revision=revision,template_id=templates[slot])
        await bot.record_answer(app['id'],question['id'],group_id=recruitment['group_id'],event_id=str(uuid.uuid4()),
                                text=text,expected_revision=revision)
    retired=await bot.prepare_question(app['id'],request_key='old-visible',expected_revision=2,template_id=templates['university_other'])
    with psycopg.connect(DSN) as c:
        c.execute("UPDATE gim.dialog_questions SET asked_at=now(),sent_cmid=20 WHERE id=%s",(retired['id'],))
        migration=Path(__file__).parents[1]/'supabase/migrations/20261022030000_questionnaire_revision.sql'
        c.execute(migration.read_text(encoding='utf-8'),prepare=False)
    faculty=None
    if next_prompt_sent:
        faculty=await bot.prepare_question(app['id'],request_key='next-visible',expected_revision=2,template_id=templates['faculty'])
        with psycopg.connect(DSN) as c:
            c.execute("UPDATE gim.dialog_questions SET asked_at=now(),sent_cmid=22 WHERE id=%s",(faculty['id'],))
    event_id=str(uuid.uuid4())
    answers_faculty=next_prompt_sent and reply_cmid>22
    event={'type':'message_new','group_id':recruitment['group_id'],'event_id':event_id,
           'object':{'message':{'from_id':actor,'peer_id':actor,'conversation_message_id':reply_cmid,
                                'text':'История, музеология' if answers_faculty else 'Поздний ответ на удалённый вопрос'}}}
    async with bot.pool.connection() as c,c.transaction():
        await enqueue_events(c,[event],recruitment['group_id'],'')
    with psycopg.connect(DSN) as c:
        from gim.vk import message_event
        receipt=c.execute("SELECT payload->'receipt' FROM gim.outbox_events WHERE dedupe_key=%s",
                          (f"vk-in:{recruitment['group_id']}:{message_event(event)['event_id']}",)).fetchone()[0]
    assert receipt['question_id']==str(faculty['id'] if answers_faculty else retired['id'])
    service=SharedService(bot,worker,staff,None,SimpleNamespace(group_id=recruitment['group_id'],recruitment_id=rid,
        analysis_rubric_path='',max_followups=0,llm_api_key='',max_answer_length=2000,consent_version='test'),None)
    await run_once({'repository':worker,'handlers':service.handlers},SQLQueue(worker.pool,recruitment['group_id']),
                   limit=1,topics=['vk.incoming'])
    context=await bot.dialog_context(app['id'])
    slots={q['id']:q['target_slot'] for q in context['questions']}
    university=[a for a in context['answers'] if slots[a['question_id']]=='university']
    assert len(university)==1 and university[0]['answer_text']=='Сохранённый университет'
    if answers_faculty:
        assert any(slots[a['question_id']]=='faculty' and a['answer_text']=='История, музеология' for a in context['answers'])
    else:
        assert context['application']['answers_revision']==2
        assert next(q for q in context['questions'] if q['id']==context['application']['current_question_id'])['target_slot']=='faculty'
