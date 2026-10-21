-- No persistent membership or delegation grants to the operator.
CREATE INDEX answers_event_app ON gim.answers(group_id,event_id,application_id);
CREATE INDEX answers_question_app ON gim.answers(question_id,application_id);
CREATE INDEX applications_current_question ON gim.applications(current_question_id,id);
CREATE INDEX applications_birth_answer ON gim.applications(birth_date_answer_id,id);
CREATE INDEX applications_decision_staff ON gim.applications(decision_by_staff_id);
CREATE INDEX questions_parent ON gim.dialog_questions(parent_question_id,application_id);
CREATE INDEX files_app_recruitment ON gim.files(application_id,recruitment_id);
CREATE INDEX files_evaluation_app ON gim.files(evaluation_id,application_id);
CREATE INDEX staff_added_by ON gim.staff_members(added_by_staff_id);
-- Common checksummed ledger for direct Python deploys and initial MCP deployment.
CREATE SCHEMA IF NOT EXISTS gim_meta;
REVOKE ALL ON SCHEMA gim_meta FROM PUBLIC;
CREATE TABLE IF NOT EXISTS gim_meta.migrations(name text PRIMARY KEY,sha256 text NOT NULL);
INSERT INTO gim_meta.migrations VALUES('20261021124900_database_mvp.sql','5533e2dc2c395b66d821ab1ce1d18a4b0b2a17b485be489de0cdb6cac107a20c') ON CONFLICT(name) DO NOTHING;
INSERT INTO gim_meta.migrations VALUES('20261021125509_database_contracts.sql','cc493ae39ff074d0117889b52a5efa9c650a49e53ac72d8e2d5d1febd9526b66') ON CONFLICT(name) DO NOTHING;
INSERT INTO gim_meta.migrations VALUES('20261021130235_snapshot_hardening.sql','d3fc625863f0e41e7c1c7d5f35dd16a616732822346dd8b2adf5c4d514f5fd23') ON CONFLICT(name) DO NOTHING;
