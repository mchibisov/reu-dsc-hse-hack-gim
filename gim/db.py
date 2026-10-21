import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool


class Database:
    def __init__(self, url, group_id=None):
        self.url = url
        self.group_id = group_id
        self.pool = AsyncConnectionPool(url, min_size=1, max_size=16, open=False,
                                        kwargs={'row_factory': dict_row, 'prepare_threshold': None})

    async def open(self):
        await self.pool.open()
        await self.pool.wait()

    async def close(self):
        await self.pool.close()

    async def migrate(self):
        async with self.pool.connection() as c:
            await c.execute("SELECT pg_advisory_xact_lock(hashtextextended('gim:migrations',0))")
            for migration in sorted((Path(__file__).parent.parent / 'migrations').glob('*.sql')):
                await c.execute(migration.read_text())

    async def bootstrap(self, ids):
        async with self.pool.connection() as c:
            for vk_id in ids:
                await c.execute("INSERT INTO users(vk_id,role,notify_new_applications) VALUES(%s,'admin',true) ON CONFLICT(vk_id) DO UPDATE SET role='admin'", (vk_id,))

    @asynccontextmanager
    async def gateway_guard(self, group_id):
        # Dedicated direct/session connection: closing it releases the singleton lock.
        async with await AsyncConnection.connect(self.url, autocommit=True, prepare_threshold=None) as c:
            row = await (await c.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0))', ('gateway:' + str(group_id),))).fetchone()
            if not row[0]:
                raise RuntimeError('A gateway for this community is already running')
            yield c

    async def enqueue(self, c, kind, payload, key, application_id=None, recipient_id=None, file_id=None):
        if self.group_id:
            payload = {**payload, 'group_id': self.group_id}
        row = await (await c.execute('''INSERT INTO jobs(kind,payload,dedupe_key,application_id,recipient_id,file_id)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(dedupe_key) DO NOTHING RETURNING id''',
            (kind, Jsonb(payload), key, application_id, recipient_id, file_id))).fetchone()
        return row['id'] if row else None

    async def ingest(self, event):
        async with self.pool.connection() as c:
            return await self._ingest(c, event)

    async def _ingest(self, c, event):
            # This transaction commits before the gateway advances Long Poll ts.
            row = await (await c.execute('''INSERT INTO inbox_events(group_id,event_id) VALUES(%s,%s)
                ON CONFLICT DO NOTHING RETURNING event_id''', (event['group_id'], event['event_id']))).fetchone()
            if not row:
                return False
            event = dict(event)
            event['serial_key'] = f"{event['group_id']}:{event['object']['message']['peer_id']}"
            await self.enqueue(c, 'dialog', event, f"event:{event['group_id']}:{event['event_id']}")
            return True

    async def cursor(self, group_id):
        async with self.pool.connection() as c:
            row = await (await c.execute("SELECT details->>'ts' ts FROM audit_log WHERE action='longpoll_checkpoint' AND details->>'group_id'=%s", (str(group_id),))).fetchone()
            return row['ts'] if row else None

    async def ingest_batch(self, events, group_id, ts):
        async with self.pool.connection() as c:
            await c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('cursor:' + str(group_id),))
            for event in events:
                await self._ingest(c, event)
            existing = await (await c.execute("SELECT id FROM audit_log WHERE action='longpoll_checkpoint' AND details->>'group_id'=%s FOR UPDATE", (str(group_id),))).fetchone()
            details = Jsonb({'group_id': str(group_id), 'ts': str(ts)})
            if existing:
                await c.execute('UPDATE audit_log SET details=%s,created_at=now() WHERE id=%s', (details, existing['id']))
            else:
                await c.execute("INSERT INTO audit_log(action,details) VALUES('longpoll_checkpoint',%s)", (details,))

    async def claim(self, kinds=None, group_id=None):
        token = uuid.uuid4()
        async with self.pool.connection() as c:
            await c.execute("""WITH exhausted AS (SELECT id FROM jobs
                WHERE status='running' AND lease_until<now() AND attempts>=max_attempts FOR UPDATE SKIP LOCKED)
                UPDATE jobs SET status='failed',last_error='lease expired after final attempt'
                FROM exhausted WHERE jobs.id=exhausted.id""")
            row = await (await c.execute('''WITH ready AS (
                SELECT j.id FROM jobs j
                WHERE ((j.status='pending' AND j.available_at<=now()) OR
                       (j.status='running' AND j.lease_until<now()))
                  AND j.attempts<j.max_attempts AND (%s::text[] IS NULL OR j.kind=ANY(%s))
                  AND (%s::bigint IS NULL OR j.payload->>'group_id'=%s)
                  AND (j.payload->>'serial_key' IS NULL OR NOT EXISTS (
                    SELECT 1 FROM jobs older WHERE older.payload->>'serial_key'=j.payload->>'serial_key'
                      AND older.status IN ('pending','running')
                      AND older.sequence<j.sequence))
                ORDER BY j.sequence FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE jobs SET status='running', attempts=attempts+1,
                lease_until=now()+interval '90 seconds', lease_token=%s
              FROM ready WHERE jobs.id=ready.id RETURNING jobs.*''', (kinds, kinds, group_id, str(group_id) if group_id else None, token))).fetchone()
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
