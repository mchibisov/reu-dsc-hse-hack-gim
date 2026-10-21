-- SQL is the only runtime queue; previously deployed migrations stay immutable.
ALTER TABLE gim.outbox_events
 ADD COLUMN lease_until timestamptz,
 ADD COLUMN lease_token uuid,
 ADD COLUMN attempts integer NOT NULL DEFAULT 0 CHECK(attempts >= 0),
 ADD COLUMN max_attempts integer NOT NULL DEFAULT 5 CHECK(max_attempts BETWEEN 1 AND 5),
 ADD COLUMN failed_at timestamptz,
 ADD CONSTRAINT outbox_lease_pair CHECK ((lease_until IS NULL) = (lease_token IS NULL));
ALTER TABLE gim.outbox_events DROP CONSTRAINT outbox_events_topic_check;
ALTER TABLE gim.outbox_events ADD CONSTRAINT outbox_events_topic_check
 CHECK(topic IN ('question.send','application.analyze','staff.notify','file.export','vk.incoming','vk.send'));
CREATE INDEX outbox_sql_pending ON gim.outbox_events(available_at,vk_random_id)
 WHERE completed_at IS NULL AND failed_at IS NULL;
CREATE INDEX outbox_incoming_serial ON gim.outbox_events
 ((payload->>'group_id'),(payload->>'serial_key'),vk_random_id)
 WHERE topic='vk.incoming' AND completed_at IS NULL AND failed_at IS NULL;

CREATE TABLE gim.gateway_checkpoints (
 group_id bigint PRIMARY KEY CHECK(group_id > 0),
 ts text,
 lease_token uuid,
 lease_until timestamptz,
 CHECK ((lease_until IS NULL) = (lease_token IS NULL))
);
ALTER TABLE gim.gateway_checkpoints ENABLE ROW LEVEL SECURITY;
CREATE POLICY backend ON gim.gateway_checkpoints TO gim_bot,gim_worker
 USING(true) WITH CHECK(true);
REVOKE ALL ON gim.gateway_checkpoints FROM PUBLIC,gim_staff;
GRANT SELECT,INSERT,UPDATE ON gim.gateway_checkpoints TO gim_bot,gim_worker;
