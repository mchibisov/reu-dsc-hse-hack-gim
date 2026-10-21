import asyncio
import os
import unittest
import uuid

try:
    from gim.db import Database
except ImportError:
    Database = None


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'TEST_DATABASE_URL not set')
class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(os.environ['TEST_DATABASE_URL'])
        await self.db.open()
        async with self.db.pool.connection() as c:
            await c.execute('TRUNCATE users,inbox_events,jobs CASCADE')
        self.key = str(uuid.uuid4())

    async def asyncTearDown(self):
        await self.db.close()

    async def test_duplicate_event_creates_one_job(self):
        event = {'event_id': self.key, 'group_id': 1, 'object': {'message': {'from_id': 42, 'peer_id': 42, 'text': 'Старт'}}}
        self.assertTrue(await self.db.ingest(event))
        self.assertFalse(await self.db.ingest(event))
        async with self.db.pool.connection() as c:
            result = await (await c.execute('SELECT count(*) AS n FROM jobs WHERE dedupe_key=%s', ('event:1:' + self.key,))).fetchone()
        self.assertEqual(result['n'], 1)

    async def test_expired_lease_cannot_be_acknowledged_by_old_worker(self):
        async with self.db.pool.connection() as c:
            await self.db.enqueue(c, 'test', {}, self.key)
        job = await self.db.claim(kinds=['test'])
        async with self.db.pool.connection() as c:
            await c.execute("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s", (job['id'],))
        new_job = await self.db.claim(kinds=['test'])
        self.assertEqual(new_job['id'], job['id'])
        self.assertNotEqual(new_job['lease_token'], job['lease_token'])
        self.assertFalse(await self.db.finish(job))
        self.assertTrue(await self.db.finish(new_job))

    async def test_last_crashed_attempt_becomes_failed(self):
        async with self.db.pool.connection() as c:
            job_id = await self.db.enqueue(c, 'exhaust', {}, self.key)
            await c.execute("UPDATE jobs SET status='running', attempts=max_attempts, lease_until=now()-interval '1 second' WHERE id=%s", (job_id,))
        await self.db.claim(kinds=['exhaust'])
        async with self.db.pool.connection() as c:
            row = await (await c.execute('SELECT status FROM jobs WHERE id=%s', (job_id,))).fetchone()
        self.assertEqual(row['status'], 'failed')

    async def test_outgoing_messages_keep_order_even_when_first_is_delayed(self):
        async with self.db.pool.connection() as c:
            first = await self.db.enqueue(c, 'ordered', {'serial_key': self.key}, self.key + ':1')
            second = await self.db.enqueue(c, 'ordered', {'serial_key': self.key}, self.key + ':2')
        a = await self.db.claim(kinds=['ordered'])
        self.assertEqual(a['id'], first)
        self.assertIsNone(await self.db.claim(kinds=['ordered']))
        await self.db.finish(a, 'retry')
        self.assertIsNone(await self.db.claim(kinds=['ordered']))
        async with self.db.pool.connection() as c:
            await c.execute('UPDATE jobs SET available_at=now() WHERE id=%s', (first,))
        a = await self.db.claim(kinds=['ordered'])
        await self.db.finish(a)
        b = await self.db.claim(kinds=['ordered'])
        self.assertEqual(b['id'], second)
        await self.db.finish(b)

    @unittest.skipUnless(os.environ.get('REAL_POSTGRES_TESTS'), 'requires multi-session PostgreSQL')
    async def test_parallel_workers_do_not_claim_same_job(self):
        async with self.db.pool.connection() as c:
            ids = [await self.db.enqueue(c, 'parallel', {}, self.key + str(i)) for i in range(12)]
        jobs = await asyncio.gather(*(self.db.claim(kinds=['parallel']) for _ in range(12)))
        self.assertEqual({j['id'] for j in jobs}, set(ids))
        self.assertEqual(len({j['lease_token'] for j in jobs}), 12)


if __name__ == '__main__':
    unittest.main()
