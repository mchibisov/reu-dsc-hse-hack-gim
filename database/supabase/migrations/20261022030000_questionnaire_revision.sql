-- Explicit operator revision requested 2026-10-22. Apply transactionally.
-- Preserve saved questions/answers; retire only the obsolete bank entry.
LOCK TABLE gim.applications IN ACCESS EXCLUSIVE MODE;
ALTER TABLE gim.question_templates DISABLE TRIGGER freeze_templates;
UPDATE gim.question_templates
SET required=false, validation=validation || '{"retired":true,"revision":"museum-v2"}'::jsonb
WHERE kind='base' AND target_slot='university_other';
UPDATE gim.question_templates SET text='Факультет, направление'
WHERE kind='base' AND target_slot='faculty';
ALTER TABLE gim.question_templates ENABLE TRIGGER freeze_templates;

UPDATE gim.dialog_questions q SET status='skipped'
FROM gim.applications a
WHERE q.application_id=a.id AND a.status='draft' AND NOT a.archived
AND q.source='base' AND q.target_slot='university_other'
AND q.status IN ('planned','active');
UPDATE gim.applications a SET current_question_id=NULL, updated_at=now()
WHERE a.status='draft' AND NOT a.archived AND EXISTS (
 SELECT FROM gim.dialog_questions q WHERE q.id=a.current_question_id
 AND q.target_slot='university_other' AND q.status='skipped');
INSERT INTO gim.audit_log(action,details)
VALUES('questionnaire.revised','{"revision":"museum-v2","retired_slot":"university_other","faculty_label":"Факультет, направление"}');
