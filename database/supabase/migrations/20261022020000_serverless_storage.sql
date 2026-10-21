-- Optional Vercel adapter: durable XLSX bytes, one bounded dispatcher per group.
CREATE TABLE gim.file_contents (
 file_id uuid PRIMARY KEY REFERENCES gim.files(id),
 body bytea NOT NULL CHECK(octet_length(body)<=20971520)
);
ALTER TABLE gim.file_contents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON gim.file_contents FROM PUBLIC,gim_bot,gim_staff;
GRANT SELECT,INSERT ON gim.file_contents TO gim_worker;
CREATE POLICY worker_read ON gim.file_contents FOR SELECT TO gim_worker USING(true);
CREATE POLICY worker_insert ON gim.file_contents FOR INSERT TO gim_worker WITH CHECK(
 EXISTS(SELECT FROM gim.files f WHERE f.id=file_id AND f.kind='xlsx' AND f.status='pending'));
CREATE TABLE gim.runtime_leases (
 group_id bigint PRIMARY KEY CHECK(group_id>0),
 token uuid NOT NULL,
 expires_at timestamptz NOT NULL
);
ALTER TABLE gim.runtime_leases ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON gim.runtime_leases FROM PUBLIC,gim_bot,gim_staff;
GRANT SELECT,INSERT,UPDATE ON gim.runtime_leases TO gim_worker;
CREATE POLICY worker ON gim.runtime_leases TO gim_worker USING(true) WITH CHECK(true);
