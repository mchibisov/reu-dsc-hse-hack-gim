-- Synthetic, transactional smoke check. ROLLBACK removes all test records.
BEGIN;
DO $$
DECLARE rid uuid; uid uuid; aid uuid; tid uuid; qid uuid; sid uuid; admin_uid uuid; snap jsonb; result jsonb; forbidden boolean:=false;
BEGIN
 INSERT INTO gim.recruitments(group_id,title,questionnaire_version,rubric_version,rubric) VALUES(999000111,'Cloud synthetic smoke','test','test','{"criteria":[{"code":"test","max_points":3}]}') RETURNING id INTO rid;
 INSERT INTO gim.question_templates(recruitment_id,code,kind,text,position,required,target_slot) VALUES(rid,'test','base','Synthetic question',1,true,'test') RETURNING id INTO tid;
 UPDATE gim.recruitments SET status='active' WHERE id=rid;
 INSERT INTO gim.users(vk_id) VALUES(999000112) RETURNING id INTO uid;
 INSERT INTO gim.users(vk_id) VALUES(999000113) RETURNING id INTO admin_uid;
 INSERT INTO gim.staff_members(user_id,group_id,role) VALUES(admin_uid,999000111,'admin') RETURNING id INTO sid;
 PERFORM set_config('role','gim_bot',true);
 INSERT INTO gim.applications(user_id,recruitment_id) VALUES(uid,rid) RETURNING id INTO aid;
 INSERT INTO gim.dialog_questions(application_id,template_id,source,text,target_slot,position,based_on_revision,request_key)
 VALUES(aid,tid,'base','Synthetic question','test',1,0,'q') RETURNING id INTO qid;
 UPDATE gim.applications SET current_question_id=qid WHERE id=aid;
 INSERT INTO gim.inbox_events(group_id,event_id,application_id,fingerprint) VALUES(999000111,'smoke',aid,'synthetic');
 INSERT INTO gim.answers(application_id,question_id,revision,answer_text,group_id,event_id) VALUES(aid,qid,1,'Synthetic answer',999000111,'smoke');
 UPDATE gim.dialog_questions SET status='answered' WHERE id=qid;
 UPDATE gim.applications SET current_question_id=NULL,birth_date=date '2000-01-01',consent_version='test',consent_at=now(),selected_directions=ARRAY['media'],status='submitted',submitted_at=now() WHERE id=aid;
 IF (SELECT count(*) FROM gim.outbox_events WHERE application_id=aid)<>2 THEN RAISE EXCEPTION 'missing transactional intents'; END IF;
 BEGIN UPDATE gim.applications SET status='draft' WHERE id=aid; EXCEPTION WHEN others THEN forbidden:=true; END;
 IF NOT forbidden THEN RAISE EXCEPTION 'reopen allowed'; END IF;
 PERFORM set_config('role','gim_staff',true);
 result:=gim.export_bundle(999000113,rid,NULL,'{}');
 IF (result->'Сводка'->>'unscored')::int<>1 THEN RAISE EXCEPTION 'null score lost'; END IF;
 forbidden:=false;
 BEGIN result:=gim.export_bundle(999000112,rid,NULL,'{}'); EXCEPTION WHEN insufficient_privilege THEN forbidden:=true; END;
 IF NOT forbidden THEN RAISE EXCEPTION 'staff access leaked'; END IF;
 PERFORM set_config('role','postgres',true);
END $$;
SELECT count(*)=12 AS twelve_tables, bool_and(rowsecurity) AS all_rls
FROM pg_tables WHERE schemaname='gim';
ROLLBACK;
