-- Pin a new scorer only for new unanswered applications. Old rubrics/results stay intact.
ALTER TABLE gim.applications ADD COLUMN analysis_rubric jsonb;
ALTER TABLE gim.applications ADD COLUMN analysis_rubric_version text;
ALTER TABLE gim.applications ADD CHECK ((analysis_rubric IS NULL)=(analysis_rubric_version IS NULL));
CREATE FUNCTION gim.freeze_application_rubric() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF (NEW.analysis_rubric,NEW.analysis_rubric_version) IS DISTINCT FROM (OLD.analysis_rubric,OLD.analysis_rubric_version)
 AND (OLD.analysis_rubric IS NOT NULL OR OLD.answers_revision<>0 OR OLD.status<>'draft')
 THEN RAISE EXCEPTION 'application rubric frozen'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER freeze_application_rubric BEFORE UPDATE ON gim.applications FOR EACH ROW EXECUTE FUNCTION gim.freeze_application_rubric();
REVOKE ALL ON FUNCTION gim.freeze_application_rubric() FROM PUBLIC;
CREATE OR REPLACE FUNCTION gim.check_evaluation() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
DECLARE a gim.applications; r gim.recruitments; cr jsonb; ev jsonb; rule jsonb; body text; f gim.files; valid_staff boolean;
BEGIN
 SELECT * INTO STRICT a FROM gim.applications WHERE id=NEW.application_id FOR SHARE;
 SELECT * INTO STRICT r FROM gim.recruitments WHERE id=a.recruitment_id;
 IF a.archived THEN RAISE EXCEPTION 'archived test attempt'; END IF;
 IF NEW.answers_revision>a.answers_revision OR NEW.rubric_version<>COALESCE(a.analysis_rubric_version,r.rubric_version) OR NEW.rubric_snapshot<>COALESCE(a.analysis_rubric,r.rubric)
 OR NEW.input_snapshot<>gim.snapshot(a.id,NEW.answers_revision) THEN RAISE EXCEPTION 'invalid evaluation snapshot'; END IF;
 IF NEW.source='curator' THEN
  IF current_user IN ('gim_worker','gim_bot') THEN RAISE EXCEPTION 'worker cannot impersonate curator' USING ERRCODE='42501'; END IF;
  SELECT true INTO valid_staff FROM gim.staff_members WHERE id=NEW.reviewer_staff_id AND group_id=r.group_id AND active FOR SHARE;
  IF valid_staff IS DISTINCT FROM true THEN RAISE EXCEPTION 'inactive/wrong staff' USING ERRCODE='42501'; END IF;
 END IF;
 IF NEW.source_event_id IS NOT NULL AND NOT EXISTS(SELECT FROM gim.outbox_events WHERE id=NEW.source_event_id AND application_id=a.id AND topic='application.analyze'
 AND (payload->>'revision')::int=NEW.answers_revision) THEN RAISE EXCEPTION 'wrong source event'; END IF;
 IF jsonb_array_length(NEW.criteria_results)<>jsonb_array_length(COALESCE(a.analysis_rubric,r.rubric)->'criteria') OR
 (SELECT count(DISTINCT x->>'code') FROM jsonb_array_elements(NEW.criteria_results) x)<>jsonb_array_length(NEW.criteria_results)
 THEN RAISE EXCEPTION 'criterion set mismatch'; END IF;
 FOR cr IN SELECT * FROM jsonb_array_elements(NEW.criteria_results) LOOP
  SELECT x INTO rule FROM jsonb_array_elements(COALESCE(a.analysis_rubric,r.rubric)->'criteria') x WHERE x->>'code'=cr->>'code';
  IF rule IS NULL OR NOT (cr ?& ARRAY['points','reason','evidence']) OR jsonb_typeof(cr->'points')<>'number'
   OR (cr->>'points')::numeric<0 OR (cr->>'points')::numeric>(rule->>'max_points')::numeric OR jsonb_typeof(cr->'evidence')<>'array'
   OR (jsonb_array_length(cr->'evidence')=0 AND COALESCE((cr->>'needs_review')::boolean,false)=false)
  THEN RAISE EXCEPTION 'invalid criterion result'; END IF;
  FOR ev IN SELECT * FROM jsonb_array_elements(cr->'evidence') LOOP
   body:=NULL;
   IF ev->>'source_type'='answer' AND NEW.input_snapshot->'answer_ids' ? (ev->>'source_id') THEN
    SELECT answer_text INTO body FROM gim.answers WHERE id=(ev->>'source_id')::uuid AND application_id=a.id AND revision<=NEW.answers_revision;
   ELSIF ev->>'source_type'='file' THEN
    SELECT * INTO f FROM gim.files WHERE id=(ev->>'source_id')::uuid AND application_id=a.id;
    IF EXISTS(SELECT FROM jsonb_array_elements(NEW.input_snapshot->'files') x WHERE x->>'id'=f.id::text AND x->>'sha256'=f.sha256) THEN body:=f.extracted_text; END IF;
   END IF;
   IF body IS NULL OR COALESCE(ev->>'quote','')='' OR strpos(body,ev->>'quote')=0 THEN RAISE EXCEPTION 'unverifiable evidence'; END IF;
  END LOOP;
 END LOOP;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION gim.curator_evaluation(p_vk bigint,p_app uuid,p_revision integer,p_score smallint,p_criteria jsonb,p_summary text,p_directions text[],p_interview jsonb,p_key text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE a gim.applications; r gim.recruitments; sid uuid; eid uuid;
BEGIN
 SELECT * INTO STRICT a FROM gim.applications WHERE id=p_app FOR UPDATE;
 SELECT * INTO STRICT r FROM gim.recruitments WHERE id=a.recruitment_id;
 sid:=gim.require_staff(p_vk,r.group_id);
 IF p_revision<>a.answers_revision THEN RAISE EXCEPTION 'stale curator snapshot'; END IF;
 IF jsonb_array_length(p_criteria)=0 THEN
 SELECT jsonb_agg(jsonb_build_object('code',x->>'code','points',0,'reason',p_summary,'needs_review',true,'evidence','[]'::jsonb)) INTO p_criteria FROM jsonb_array_elements(COALESCE(a.analysis_rubric,r.rubric)->'criteria') x;
 END IF;
 INSERT INTO gim.evaluations(application_id,answers_revision,source,reviewer_staff_id,score,rubric_version,rubric_snapshot,criteria_results,input_snapshot,summary,recommended_directions,interview_questions,request_key)
 VALUES(p_app,p_revision,'curator',sid,p_score,COALESCE(a.analysis_rubric_version,r.rubric_version),COALESCE(a.analysis_rubric,r.rubric),p_criteria,gim.snapshot(p_app,p_revision),p_summary,p_directions,p_interview,p_key)
 ON CONFLICT(application_id,source,request_key) DO NOTHING RETURNING id INTO eid;
 IF eid IS NULL THEN SELECT id INTO eid FROM gim.evaluations WHERE application_id=p_app AND source='curator' AND request_key=p_key; ELSE
 INSERT INTO gim.audit_log(application_id,actor_staff_id,action,details) VALUES(p_app,sid,'evaluation.curator',jsonb_build_object('evaluation_id',eid,'revision',p_revision)); END IF;
 RETURN eid;
END $$;

GRANT UPDATE(analysis_rubric,analysis_rubric_version) ON gim.applications TO gim_bot;
