import json
import uuid
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool


class Database:
    def __init__(self, url):
        self.pool = AsyncConnectionPool(url, min_size=1, max_size=16, open=False,
                                        kwargs={'row_factory': dict_row, 'prepare_threshold': None})

    async def open(self):
        await self.pool.open()
        await self.pool.wait()

    async def close(self):
        await self.pool.close()

    async def migrate(self):
        sql = (Path(__file__).parent.parent / 'migrations/001_init.sql').read_text()
        async with self.pool.connection() as c:
            await c.execute(sql)

    async def bootstrap(self, ids):
        async with self.pool.connection() as c:
            for vk_id in ids:
                await c.execute("INSERT INTO users(vk_id,role,notify_new_applications) VALUES(%s,'admin',true) ON CONFLICT(vk_id) DO NOTHING", (vk_id,))

    async def enqueue(self, c, kind, payload, key, application_id=None, recipient_id=None, file_id=None):
        row = await (await c.execute('''INSERT INTO jobs(kind,payload,dedupe_key,application_id,recipient_id,file_id)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(dedupe_key) DO NOTHING RETURNING id''',
            (kind, Jsonb(payload), key, application_id, recipient_id, file_id))).fetchone()
        return row['id'] if row else None

    async def ingest(self, event):
        async with self.pool.connection() as c:
            # This transaction commits before the gateway advances Long Poll ts.
            row = await (await c.execute('''INSERT INTO inbox_events(group_id,event_id) VALUES(%s,%s)
                ON CONFLICT DO NOTHING RETURNING event_id''', (event['group_id'], event['event_id']))).fetchone()
            if not row:
                return False
            event = dict(event)
            event['serial_key'] = f"{event['group_id']}:{event['object']['message']['peer_id']}"
            await self.enqueue(c, 'dialog', event, f"event:{event['group_id']}:{event['event_id']}")
            return True

    async def claim(self, kinds=None):
        token = uuid.uuid4()
        async with self.pool.connection() as c:
            await c.execute("""UPDATE jobs SET status='failed',last_error='lease expired after final attempt'
                WHERE status='running' AND lease_until<now() AND attempts>=max_attempts""")
            row = await (await c.execute('''WITH ready AS (
                SELECT j.id FROM jobs j
                WHERE ((j.status='pending' AND j.available_at<=now()) OR
                       (j.status='running' AND j.lease_until<now()))
                  AND j.attempts<j.max_attempts AND (%s::text[] IS NULL OR j.kind=ANY(%s))
                  AND (j.payload->>'serial_key' IS NULL OR NOT EXISTS (
                    SELECT 1 FROM jobs older WHERE older.payload->>'serial_key'=j.payload->>'serial_key'
                      AND older.status IN ('pending','running')
                      AND older.sequence<j.sequence))
                ORDER BY j.sequence FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE jobs SET status='running', attempts=attempts+1,
                lease_until=now()+interval '90 seconds', lease_token=%s
              FROM ready WHERE jobs.id=ready.id RETURNING jobs.*''', (kinds, kinds, token))).fetchone()
            return row

    async def finish(self, job, error=None):
        async with self.pool.connection() as c:
            if error:
                row = await (await c.execute('''UPDATE jobs SET
                    status=CASE WHEN attempts>=max_attempts THEN 'failed' ELSE 'pending' END,
                    available_at=now()+ make_interval(secs=>LEAST(300,power(2,attempts)::int)),
                    last_error=%s,lease_until=NULL,lease_token=NULL
                    WHERE id=%s AND lease_token=%s AND status='running' RETURNING id''',
                    (error[:300], job['id'], job['lease_token']))).fetchone()
            else:
                row = await (await c.execute("UPDATE jobs SET status='done',lease_until=NULL WHERE id=%s AND lease_token=%s AND status='running' RETURNING id", (job['id'], job['lease_token']))).fetchone()
            return bool(row)

    async def renew(self, job):
        async with self.pool.connection() as c:
            row = await (await c.execute("UPDATE jobs SET lease_until=now()+interval '90 seconds' WHERE id=%s AND lease_token=%s AND status='running' RETURNING id", (job['id'], job['lease_token']))).fetchone()
            return bool(row)
