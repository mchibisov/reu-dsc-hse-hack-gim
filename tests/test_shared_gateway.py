import asyncio
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from gim.shared_gateway import GatewayLedger, LeaseBusy, LeaseLost

DSN = os.environ.get('TEST_DATABASE_URL', '')
LOCAL = any(host in DSN for host in ('@127.0.0.1:', '@localhost:'))
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@unittest.skipUnless(DSN and LOCAL, 'Нужна отдельная TEST_DATABASE_URL на localhost')
class GatewayIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = AsyncConnectionPool(DSN, open=False, min_size=1, max_size=3,
            kwargs={'autocommit': True, 'row_factory': dict_row, 'prepare_threshold': None,
                    'options': '-c role=gim_bot'})
        await self.pool.open()
        await self.pool.wait()
        self.group = uuid4().int % 1000000000 + 1

    async def asyncTearDown(self):
        await self.pool.close()

    async def test_singleton_checkpoint_and_event_replay(self):
        first = GatewayLedger(self.pool, self.group)
        second = GatewayLedger(self.pool, self.group)
        await first.acquire()
        self.assertIsNone(await first.cursor(self.group))
        with self.assertRaises(LeaseBusy):
            await second.acquire()
        event = {'group_id': self.group, 'type': 'message_new', 'event_id': 'synthetic-1',
                 'object': {'message': {'peer_id': 123, 'from_id': 123, 'text': '/start'}}}
        await first.ingest_batch([event], self.group, '42')
        await first.ingest_batch([event], self.group, '43')
        self.assertEqual(await first.cursor(self.group), '43')
        with psycopg.connect(DSN) as c:
            count = c.execute("SELECT count(*) FROM gim.outbox_events WHERE dedupe_key=%s",
                              (f'vk-in:{self.group}:synthetic-1',)).fetchone()[0]
            self.assertEqual(count, 1)
            c.execute("UPDATE gim.gateway_checkpoints SET lease_until=now()-interval '1 second' WHERE group_id=%s", (self.group,))
        await second.acquire()
        with self.assertRaises(LeaseLost):
            await first.execute('SELECT 1')
        with self.assertRaises(LeaseLost):
            await first.ingest_batch([], self.group, 'wrong')
        self.assertEqual(await second.cursor(self.group), '43')
        self.assertFalse(await first.release())
        self.assertTrue(await second.release())

    async def test_group_mismatch_cannot_advance_cursor(self):
        ledger = GatewayLedger(self.pool, self.group)
        await ledger.acquire()
        with self.assertRaises(ValueError):
            await ledger.ingest_batch([], self.group + 1, 'bad')
        with self.assertRaises(ValueError):
            await ledger.ingest_batch([{'group_id': self.group + 1}], self.group, 'bad')
        self.assertIsNone(await ledger.cursor(self.group))
        await ledger.release()
