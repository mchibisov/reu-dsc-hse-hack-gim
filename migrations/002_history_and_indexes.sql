-- Historical anonymised forms have no VK ID; never invent an addressable ID.
ALTER TABLE users ALTER COLUMN vk_id DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS model_evaluation_revision
 ON evaluations(application_id,answer_revision) WHERE source='model';
CREATE INDEX IF NOT EXISTS longpoll_checkpoint_group
 ON audit_log((details->>'group_id')) WHERE action='longpoll_checkpoint';
