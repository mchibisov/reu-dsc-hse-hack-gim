import hashlib
import uuid
import psycopg
import pytest
from test_database import DSN,env,complete_draft


async def test_resume_snapshot_and_export_scope(env):
    from gim_db.storage import FileRepository
    bot,worker,staff,r,t,vk,sid=env
    a,q,ans=await complete_draft(env)
    fr=FileRepository(worker.pool)
    f=await fr.reserve_resume(a['id'],mime_type='application/pdf')
    assert f['version']==1 and f['status']=='pending'
    await fr.finish(f['id'],size_bytes=42,sha256=hashlib.sha256(b'resume').hexdigest(),extracted_text='Съёмка музейных коллекций',extraction_version='test')
    snap=await worker.evaluation_snapshot(a['id'])
    assert snap['input_snapshot']['revision']==2 and snap['input_snapshot']['files'][0]['id']==str(f['id'])
    cr=[{'code':'motivation','points':1,'reason':'Опыт','evidence':[{'source_type':'file','source_id':str(f['id']),'quote':'музейных коллекций'}]}]
    await worker.save_evaluation(a['id'],snapshot=snap,score=1,criteria=cr,summary='X',request_key='resume')
    f2=await fr.reserve_resume(a['id'],mime_type='application/pdf')
    await fr.finish(f2['id'],size_bytes=10,sha256=hashlib.sha256(b'new').hexdigest(),extracted_text='Другой документ',extraction_version='test')
    new=await worker.evaluation_snapshot(a['id'])
    assert new['input_snapshot']['revision']==3
    with pytest.raises(Exception):await worker.save_evaluation(a['id'],snapshot=new,score=1,criteria=cr,summary='X',request_key='wrongresume')
    fid=await staff.request_export(vk,r['id'],request_key='cohort')
    with psycopg.connect(DSN) as c:
        scope,app=c.execute('SELECT scope,application_id FROM gim.files WHERE id=%s',(fid,)).fetchone()
        assert scope=='cohort' and app is None
    await fr.finish(fid,size_bytes=10,sha256=hashlib.sha256(b'xlsx').hexdigest())
    meta=await staff.staff_file(vk,fid)
    assert meta['scope']=='cohort'
    with pytest.raises(Exception):await staff.staff_file(vk+1,fid)
    with pytest.raises(Exception):await fr.finish(f['id'],size_bytes=43,sha256=hashlib.sha256(b'bad').hexdigest())
