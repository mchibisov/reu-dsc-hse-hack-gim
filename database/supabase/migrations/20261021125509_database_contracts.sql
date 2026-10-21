CREATE FUNCTION gim.check_submission() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
DECLARE today date := (now() AT TIME ZONE 'Europe/Moscow')::date;
BEGIN
 IF NEW.status='submitted' AND OLD.status<>'submitted' THEN
  IF OLD.status<>'draft' OR NEW.consent_at IS NULL OR NEW.consent_version IS NULL OR NEW.birth_date IS NULL
   OR NEW.birth_date>today-interval '18 years' OR NEW.birth_date<date '1900-01-01'
   OR NEW.current_question_id IS NOT NULL OR (cardinality(NEW.selected_directions)=0 AND NOT NEW.undecided)
  THEN RAISE EXCEPTION 'consent, adult date, direction choice and completed dialog required' USING ERRCODE='23514'; END IF;
  IF NOT EXISTS(SELECT FROM gim.recruitments WHERE id=NEW.recruitment_id AND status='active') THEN RAISE EXCEPTION 'recruitment closed'; END IF;
  IF EXISTS(SELECT FROM gim.question_templates t WHERE t.recruitment_id=NEW.recruitment_id AND t.required
    AND NOT EXISTS(SELECT FROM gim.dialog_questions q JOIN gim.answers a ON a.question_id=q.id
      WHERE q.application_id=NEW.id AND q.template_id=t.id AND q.source='base' AND a.application_id=NEW.id))
   THEN RAISE EXCEPTION 'required questionnaire incomplete' USING ERRCODE='23514'; END IF;
 END IF;
 IF OLD.status<>'draft' AND (NEW.user_id,NEW.recruitment_id,NEW.answers_revision,NEW.birth_date,NEW.consent_version,NEW.consent_at,NEW.profile,NEW.selected_directions,NEW.undecided)
  IS DISTINCT FROM (OLD.user_id,OLD.recruitment_id,OLD.answers_revision,OLD.birth_date,OLD.consent_version,OLD.consent_at,OLD.profile,OLD.selected_directions,OLD.undecided)
 THEN RAISE EXCEPTION 'submitted application immutable'; END IF;
 IF NEW.user_id<>OLD.user_id OR NEW.recruitment_id<>OLD.recruitment_id THEN RAISE EXCEPTION 'application identity immutable'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER check_submission BEFORE UPDATE ON gim.applications FOR EACH ROW EXECUTE FUNCTION gim.check_submission();

CREATE FUNCTION gim.export_bundle(p_vk bigint,p_recruitment uuid,p_application uuid DEFAULT NULL,p_filters jsonb DEFAULT '{}')
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
   reviewer.full_name reviewer_name
  FROM gim.applications a JOIN gim.users u ON u.id=a.user_id
  LEFT JOIN gim.effective_evaluations e ON e.application_id=a.id
  LEFT JOIN gim.staff_members sm ON sm.id=e.reviewer_staff_id LEFT JOIN gim.users reviewer ON reviewer.id=sm.user_id
  WHERE a.recruitment_id=p_recruitment AND (p_application IS NULL OR a.id=p_application)
   AND (NOT p_filters ? 'status' OR a.status=p_filters->>'status')
   AND (NOT p_filters ? 'decision' OR a.decision=p_filters->>'decision')
   AND (NOT p_filters ? 'direction' OR p_filters->>'direction'=ANY(a.selected_directions))
 ), questionnaire AS (
  SELECT id application_id,vk_id,full_name,email,birth_date,birth_date_raw,status,decision,selected_directions,undecided,
    answers_revision,submitted_at,evaluation_id,score,evaluation_source,reviewer_staff_id,reviewer_name,summary,
    recommended_directions,criteria_results,evaluation_revision,evaluated_at,
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

CREATE FUNCTION gim.request_export(p_vk bigint,p_recruitment uuid,p_application uuid,p_kind text,p_filters jsonb,p_key text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE sid uuid; g bigint; fid uuid; eid uuid; rev integer; v integer;
BEGIN
 SELECT group_id INTO STRICT g FROM gim.recruitments WHERE id=p_recruitment;
 sid:=gim.require_staff(p_vk,g);
 PERFORM pg_advisory_xact_lock(hashtextextended(p_recruitment::text,0));
 SELECT file_id INTO fid FROM gim.outbox_events WHERE dedupe_key='export:'||sid::text||':'||p_key;
 IF fid IS NOT NULL THEN RETURN fid; END IF;
 IF p_kind NOT IN ('xlsx','profile_pdf') OR (p_kind='profile_pdf' AND p_application IS NULL) THEN RAISE EXCEPTION 'invalid export scope'; END IF;
 IF p_application IS NOT NULL THEN
  SELECT answers_revision INTO STRICT rev FROM gim.applications WHERE id=p_application AND recruitment_id=p_recruitment;
  SELECT id INTO eid FROM gim.effective_evaluations WHERE application_id=p_application;
 END IF;
 SELECT COALESCE(max(version),0)+1 INTO v FROM gim.files WHERE recruitment_id=p_recruitment AND application_id IS NOT DISTINCT FROM p_application AND kind=p_kind;
 fid:=gen_random_uuid();
 INSERT INTO gim.files(id,application_id,evaluation_id,requested_by_staff_id,recruitment_id,kind,scope,version,answers_revision,filters,storage_key,mime_type)
 VALUES(fid,p_application,CASE WHEN p_kind='profile_pdf' THEN eid END,sid,p_recruitment,p_kind,CASE WHEN p_application IS NULL THEN 'cohort' ELSE 'candidate' END,v,rev,p_filters,
 p_recruitment::text||'/'||fid::text,CASE WHEN p_kind='xlsx' THEN 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ELSE 'application/pdf' END);
 INSERT INTO gim.outbox_events(application_id,file_id,topic,dedupe_key) VALUES(p_application,fid,'file.export','export:'||sid::text||':'||p_key);
 INSERT INTO gim.audit_log(application_id,actor_staff_id,action,details) VALUES(p_application,sid,'export.requested',jsonb_build_object('file_id',fid));
 RETURN fid;
END $$;
CREATE FUNCTION gim.staff_file(p_vk bigint,p_file uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE f gim.files; g bigint; sid uuid;
BEGIN
 SELECT * INTO STRICT f FROM gim.files WHERE id=p_file;
 SELECT group_id INTO STRICT g FROM gim.recruitments WHERE id=f.recruitment_id;
 sid:=gim.require_staff(p_vk,g);
 IF f.status<>'ready' THEN RAISE EXCEPTION 'file not ready'; END IF;
 INSERT INTO gim.audit_log(application_id,actor_staff_id,action,details) VALUES(f.application_id,sid,'file.access',jsonb_build_object('file_id',f.id));
 RETURN to_jsonb(f)-'extracted_text';
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA gim FROM PUBLIC;
GRANT EXECUTE ON FUNCTION gim.export_bundle(bigint,uuid,uuid,jsonb),gim.request_export(bigint,uuid,uuid,text,jsonb,text),gim.staff_file(bigint,uuid) TO gim_staff;
