-- Non-destructive test attempts. Old answers/evaluations/files remain immutable.
ALTER TABLE gim.applications ADD COLUMN archived boolean NOT NULL DEFAULT false;
ALTER TABLE gim.applications ADD COLUMN attempt integer NOT NULL DEFAULT 1 CHECK(attempt>0);
ALTER TABLE gim.applications DROP CONSTRAINT applications_user_id_recruitment_id_key;
ALTER TABLE gim.applications ADD CONSTRAINT applications_attempt UNIQUE(user_id,recruitment_id,attempt);
CREATE UNIQUE INDEX applications_current ON gim.applications(user_id,recruitment_id) WHERE NOT archived;

CREATE FUNCTION gim.reset_own_application(p_vk bigint,p_recruitment uuid,p_key text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE sid uuid; uid uuid; old_app uuid; new_app uuid; g bigint; next_attempt integer;
BEGIN
 SELECT group_id INTO STRICT g FROM gim.recruitments WHERE id=p_recruitment AND status='active';
 sid:=gim.require_staff(p_vk,g,true);
 IF p_key IS NULL OR length(p_key) NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION 'invalid request'; END IF;
 SELECT id INTO STRICT uid FROM gim.users WHERE vk_id=p_vk FOR UPDATE;
 SELECT (details->>'new_application_id')::uuid INTO new_app FROM gim.audit_log
 WHERE action='application.test_reset' AND details->>'request_key'=p_key AND details->>'staff_id'=sid::text LIMIT 1;
 IF new_app IS NOT NULL THEN RETURN new_app; END IF;
 SELECT id INTO old_app FROM gim.applications WHERE user_id=uid AND recruitment_id=p_recruitment AND NOT archived FOR UPDATE;
 IF old_app IS NOT NULL THEN
  UPDATE gim.applications SET archived=true WHERE id=old_app;
  UPDATE gim.outbox_events SET completed_at=COALESCE(completed_at,now()),lease_token=NULL,lease_until=NULL,
    last_error_code='test_attempt_archived' WHERE application_id=old_app AND completed_at IS NULL AND failed_at IS NULL
    AND topic IN ('vk.incoming','vk.send','question.send','application.analyze','staff.notify');
 END IF;
 SELECT COALESCE(max(attempt),0)+1 INTO next_attempt FROM gim.applications WHERE user_id=uid AND recruitment_id=p_recruitment;
 INSERT INTO gim.applications(user_id,recruitment_id,attempt) VALUES(uid,p_recruitment,next_attempt) RETURNING id INTO new_app;
 INSERT INTO gim.audit_log(application_id,action,details) VALUES(new_app,'application.test_reset',
  jsonb_build_object('old_application_id',old_app,'new_application_id',new_app,'staff_id',sid,'request_key',p_key));
 RETURN new_app;
END $$;
REVOKE ALL ON FUNCTION gim.reset_own_application(bigint,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION gim.reset_own_application(bigint,uuid,text) TO gim_staff;

CREATE OR REPLACE FUNCTION gim.export_bundle(p_vk bigint,p_recruitment uuid,p_application uuid DEFAULT NULL,p_filters jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE g bigint; result jsonb; sid uuid;
BEGIN
 SELECT group_id INTO STRICT g FROM gim.recruitments WHERE id=p_recruitment;
 sid:=gim.require_staff(p_vk,g);
 IF p_application IS NOT NULL AND NOT EXISTS(SELECT FROM gim.applications WHERE id=p_application AND recruitment_id=p_recruitment)
  THEN RAISE EXCEPTION 'application outside recruitment'; END IF;
 IF EXISTS(SELECT FROM jsonb_object_keys(p_filters) x WHERE x NOT IN ('status','direction','decision')) THEN RAISE EXCEPTION 'unsupported export filter'; END IF;
 WITH selected AS (
  SELECT a.*,u.vk_id,u.full_name,u.email,e.id evaluation_id,e.score,e.source evaluation_source,e.reviewer_staff_id,e.summary,
   e.recommended_directions,e.interview_questions,e.criteria_results,e.answers_revision evaluation_revision,e.created_at evaluated_at,
   reviewer.full_name reviewer_name,
   (SELECT ae.score FROM gim.evaluations ae WHERE ae.application_id=a.id AND ae.source='algorithm' ORDER BY ae.answers_revision DESC,ae.created_at DESC LIMIT 1) ai_score,
   (SELECT ae.summary FROM gim.evaluations ae WHERE ae.application_id=a.id AND ae.source='algorithm' ORDER BY ae.answers_revision DESC,ae.created_at DESC LIMIT 1) ai_summary
  FROM gim.applications a JOIN gim.users u ON u.id=a.user_id
  LEFT JOIN gim.effective_evaluations e ON e.application_id=a.id
  LEFT JOIN gim.staff_members sm ON sm.id=e.reviewer_staff_id LEFT JOIN gim.users reviewer ON reviewer.id=sm.user_id
  WHERE (NOT a.archived OR p_application IS NOT NULL) AND a.recruitment_id=p_recruitment AND (p_application IS NULL OR a.id=p_application)
   AND (NOT p_filters ? 'status' OR a.status=p_filters->>'status')
   AND (NOT p_filters ? 'decision' OR a.decision=p_filters->>'decision')
   AND (NOT p_filters ? 'direction' OR p_filters->>'direction'=ANY(a.selected_directions))
 ), questionnaire AS (
  SELECT id application_id,vk_id,full_name,email,birth_date,birth_date_raw,status,decision,selected_directions,undecided,
    answers_revision,submitted_at,evaluation_id,score,evaluation_source,reviewer_staff_id,reviewer_name,summary,
    recommended_directions,criteria_results,evaluation_revision,evaluated_at,ai_score,ai_summary,
    COALESCE(evaluation_revision<answers_revision,false) evaluation_stale
  FROM selected ORDER BY score DESC NULLS LAST,submitted_at NULLS LAST,id
 ), answers AS (
  SELECT s.id application_id,q.id question_id,q.position,q.text question_text,q.source question_source,q.purpose,q.target_slot,
    a.id answer_id,a.revision,a.answer_text,a.value,a.created_at,
    a.id=(SELECT aa.id FROM gim.answers aa WHERE aa.question_id=q.id ORDER BY aa.revision DESC LIMIT 1) is_latest
  FROM selected s JOIN gim.dialog_questions q ON q.application_id=s.id LEFT JOIN gim.answers a ON a.question_id=q.id
  ORDER BY s.id,q.position,a.revision
 ), interview AS (
  SELECT id application_id,evaluation_id,summary,interview_questions,
   (SELECT COALESCE(jsonb_agg(jsonb_build_object('question',q.text,'answer',a.answer_text,'revision',a.revision) ORDER BY q.position,a.revision),'[]')
     FROM gim.dialog_questions q LEFT JOIN gim.answers a ON a.question_id=q.id WHERE q.application_id=s.id AND q.purpose='expectations') expectations
  FROM selected s ORDER BY id
 )
 SELECT jsonb_build_object('snapshot_at',transaction_timestamp(),'recruitment_id',p_recruitment,'filters',p_filters,
  'Анкеты',COALESCE((SELECT jsonb_agg(to_jsonb(q)) FROM questionnaire q),'[]'),
  'Ответы',COALESCE((SELECT jsonb_agg(to_jsonb(a)) FROM answers a),'[]'),
  'Собеседование',COALESCE((SELECT jsonb_agg(to_jsonb(i)) FROM interview i),'[]'),
  'Сводка',jsonb_build_object('total',(SELECT count(*) FROM selected),'scored',(SELECT count(score) FROM selected),
    'unscored',(SELECT count(*) FROM selected WHERE score IS NULL),'average_score',(SELECT avg(score) FROM selected),
    'score_distribution',(SELECT COALESCE(jsonb_object_agg(score,n),'{}') FROM (SELECT score,count(*) n FROM selected WHERE score IS NOT NULL GROUP BY score) x),
    'directions',(SELECT COALESCE(jsonb_object_agg(direction,n),'{}') FROM (SELECT d direction,count(*) n FROM selected,unnest(selected_directions) d GROUP BY d) x),
    'decisions',(SELECT COALESCE(jsonb_object_agg(decision,n),'{}') FROM (SELECT decision,count(*) n FROM selected GROUP BY decision) x))) INTO result;
 INSERT INTO gim.audit_log(actor_staff_id,action,details) VALUES(sid,'export.read',jsonb_build_object('recruitment_id',p_recruitment,'application_id',p_application));
 RETURN result;
END $$;

