CREATE OR REPLACE FUNCTION gim.check_submission() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
DECLARE today date := (now() AT TIME ZONE 'Europe/Moscow')::date;
BEGIN
 IF OLD.status<>'draft' AND NEW.status<>OLD.status THEN RAISE EXCEPTION 'cannot reopen submitted/withdrawn application'; END IF;
 IF NEW.status='submitted' AND OLD.status<>'submitted' THEN
  IF OLD.status<>'draft' OR NEW.consent_at IS NULL OR NEW.consent_version IS NULL OR NEW.birth_date IS NULL
   OR NEW.birth_date>today-interval '18 years' OR NEW.birth_date<date '1900-01-01'
   OR NEW.current_question_id IS NOT NULL OR (cardinality(NEW.selected_directions)=0 AND NOT NEW.undecided)
  THEN RAISE EXCEPTION 'consent, adult date, direction choice and completed dialog required' USING ERRCODE='23514'; END IF;
  IF NOT EXISTS(SELECT FROM gim.recruitments WHERE id=NEW.recruitment_id AND status='active') THEN RAISE EXCEPTION 'recruitment closed'; END IF;
  IF EXISTS(SELECT FROM gim.files WHERE application_id=NEW.id AND kind='resume' AND status='pending') THEN RAISE EXCEPTION 'pending resume extraction'; END IF;
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

CREATE OR REPLACE FUNCTION gim.request_export(p_vk bigint,p_recruitment uuid,p_application uuid,p_kind text,p_filters jsonb,p_key text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE sid uuid; g bigint; fid uuid; eid uuid; rev integer; v integer; bundle jsonb;
BEGIN
 SELECT group_id INTO STRICT g FROM gim.recruitments WHERE id=p_recruitment;
 sid:=gim.require_staff(p_vk,g);
 PERFORM pg_advisory_xact_lock(hashtextextended(p_recruitment::text,0));
 SELECT file_id INTO fid FROM gim.outbox_events WHERE dedupe_key='export:'||sid::text||':'||p_key;
 IF fid IS NOT NULL THEN RETURN fid; END IF;
 bundle:=gim.export_bundle(p_vk,p_recruitment,p_application,p_filters);
 IF p_kind NOT IN ('xlsx','profile_pdf') OR (p_kind='profile_pdf' AND p_application IS NULL) THEN RAISE EXCEPTION 'invalid export scope'; END IF;
 IF p_application IS NOT NULL THEN
  SELECT answers_revision INTO STRICT rev FROM gim.applications WHERE id=p_application AND recruitment_id=p_recruitment;
  SELECT id INTO eid FROM gim.effective_evaluations WHERE application_id=p_application;
  IF p_kind='profile_pdf' AND NOT EXISTS(SELECT FROM gim.evaluations WHERE id=eid AND answers_revision=rev) THEN RAISE EXCEPTION 'PDF requires current evaluation'; END IF;
 END IF;
 SELECT COALESCE(max(version),0)+1 INTO v FROM gim.files WHERE recruitment_id=p_recruitment AND application_id IS NOT DISTINCT FROM p_application AND kind=p_kind;
 fid:=gen_random_uuid();
 INSERT INTO gim.files(id,application_id,evaluation_id,requested_by_staff_id,recruitment_id,kind,scope,version,answers_revision,filters,storage_key,mime_type)
 VALUES(fid,p_application,CASE WHEN p_kind='profile_pdf' THEN eid END,sid,p_recruitment,p_kind,CASE WHEN p_application IS NULL THEN 'cohort' ELSE 'candidate' END,v,rev,p_filters,
 p_recruitment::text||'/'||fid::text,CASE WHEN p_kind='xlsx' THEN 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ELSE 'application/pdf' END);
 INSERT INTO gim.outbox_events(application_id,file_id,topic,dedupe_key,payload) VALUES(p_application,fid,'file.export','export:'||sid::text||':'||p_key,jsonb_build_object('snapshot',bundle));
 INSERT INTO gim.audit_log(application_id,actor_staff_id,action,details) VALUES(p_application,sid,'export.requested',jsonb_build_object('file_id',fid));
 RETURN fid;
END $$;

-- Submission and its intentions cannot be split, even by direct SQL from the bot.
CREATE FUNCTION gim.after_submit() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE s record; g bigint;
BEGIN
 IF NEW.status='submitted' AND OLD.status<>'submitted' THEN
  INSERT INTO gim.outbox_events(application_id,topic,dedupe_key,payload)
   VALUES(NEW.id,'application.analyze','analyze:'||NEW.id::text||':'||NEW.answers_revision::text,jsonb_build_object('revision',NEW.answers_revision)) ON CONFLICT(dedupe_key) DO NOTHING;
  SELECT group_id INTO g FROM gim.recruitments WHERE id=NEW.recruitment_id;
  FOR s IN SELECT id FROM gim.staff_members WHERE group_id=g AND active AND notify_new_applications LOOP
   INSERT INTO gim.outbox_events(application_id,topic,dedupe_key,recipient_staff_id)
    VALUES(NEW.id,'staff.notify','notify:'||NEW.id::text||':'||s.id::text,s.id) ON CONFLICT(dedupe_key) DO NOTHING;
  END LOOP;
  INSERT INTO gim.audit_log(application_id,action,details) VALUES(NEW.id,'application.submitted',jsonb_build_object('revision',NEW.answers_revision));
 END IF; RETURN NEW;
END $$;
CREATE TRIGGER after_submit AFTER UPDATE OF status ON gim.applications FOR EACH ROW EXECUTE FUNCTION gim.after_submit();
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA gim FROM PUBLIC;
