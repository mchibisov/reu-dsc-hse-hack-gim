-- Optional cloud dispatcher. Configure gim_worker_url/key in Supabase Vault first.
CREATE EXTENSION IF NOT EXISTS pg_net;
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE OR REPLACE FUNCTION gim.wake_worker(p_group bigint) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE endpoint text; bearer text; request_id bigint;
BEGIN
 IF EXISTS(SELECT FROM gim.runtime_leases WHERE group_id=p_group AND expires_at>now()) THEN RETURN NULL; END IF;
 IF NOT EXISTS(SELECT FROM gim.outbox_events e
  LEFT JOIN gim.applications a ON a.id=e.application_id LEFT JOIN gim.recruitments r ON r.id=a.recruitment_id
  LEFT JOIN gim.files f ON f.id=e.file_id LEFT JOIN gim.recruitments fr ON fr.id=f.recruitment_id
  WHERE COALESCE(r.group_id,fr.group_id,(e.payload->>'group_id')::bigint)=p_group
  AND e.completed_at IS NULL AND e.failed_at IS NULL AND e.available_at<=now()
  AND (e.lease_until IS NULL OR e.lease_until<=now())) THEN RETURN NULL; END IF;
 SELECT decrypted_secret INTO endpoint FROM vault.decrypted_secrets WHERE name='gim_worker_url';
 SELECT decrypted_secret INTO bearer FROM vault.decrypted_secrets WHERE name='gim_worker_key';
 IF endpoint IS NULL OR bearer IS NULL OR endpoint !~ '^https://[a-z0-9-]+[.]vercel[.]app/work$' THEN
  RAISE EXCEPTION 'Cloud dispatcher is not configured'; END IF;
 SELECT net.http_post(url:=endpoint,body:='{}'::jsonb,headers:=jsonb_build_object('Content-Type','application/json','Authorization','Bearer '||bearer),timeout_milliseconds:=290000) INTO request_id;
 RETURN request_id;
END $$;
REVOKE ALL ON FUNCTION gim.wake_worker(bigint) FROM PUBLIC,anon,authenticated,gim_worker,gim_staff;
GRANT EXECUTE ON FUNCTION gim.wake_worker(bigint) TO gim_bot;
REVOKE ALL ON net.http_request_queue,net._http_response FROM PUBLIC,anon,authenticated;
-- Mandatory recovery schedule after Vault setup, replacing GROUP_ID with the configured VK group:
-- SELECT cron.schedule('gim-worker-recovery','* * * * *','SELECT gim.wake_worker(GROUP_ID)');
-- This closes callback/dispatcher exit races and retries after a killed invocation.
