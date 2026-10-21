-- Private application schema. No Data API / browser access.
CREATE SCHEMA gim;
REVOKE ALL ON SCHEMA gim FROM PUBLIC;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='gim_bot') THEN CREATE ROLE gim_bot NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='gim_worker') THEN CREATE ROLE gim_worker NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='gim_staff') THEN CREATE ROLE gim_staff NOLOGIN; END IF;
END $$;
ALTER DEFAULT PRIVILEGES IN SCHEMA gim REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA gim REVOKE ALL ON TABLES FROM PUBLIC;

CREATE TABLE gim.users (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), vk_id bigint UNIQUE NOT NULL CHECK(vk_id>0),
 full_name text, email text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE gim.staff_members (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES gim.users,
 group_id bigint NOT NULL CHECK(group_id>0), role text NOT NULL CHECK(role IN ('curator','admin')),
 active boolean NOT NULL DEFAULT true, notify_new_applications boolean NOT NULL DEFAULT true,
 added_by_staff_id uuid REFERENCES gim.staff_members, revoked_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(user_id,group_id),
 CHECK(active=(revoked_at IS NULL))
);
CREATE INDEX staff_group_active ON gim.staff_members(group_id) WHERE active;
CREATE TABLE gim.recruitments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), group_id bigint NOT NULL CHECK(group_id>0), title text NOT NULL,
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','closed')),
 questionnaire_version text NOT NULL, rubric_version text NOT NULL,
 rubric jsonb NOT NULL CHECK(jsonb_typeof(rubric)='object' AND rubric ? 'criteria'),
 direction_info jsonb NOT NULL DEFAULT '{}', followup_policy jsonb NOT NULL DEFAULT '{"max_followups":5}',
 created_at timestamptz NOT NULL DEFAULT now(), opened_at timestamptz, closed_at timestamptz
);
CREATE INDEX recruitments_group ON gim.recruitments(group_id);
CREATE TABLE gim.question_templates (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), recruitment_id uuid NOT NULL REFERENCES gim.recruitments,
 code text NOT NULL, kind text NOT NULL CHECK(kind IN ('base','followup')),
 text text NOT NULL CHECK(length(btrim(text))>0), position integer NOT NULL CHECK(position>0),
 required boolean NOT NULL DEFAULT false, target_slot text NOT NULL,
 directions text[] NOT NULL DEFAULT '{}', validation jsonb NOT NULL DEFAULT '{}',
 UNIQUE(recruitment_id,code), UNIQUE(id,recruitment_id), CHECK(NOT required OR kind='base'),
 CHECK(directions <@ ARRAY['organizational','project','collections','inclusive','media']::text[])
);
CREATE TABLE gim.applications (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES gim.users,
 recruitment_id uuid NOT NULL REFERENCES gim.recruitments,
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted','withdrawn')),
 answers_revision integer NOT NULL DEFAULT 0 CHECK(answers_revision>=0), current_question_id uuid,
 profile jsonb NOT NULL DEFAULT '{}', selected_directions text[] NOT NULL DEFAULT '{}', undecided boolean NOT NULL DEFAULT false,
 birth_date date, birth_date_raw text, birth_date_answer_id uuid,
 consent_version text, consent_at timestamptz,
 decision text NOT NULL DEFAULT 'pending' CHECK(decision IN ('pending','invited','accepted','rejected')),
 decision_by_staff_id uuid REFERENCES gim.staff_members, decision_at timestamptz,
 submitted_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(user_id,recruitment_id), UNIQUE(id,recruitment_id),
 CHECK(selected_directions <@ ARRAY['organizational','project','collections','inclusive','media']::text[]),
 CHECK(NOT undecided OR cardinality(selected_directions)=0),
 CHECK((consent_version IS NULL)=(consent_at IS NULL)),
 CHECK((decision='pending' AND decision_by_staff_id IS NULL AND decision_at IS NULL) OR
       (decision<>'pending' AND decision_by_staff_id IS NOT NULL AND decision_at IS NOT NULL))
);
CREATE INDEX applications_recruitment ON gim.applications(recruitment_id,status);
CREATE TABLE gim.dialog_questions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id uuid NOT NULL REFERENCES gim.applications,
 template_id uuid REFERENCES gim.question_templates, source text NOT NULL CHECK(source IN ('base','template','generated')),
 purpose text NOT NULL DEFAULT 'collect' CHECK(purpose IN ('collect','clarify','expectations')),
 text text NOT NULL CHECK(length(btrim(text))>0), target_slot text NOT NULL,
 position integer NOT NULL CHECK(position>0), status text NOT NULL DEFAULT 'active' CHECK(status IN ('planned','active','answered','skipped')),
 based_on_revision integer NOT NULL CHECK(based_on_revision>=0), context jsonb NOT NULL DEFAULT '{}',
 request_key text NOT NULL, parent_question_id uuid, asked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(application_id,position), UNIQUE(application_id,request_key), UNIQUE(id,application_id),
 FOREIGN KEY(parent_question_id,application_id) REFERENCES gim.dialog_questions(id,application_id),
 CHECK((source='generated' AND template_id IS NULL) OR (source<>'generated' AND template_id IS NOT NULL))
);
CREATE UNIQUE INDEX one_active_question ON gim.dialog_questions(application_id) WHERE status='active';
CREATE INDEX questions_template ON gim.dialog_questions(template_id);
ALTER TABLE gim.applications ADD CONSTRAINT application_current_question_fk
 FOREIGN KEY(current_question_id,id) REFERENCES gim.dialog_questions(id,application_id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE gim.inbox_events (
 group_id bigint NOT NULL, event_id text NOT NULL, application_id uuid NOT NULL REFERENCES gim.applications,
 fingerprint text NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(group_id,event_id), UNIQUE(group_id,event_id,application_id)
);
CREATE INDEX inbox_application ON gim.inbox_events(application_id);
CREATE TABLE gim.answers (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id uuid NOT NULL REFERENCES gim.applications,
 question_id uuid NOT NULL, revision integer NOT NULL CHECK(revision>0),
 answer_text text NOT NULL CHECK(length(btrim(answer_text))>0), value jsonb NOT NULL DEFAULT 'null',
 group_id bigint NOT NULL, event_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(application_id,revision), UNIQUE(group_id,event_id), UNIQUE(id,application_id),
 FOREIGN KEY(question_id,application_id) REFERENCES gim.dialog_questions(id,application_id),
 FOREIGN KEY(group_id,event_id,application_id) REFERENCES gim.inbox_events(group_id,event_id,application_id)
);
CREATE INDEX answers_question_revision ON gim.answers(question_id,revision DESC);
ALTER TABLE gim.applications ADD FOREIGN KEY(birth_date_answer_id,id) REFERENCES gim.answers(id,application_id);
CREATE TABLE gim.evaluations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id uuid NOT NULL REFERENCES gim.applications,
 answers_revision integer NOT NULL CHECK(answers_revision>=0),
 source text NOT NULL CHECK(source IN ('algorithm','curator')),
 reviewer_staff_id uuid REFERENCES gim.staff_members, score smallint NOT NULL CHECK(score BETWEEN 0 AND 3),
 rubric_version text NOT NULL, rubric_snapshot jsonb NOT NULL,
 criteria_results jsonb NOT NULL CHECK(jsonb_typeof(criteria_results)='array'),
 input_snapshot jsonb NOT NULL, summary text NOT NULL,
 recommended_directions text[] NOT NULL DEFAULT '{}', interview_questions jsonb NOT NULL DEFAULT '[]',
 model text, prompt_version text, request_key text NOT NULL, source_event_id uuid,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(application_id,source,request_key), UNIQUE(id,application_id),
 CHECK((source='curator')=(reviewer_staff_id IS NOT NULL)),
 CHECK(recommended_directions <@ ARRAY['organizational','project','collections','inclusive','media']::text[])
);
CREATE INDEX evaluations_effective ON gim.evaluations(application_id,answers_revision DESC,source,created_at DESC);
CREATE INDEX evaluations_reviewer ON gim.evaluations(reviewer_staff_id);
CREATE TABLE gim.files (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id uuid REFERENCES gim.applications,
 evaluation_id uuid, requested_by_staff_id uuid REFERENCES gim.staff_members,
 recruitment_id uuid NOT NULL REFERENCES gim.recruitments,
 kind text NOT NULL CHECK(kind IN ('resume','profile_pdf','xlsx')), scope text NOT NULL CHECK(scope IN ('candidate','cohort')),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','ready','failed')),
 version integer NOT NULL CHECK(version>0), answers_revision integer,
 filters jsonb NOT NULL DEFAULT '{}', snapshot_at timestamptz NOT NULL DEFAULT now(),
 storage_key text NOT NULL UNIQUE, mime_type text NOT NULL, size_bytes bigint CHECK(size_bytes>=0),
 sha256 text CHECK(sha256 ~ '^[a-f0-9]{64}$'), extracted_text text, extraction_version text,
 ready_revision integer, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(id,application_id),
 FOREIGN KEY(application_id,recruitment_id) REFERENCES gim.applications(id,recruitment_id),
 FOREIGN KEY(evaluation_id,application_id) REFERENCES gim.evaluations(id,application_id),
 CHECK((scope='candidate' AND application_id IS NOT NULL) OR
       (scope='cohort' AND application_id IS NULL AND kind='xlsx' AND evaluation_id IS NULL)),
 CHECK(kind<>'profile_pdf' OR evaluation_id IS NOT NULL),
 CHECK(kind<>'resume' OR (scope='candidate' AND evaluation_id IS NULL)),
 CHECK(status<>'ready' OR (sha256 IS NOT NULL AND size_bytes IS NOT NULL)),
 CHECK(extracted_text IS NULL OR (kind='resume' AND extraction_version IS NOT NULL))
);
CREATE UNIQUE INDEX candidate_file_version ON gim.files(application_id,kind,version) WHERE application_id IS NOT NULL;
CREATE UNIQUE INDEX cohort_file_version ON gim.files(recruitment_id,kind,version) WHERE application_id IS NULL;
CREATE INDEX files_evaluation ON gim.files(evaluation_id);
CREATE INDEX files_requester ON gim.files(requested_by_staff_id);
CREATE TABLE gim.outbox_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id uuid REFERENCES gim.applications, file_id uuid REFERENCES gim.files,
 recipient_staff_id uuid REFERENCES gim.staff_members, topic text NOT NULL CHECK(topic IN ('question.send','application.analyze','staff.notify','file.export')),
 payload jsonb NOT NULL DEFAULT '{}', dedupe_key text NOT NULL UNIQUE,
 vk_random_id bigint GENERATED ALWAYS AS IDENTITY UNIQUE CHECK(vk_random_id>0),
 available_at timestamptz NOT NULL DEFAULT now(), last_published_at timestamptz, completed_at timestamptz,
 publish_attempts integer NOT NULL DEFAULT 0, last_error_code text, created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE gim.evaluations ADD FOREIGN KEY(source_event_id) REFERENCES gim.outbox_events;
