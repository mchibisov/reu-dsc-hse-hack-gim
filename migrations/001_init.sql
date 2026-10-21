-- Initial migration for a NEW database. Existing team DB must be compared first.
CREATE TABLE IF NOT EXISTS users (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), vk_id bigint UNIQUE NOT NULL,
 role text NOT NULL DEFAULT 'candidate' CHECK(role IN ('candidate','curator','admin')),
 name text, email text, active boolean NOT NULL DEFAULT true,
 notify_new_applications boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS applications (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES users,
 group_id bigint NOT NULL, campaign text NOT NULL,
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted','evaluated')),
 revision int NOT NULL DEFAULT 0, state jsonb NOT NULL DEFAULT '{}',
 profile jsonb NOT NULL DEFAULT '{}', questionnaire jsonb NOT NULL DEFAULT '{}',
 selected_directions text[] NOT NULL DEFAULT '{}', consent_at timestamptz,
 submitted_at timestamptz, UNIQUE(user_id,group_id,campaign)
);
CREATE TABLE IF NOT EXISTS inbox_events (
 group_id bigint NOT NULL, event_id text NOT NULL,
 application_id uuid REFERENCES applications, received_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(group_id,event_id)
);
CREATE TABLE IF NOT EXISTS answers (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id uuid NOT NULL REFERENCES applications,
 question_code text NOT NULL, question_kind text NOT NULL, question_text text NOT NULL,
 answer_text text NOT NULL, revision int NOT NULL, group_id bigint NOT NULL, event_id text NOT NULL,
 FOREIGN KEY(group_id,event_id) REFERENCES inbox_events(group_id,event_id),
 UNIQUE(application_id,revision), UNIQUE(group_id,event_id)
);
CREATE TABLE IF NOT EXISTS evaluations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id uuid NOT NULL REFERENCES applications,
 reviewer_id uuid REFERENCES users, score numeric NOT NULL CHECK(score BETWEEN 0 AND 3),
 source text NOT NULL CHECK(source IN ('model','human')), answer_revision int NOT NULL,
 rubric_version text NOT NULL, rubric_snapshot jsonb NOT NULL DEFAULT '{}',
 criteria_results jsonb NOT NULL DEFAULT '[]', summary text NOT NULL DEFAULT '',
 interview_questions jsonb NOT NULL DEFAULT '[]', recommended_directions text[] NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS files (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id uuid REFERENCES applications,
 evaluation_id uuid REFERENCES evaluations, requested_by uuid REFERENCES users,
 kind text NOT NULL, scope text, status text NOT NULL DEFAULT 'pending', campaign text,
 filters jsonb NOT NULL DEFAULT '{}', snapshot_at timestamptz, storage_key text,
 mime_type text, size_bytes bigint
);
CREATE TABLE IF NOT EXISTS jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), application_id uuid REFERENCES applications,
 sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
 file_id uuid REFERENCES files, recipient_id uuid REFERENCES users,
 dedupe_key text UNIQUE NOT NULL,
 vk_random_id bigint UNIQUE NOT NULL DEFAULT (1 + floor(random()*2147483646))::bigint,
 kind text NOT NULL, status text NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','running','done','failed')),
 payload jsonb NOT NULL DEFAULT '{}', attempts int NOT NULL DEFAULT 0,
 max_attempts int NOT NULL DEFAULT 5, available_at timestamptz NOT NULL DEFAULT now(),
 lease_until timestamptz, lease_token uuid, last_error text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_log (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, application_id uuid REFERENCES applications,
 actor_id uuid REFERENCES users, action text NOT NULL, details jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(status,available_at,created_at);
CREATE INDEX IF NOT EXISTS jobs_stream_order ON jobs((payload->>'serial_key'),sequence);
CREATE INDEX IF NOT EXISTS answers_application ON answers(application_id,revision);
CREATE INDEX IF NOT EXISTS evaluations_latest ON evaluations(application_id,created_at DESC);
