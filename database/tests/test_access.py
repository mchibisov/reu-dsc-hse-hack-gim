import uuid
import psycopg
import pytest
from test_database import DSN,env,complete_draft


async def test_staff_admin_scoping_and_unsubscribe(env):
    bot,worker,staff,r,t,vk,sid=env
    curator=vk+1
    await staff.set_staff(vk,r['group_id'],curator,role='curator',notify=False)
    with pytest.raises(Exception):await staff.set_staff(curator,r['group_id'],vk+2)
    with pytest.raises(Exception):await staff.set_staff(vk,r['group_id'],vk,active=False)
    with pytest.raises(Exception):await staff.set_staff(vk,r['group_id']+1,vk+2)
    a,q,ans=await complete_draft(env)
    await bot.submit(a['id'])
    await staff.decide(curator,a['id'],'invited')
    with psycopg.connect(DSN) as c:
        assert c.execute("SELECT count(*) FROM gim.outbox_events WHERE application_id=%s AND topic='staff.notify'",(a['id'],)).fetchone()[0]==1
    await staff.set_staff(vk,r['group_id'],curator,active=False)
    with pytest.raises(Exception):await staff.decide(curator,a['id'],'accepted')


async def test_frozen_config_and_question_and_worker_cannot_be_curator(env):
    bot,worker,staff,r,t,vk,sid=env
    with psycopg.connect(DSN,autocommit=True) as c:
        with pytest.raises(Exception):c.execute("UPDATE gim.recruitments SET rubric_version='changed' WHERE id=%s",(r['id'],))
        with pytest.raises(Exception):c.execute("UPDATE gim.question_templates SET text='Changed' WHERE id=%s",(t['id'],))
    a,q,ans=await complete_draft(env)
    async with worker.pool.connection() as c:
        with pytest.raises(Exception):await c.execute('SELECT gim.curator_evaluation(%s,%s,1,1::smallint,\'[]\',\'X\',\'{}\'::text[],\'[]\',\'k\')',(vk,a['id']))
        with pytest.raises(Exception):await c.execute("UPDATE gim.dialog_questions SET text='Подмена' WHERE id=%s",(q['id'],))
    with psycopg.connect(DSN,autocommit=True) as c:
        with pytest.raises(Exception):c.execute("UPDATE gim.dialog_questions SET text='Подмена' WHERE id=%s",(q['id'],))


async def test_zero_is_not_missing_and_no_100_application_cap(env):
    bot,worker,staff,r,t,vk,sid=env
    a,q,ans=await complete_draft(env)
    snap=await worker.evaluation_snapshot(a['id'])
    criteria=[{'code':'motivation','points':0,'reason':'Не подтверждено','evidence':[],'needs_review':True}]
    await worker.save_evaluation(a['id'],snapshot=snap,score=0,criteria=criteria,summary='Нужна проверка',request_key='zero')
    import asyncio
    await asyncio.gather(*[bot.start_application(r['id'],r['group_id']+i) for i in range(1,102)])
    bundle=await staff.export_bundle(vk,r['id'])
    assert bundle['Сводка']['total']==102 and bundle['Сводка']['unscored']==101
    assert bundle['Сводка']['average_score']==0 and bundle['Анкеты'][0]['score']==0

async def test_worker_login_cannot_impersonate_curator(env):
    bot,worker,staff,r,t,vk,sid=env
    a,q,answer=await complete_draft(env)
    snap=await worker.evaluation_snapshot(a['id'])
    cr=[{'code':'motivation','points':0,'reason':'x','evidence':[],'needs_review':True}]
    eid=await worker.save_evaluation(a['id'],snapshot=snap,score=0,criteria=cr,summary='x',request_key='source')
    with psycopg.connect(DSN,autocommit=True) as c:
        from psycopg import sql
        login='test_worker_'+uuid.uuid4().hex
        c.execute(sql.SQL('CREATE ROLE {} NOLOGIN INHERIT IN ROLE gim_worker').format(sql.Identifier(login)))
        try:
            with c.transaction():
                c.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(login)))
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with c.transaction():
                        c.execute("""INSERT INTO gim.evaluations(application_id,answers_revision,source,reviewer_staff_id,score,rubric_version,rubric_snapshot,criteria_results,input_snapshot,summary,request_key)
                        SELECT application_id,answers_revision,'curator',%s,score,rubric_version,rubric_snapshot,criteria_results,input_snapshot,summary,'impersonate' FROM gim.evaluations WHERE id=%s""",(sid,eid))
        finally:c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(login)))

async def test_real_login_provisioning(env,tmp_path):
    import json,os,subprocess,sys
    from pathlib import Path
    from psycopg import sql
    token=uuid.uuid4().hex[:12]
    cfg={s:{'login':f'gim_test_{s}_{token}','password':uuid.uuid4().hex} for s in ('bot','worker','staff')}
    f=tmp_path/'credentials.json';f.write_text(json.dumps(cfg));f.chmod(0o600)
    try:
        subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts'/'provision_runtime.py'),str(f)],env={'PATH':os.environ.get('PATH',''),'DATABASE_ADMIN_URL':DSN},check=True,capture_output=True)
        from psycopg.conninfo import conninfo_to_dict
        params=conninfo_to_dict(DSN)
        for service in cfg:
            with psycopg.connect(**{**params,'user':cfg[service]['login'],'password':cfg[service]['password']}) as c:
                if service=='staff':
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM gim.answers')
                else:assert c.execute('SELECT count(*)>=0 FROM gim.answers').fetchone()[0]
    finally:
        with psycopg.connect(DSN,autocommit=True) as c:
            for row in cfg.values():c.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(row['login'])))