CREATE UNIQUE INDEX evaluations_event ON gim.evaluations(source_event_id) WHERE source_event_id IS NOT NULL;
CREATE INDEX outbox_pending ON gim.outbox_events(available_at,last_published_at) WHERE completed_at IS NULL;
CREATE INDEX outbox_application ON gim.outbox_events(application_id);
CREATE INDEX outbox_file ON gim.outbox_events(file_id);
CREATE INDEX outbox_staff ON gim.outbox_events(recipient_staff_id);
CREATE TABLE gim.audit_log (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, application_id uuid REFERENCES gim.applications,
 actor_staff_id uuid REFERENCES gim.staff_members, actor_user_id uuid REFERENCES gim.users,
 action text NOT NULL, details jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_application ON gim.audit_log(application_id,created_at);
CREATE INDEX audit_staff ON gim.audit_log(actor_staff_id);
CREATE INDEX audit_user ON gim.audit_log(actor_user_id);

CREATE FUNCTION gim.immutable() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'immutable record' USING ERRCODE='23514'; END $$;
CREATE TRIGGER immutable_answer BEFORE UPDATE OR DELETE ON gim.answers FOR EACH ROW EXECUTE FUNCTION gim.immutable();
CREATE TRIGGER immutable_evaluation BEFORE UPDATE OR DELETE ON gim.evaluations FOR EACH ROW EXECUTE FUNCTION gim.immutable();
CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON gim.audit_log FOR EACH ROW EXECUTE FUNCTION gim.immutable();
CREATE TRIGGER immutable_inbox BEFORE UPDATE OR DELETE ON gim.inbox_events FOR EACH ROW EXECUTE FUNCTION gim.immutable();

CREATE FUNCTION gim.freeze_config() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
DECLARE r gim.recruitments;
BEGIN
 IF TG_TABLE_NAME='recruitments' THEN
  IF TG_OP='DELETE' AND OLD.status<>'draft' THEN RAISE EXCEPTION 'frozen recruitment'; END IF;
  IF TG_OP='UPDATE' AND OLD.status<>'draft' AND
     (NEW.rubric,NEW.rubric_version,NEW.questionnaire_version,NEW.direction_info,NEW.followup_policy,NEW.group_id)
       IS DISTINCT FROM (OLD.rubric,OLD.rubric_version,OLD.questionnaire_version,OLD.direction_info,OLD.followup_policy,OLD.group_id)
     THEN RAISE EXCEPTION 'frozen recruitment'; END IF;
  IF TG_OP='UPDATE' AND OLD.status<>'draft' AND NEW.status='draft' THEN RAISE EXCEPTION 'cannot unfreeze'; END IF;
  IF TG_OP='UPDATE' AND OLD.status='closed' AND NEW.status<>'closed' THEN RAISE EXCEPTION 'cannot reopen'; END IF;
 ELSE
  SELECT * INTO r FROM gim.recruitments WHERE id=CASE WHEN TG_OP='DELETE' THEN OLD.recruitment_id ELSE NEW.recruitment_id END FOR SHARE;
  IF r.status<>'draft' THEN RAISE EXCEPTION 'frozen question bank'; END IF;
  IF TG_OP='UPDATE' AND NEW.recruitment_id<>OLD.recruitment_id THEN RAISE EXCEPTION 'cannot move template'; END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
END $$;
CREATE TRIGGER freeze_recruitment BEFORE UPDATE OR DELETE ON gim.recruitments FOR EACH ROW EXECUTE FUNCTION gim.freeze_config();
CREATE TRIGGER freeze_templates BEFORE INSERT OR UPDATE OR DELETE ON gim.question_templates FOR EACH ROW EXECUTE FUNCTION gim.freeze_config();

CREATE FUNCTION gim.check_question() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
DECLARE a gim.applications; t gim.question_templates;
BEGIN
 SELECT * INTO STRICT a FROM gim.applications WHERE id=NEW.application_id FOR UPDATE;
 IF TG_OP='UPDATE' THEN
  IF (NEW.application_id,NEW.text,NEW.source,NEW.template_id,NEW.target_slot,NEW.based_on_revision,NEW.context,NEW.request_key,NEW.parent_question_id,NEW.position,NEW.purpose)
   IS DISTINCT FROM (OLD.application_id,OLD.text,OLD.source,OLD.template_id,OLD.target_slot,OLD.based_on_revision,OLD.context,OLD.request_key,OLD.parent_question_id,OLD.position,OLD.purpose)
   THEN RAISE EXCEPTION 'question wording/context immutable'; END IF;
 ELSE
  IF a.status<>'draft' OR NEW.based_on_revision<>a.answers_revision THEN RAISE EXCEPTION 'stale question context'; END IF;
  IF NEW.template_id IS NOT NULL THEN
   SELECT * INTO STRICT t FROM gim.question_templates WHERE id=NEW.template_id;
   IF t.recruitment_id<>a.recruitment_id OR (NEW.source='base' AND (t.kind<>'base' OR NEW.text<>t.text)) THEN RAISE EXCEPTION 'wrong question template'; END IF;
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER check_question BEFORE INSERT OR UPDATE ON gim.dialog_questions FOR EACH ROW EXECUTE FUNCTION gim.check_question();

CREATE FUNCTION gim.check_answer() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
DECLARE a gim.applications; q gim.dialog_questions; g bigint;
BEGIN
 SELECT * INTO STRICT a FROM gim.applications WHERE id=NEW.application_id FOR UPDATE;
 SELECT * INTO STRICT q FROM gim.dialog_questions WHERE id=NEW.question_id AND application_id=a.id;
 SELECT group_id INTO g FROM gim.recruitments WHERE id=a.recruitment_id;
 IF g<>NEW.group_id OR a.status<>'draft' OR NEW.revision<>a.answers_revision+1 OR q.status NOT IN ('active','answered')
 THEN RAISE EXCEPTION 'invalid answer revision/state'; END IF;
 UPDATE gim.applications SET answers_revision=NEW.revision,updated_at=now() WHERE id=a.id;
 RETURN NEW;
END $$;
CREATE TRIGGER check_answer BEFORE INSERT ON gim.answers FOR EACH ROW EXECUTE FUNCTION gim.check_answer();

CREATE FUNCTION gim.check_file() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
DECLARE a gim.applications;
BEGIN
 IF TG_OP='UPDATE' AND OLD.status='ready' THEN RAISE EXCEPTION 'ready file immutable'; END IF;
 IF TG_OP='UPDATE' AND (NEW.id,NEW.application_id,NEW.recruitment_id,NEW.kind,NEW.version,NEW.storage_key,NEW.evaluation_id)
  IS DISTINCT FROM (OLD.id,OLD.application_id,OLD.recruitment_id,OLD.kind,OLD.version,OLD.storage_key,OLD.evaluation_id) THEN RAISE EXCEPTION 'file identity immutable'; END IF;
 IF NEW.kind='resume' AND NEW.status='ready' THEN
  SELECT * INTO STRICT a FROM gim.applications WHERE id=NEW.application_id FOR UPDATE;
  IF a.status<>'draft' THEN RAISE EXCEPTION 'resume after submission'; END IF;
  NEW.ready_revision := a.answers_revision+1;
  UPDATE gim.applications SET answers_revision=NEW.ready_revision,updated_at=now() WHERE id=a.id;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER check_file BEFORE INSERT OR UPDATE ON gim.files FOR EACH ROW EXECUTE FUNCTION gim.check_file();

CREATE FUNCTION gim.snapshot(p_app uuid,p_revision integer) RETURNS jsonb LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT jsonb_build_object('revision',p_revision,
 'answer_ids',COALESCE((SELECT jsonb_agg(x.id ORDER BY x.question_id) FROM
 (SELECT DISTINCT ON(question_id) id,question_id FROM gim.answers WHERE application_id=p_app AND revision<=p_revision ORDER BY question_id,revision DESC) x),'[]'),
 'files',COALESCE((SELECT jsonb_agg(jsonb_build_object('id',x.id,'sha256',x.sha256) ORDER BY x.id) FROM
 (SELECT DISTINCT ON(kind) id,sha256 FROM gim.files WHERE application_id=p_app AND kind='resume' AND status='ready' AND ready_revision<=p_revision ORDER BY kind,version DESC) x),'[]'))
$$;

CREATE FUNCTION gim.check_evaluation() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
DECLARE a gim.applications; r gim.recruitments; cr jsonb; ev jsonb; rule jsonb; body text; f gim.files; valid_staff boolean;
BEGIN
 SELECT * INTO STRICT a FROM gim.applications WHERE id=NEW.application_id FOR SHARE;
 SELECT * INTO STRICT r FROM gim.recruitments WHERE id=a.recruitment_id;
 IF NEW.answers_revision>a.answers_revision OR NEW.rubric_version<>r.rubric_version OR NEW.rubric_snapshot<>r.rubric
 OR NEW.input_snapshot<>gim.snapshot(a.id,NEW.answers_revision) THEN RAISE EXCEPTION 'invalid evaluation snapshot'; END IF;
 IF NEW.source='curator' THEN
  IF current_user IN ('gim_worker','gim_bot') THEN RAISE EXCEPTION 'worker cannot impersonate curator' USING ERRCODE='42501'; END IF;
  SELECT true INTO valid_staff FROM gim.staff_members WHERE id=NEW.reviewer_staff_id AND group_id=r.group_id AND active FOR SHARE;
  IF valid_staff IS DISTINCT FROM true THEN RAISE EXCEPTION 'inactive/wrong staff' USING ERRCODE='42501'; END IF;
 END IF;
 IF NEW.source_event_id IS NOT NULL AND NOT EXISTS(SELECT FROM gim.outbox_events WHERE id=NEW.source_event_id AND application_id=a.id AND topic='application.analyze'
 AND (payload->>'revision')::int=NEW.answers_revision) THEN RAISE EXCEPTION 'wrong source event'; END IF;
 IF jsonb_array_length(NEW.criteria_results)<>jsonb_array_length(r.rubric->'criteria') OR
 (SELECT count(DISTINCT x->>'code') FROM jsonb_array_elements(NEW.criteria_results) x)<>jsonb_array_length(NEW.criteria_results)
 THEN RAISE EXCEPTION 'criterion set mismatch'; END IF;
 FOR cr IN SELECT * FROM jsonb_array_elements(NEW.criteria_results) LOOP
  SELECT x INTO rule FROM jsonb_array_elements(r.rubric->'criteria') x WHERE x->>'code'=cr->>'code';
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
CREATE TRIGGER check_evaluation BEFORE INSERT ON gim.evaluations FOR EACH ROW EXECUTE FUNCTION gim.check_evaluation();

CREATE VIEW gim.effective_evaluations WITH (security_invoker=true) AS
 SELECT DISTINCT ON(application_id) * FROM gim.evaluations ORDER BY application_id,answers_revision DESC,(source='curator') DESC,created_at DESC,id DESC;

-- Trusted staff backend passes verified VK identity. Never expose these functions as a public RPC.
CREATE FUNCTION gim.require_staff(p_vk bigint,p_group bigint,p_admin boolean DEFAULT false) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE sid uuid;
BEGIN
 SELECT s.id INTO sid FROM gim.staff_members s JOIN gim.users u ON u.id=s.user_id
 WHERE u.vk_id=p_vk AND s.group_id=p_group AND s.active AND (NOT p_admin OR s.role='admin') FOR SHARE OF s;
 IF sid IS NULL THEN RAISE EXCEPTION 'staff access denied' USING ERRCODE='42501'; END IF; RETURN sid;
END $$;
CREATE FUNCTION gim.set_staff(p_vk bigint,p_group bigint,p_target_vk bigint,p_role text,p_active boolean,p_notify boolean)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE actor uuid; target uuid; sid uuid;
BEGIN
 actor:=gim.require_staff(p_vk,p_group,true);
 -- Serialize membership edits within the community, including last-admin protection.
 PERFORM pg_advisory_xact_lock(p_group);
 IF p_role NOT IN ('curator','admin') THEN RAISE EXCEPTION 'invalid role'; END IF;
 IF EXISTS(SELECT FROM gim.staff_members s JOIN gim.users u ON u.id=s.user_id WHERE u.vk_id=p_target_vk AND s.group_id=p_group AND s.active AND s.role='admin')
 AND (NOT p_active OR p_role<>'admin') AND (SELECT count(*) FROM gim.staff_members WHERE group_id=p_group AND active AND role='admin')<=1
 THEN RAISE EXCEPTION 'cannot revoke last admin'; END IF;
 INSERT INTO gim.users(vk_id) VALUES(p_target_vk) ON CONFLICT(vk_id) DO UPDATE SET vk_id=excluded.vk_id RETURNING id INTO target;
 INSERT INTO gim.staff_members(user_id,group_id,role,active,notify_new_applications,added_by_staff_id,revoked_at)
 VALUES(target,p_group,p_role,p_active,p_notify,actor,CASE WHEN NOT p_active THEN now() END)
 ON CONFLICT(user_id,group_id) DO UPDATE SET role=excluded.role,active=excluded.active,notify_new_applications=excluded.notify_new_applications,revoked_at=excluded.revoked_at RETURNING id INTO sid;
 INSERT INTO gim.audit_log(actor_staff_id,action,details) VALUES(actor,'staff.changed',jsonb_build_object('staff_id',sid,'active',p_active,'role',p_role));
 RETURN sid;
END $$;
CREATE FUNCTION gim.staff_decision(p_vk bigint,p_app uuid,p_decision text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE a gim.applications; sid uuid; g bigint;
BEGIN
 SELECT * INTO STRICT a FROM gim.applications WHERE id=p_app FOR UPDATE;
 SELECT group_id INTO g FROM gim.recruitments WHERE id=a.recruitment_id;
 sid:=gim.require_staff(p_vk,g);
 IF a.status<>'submitted' OR p_decision NOT IN ('invited','accepted','rejected') THEN RAISE EXCEPTION 'invalid decision'; END IF;
 UPDATE gim.applications SET decision=p_decision,decision_by_staff_id=sid,decision_at=now(),updated_at=now() WHERE id=p_app;
 INSERT INTO gim.audit_log(application_id,actor_staff_id,action,details) VALUES(p_app,sid,'application.decision',jsonb_build_object('decision',p_decision));
END $$;
CREATE FUNCTION gim.curator_evaluation(p_vk bigint,p_app uuid,p_revision integer,p_score smallint,p_criteria jsonb,p_summary text,p_directions text[],p_interview jsonb,p_key text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE a gim.applications; r gim.recruitments; sid uuid; eid uuid;
BEGIN
 SELECT * INTO STRICT a FROM gim.applications WHERE id=p_app FOR UPDATE;
 SELECT * INTO STRICT r FROM gim.recruitments WHERE id=a.recruitment_id;
 sid:=gim.require_staff(p_vk,r.group_id);
 IF p_revision<>a.answers_revision THEN RAISE EXCEPTION 'stale curator snapshot'; END IF;
 INSERT INTO gim.evaluations(application_id,answers_revision,source,reviewer_staff_id,score,rubric_version,rubric_snapshot,criteria_results,input_snapshot,summary,recommended_directions,interview_questions,request_key)
 VALUES(p_app,p_revision,'curator',sid,p_score,r.rubric_version,r.rubric,p_criteria,gim.snapshot(p_app,p_revision),p_summary,p_directions,p_interview,p_key)
 ON CONFLICT(application_id,source,request_key) DO NOTHING RETURNING id INTO eid;
 IF eid IS NULL THEN SELECT id INTO eid FROM gim.evaluations WHERE application_id=p_app AND source='curator' AND request_key=p_key; ELSE
 INSERT INTO gim.audit_log(application_id,actor_staff_id,action,details) VALUES(p_app,sid,'evaluation.curator',jsonb_build_object('evaluation_id',eid,'revision',p_revision)); END IF;
 RETURN eid;
END $$;

-- Defense in depth: no policies for public API identities; only trusted backend roles.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['users','staff_members','recruitments','question_templates','applications','dialog_questions','answers','evaluations','files','inbox_events','outbox_events','audit_log'] LOOP
 EXECUTE format('ALTER TABLE gim.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY backend ON gim.%I TO gim_bot,gim_worker USING(true) WITH CHECK(true)',t);
 END LOOP;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA gim FROM PUBLIC;
GRANT USAGE ON SCHEMA gim TO gim_bot,gim_worker,gim_staff;
GRANT SELECT ON ALL TABLES IN SCHEMA gim TO gim_bot,gim_worker;
-- Column grants stop the bot changing admission decisions or granting staff rights.
GRANT INSERT(vk_id,full_name,email) ON gim.users TO gim_bot;
GRANT UPDATE(full_name,email) ON gim.users TO gim_bot;
GRANT INSERT(user_id,recruitment_id) ON gim.applications TO gim_bot;
GRANT UPDATE(status,current_question_id,profile,selected_directions,undecided,birth_date,birth_date_raw,birth_date_answer_id,consent_version,consent_at,submitted_at,updated_at,answers_revision) ON gim.applications TO gim_bot;
GRANT INSERT ON gim.dialog_questions,gim.answers,gim.inbox_events,gim.outbox_events,gim.audit_log,gim.files TO gim_bot;
GRANT UPDATE(status,asked_at) ON gim.dialog_questions TO gim_bot,gim_worker;
GRANT UPDATE ON gim.outbox_events TO gim_bot,gim_worker;
GRANT INSERT ON gim.evaluations,gim.outbox_events,gim.audit_log,gim.files TO gim_worker;
GRANT UPDATE ON gim.files TO gim_worker;
GRANT UPDATE(answers_revision,updated_at) ON gim.applications TO gim_worker;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA gim TO gim_bot,gim_worker;
GRANT EXECUTE ON FUNCTION gim.snapshot(uuid,integer) TO gim_bot,gim_worker;
GRANT EXECUTE ON FUNCTION gim.set_staff(bigint,bigint,bigint,text,boolean,boolean),gim.staff_decision(bigint,uuid,text),
 gim.curator_evaluation(bigint,uuid,integer,smallint,jsonb,text,text[],jsonb,text) TO gim_staff;
