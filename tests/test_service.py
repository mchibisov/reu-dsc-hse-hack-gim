import os
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from gim.db import Database
from gim.service import Service


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'TEST_DATABASE_URL not set')
class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(os.environ['TEST_DATABASE_URL'])
        await self.db.open()
        async with self.db.pool.connection() as c:
            await c.execute('TRUNCATE users,inbox_events,jobs CASCADE')
        self.group = uuid.uuid4().int % 100000000
        self.vk_id = uuid.uuid4().int % 100000000 + 100000000
        self.settings = SimpleNamespace(group_id=self.group, campaign='test', consent_text='Тестовое согласие',
                                        storage_dir=tempfile.mkdtemp(prefix='gim-test-'), scoring_url='', scoring_token='')
        self.vk = SimpleNamespace(send=AsyncMock(), upload=AsyncMock(return_value='doc1_2'))
        self.s = Service(self.db, self.vk, self.settings)

    async def asyncTearDown(self):
        await self.db.close()

    async def process(self, text):
        event = {'type': 'message_new', 'group_id': self.group, 'event_id': str(uuid.uuid4()),
                 'object': {'message': {'from_id': self.vk_id, 'peer_id': self.vk_id, 'text': text}}}
        await self.db.ingest(event)
        # Claim only this test's earliest dialog through ordinary queue semantics.
        job = await self.db.claim(kinds=['dialog'])
        self.assertIsNotNone(job)
        await self.s.dialog(job)
        return job

    async def test_answers_and_submission_survive_new_service_instance(self):
        for text in ['Старт', 'Согласен', 'Иван', 'История', 'Архив', 'Нет', '3', 'Помогать',
                     '5 часов', 'Книги', 'Аккуратность', 'VK', 'Каталогизировал', 'Медиа']:
            await self.process(text)
            self.s = Service(self.db, self.vk, self.settings)
        async with self.db.pool.connection() as c:
            row = await (await c.execute('SELECT a.* FROM applications a JOIN users u ON u.id=a.user_id WHERE u.vk_id=%s', (self.vk_id,))).fetchone()
            count = await (await c.execute('SELECT count(*) n FROM answers WHERE application_id=%s', (row['id'],))).fetchone()
        self.assertEqual(row['status'], 'submitted')
        self.assertEqual(count['n'], 12)
        self.assertIsNotNone(row['consent_at'])

    async def test_staff_reply_carries_permission_guard(self):
        async with self.db.pool.connection() as c:
            await c.execute("INSERT INTO users(vk_id,role) VALUES(%s,'curator')", (self.vk_id,))
        job = await self.process('/top')
        async with self.db.pool.connection() as c:
            reply = await (await c.execute("SELECT * FROM jobs WHERE dedupe_key=%s", (str(job['id']) + ':reply:0',))).fetchone()
        self.assertIsNotNone(reply['recipient_id'])

    async def test_revoked_staff_cannot_receive_export(self):
        async with self.db.pool.connection() as c:
            user = await (await c.execute("INSERT INTO users(vk_id,role) VALUES(%s,'curator') RETURNING *", (self.vk_id,))).fetchone()
            jid = await self.db.enqueue(c, 'send', {'peer_id': self.vk_id, 'text': 'private'}, str(uuid.uuid4()), recipient_id=user['id'])
            await c.execute('UPDATE users SET active=false WHERE id=%s', (user['id'],))
            job = await (await c.execute('SELECT * FROM jobs WHERE id=%s', (jid,))).fetchone()
        await self.s.handle(job)
        self.vk.send.assert_not_awaited()

    async def test_stale_export_cannot_publish_file(self):
        async with self.db.pool.connection() as c:
            user = await (await c.execute("INSERT INTO users(vk_id,role) VALUES(%s,'curator') RETURNING *", (self.vk_id,))).fetchone()
            jid = await self.db.enqueue(c, 'export', {'peer_id': self.vk_id}, str(uuid.uuid4()), recipient_id=user['id'])
            job = await (await c.execute('SELECT * FROM jobs WHERE id=%s', (jid,))).fetchone()
        # Pending job has never been leased: simulates a handler with a stale token.
        job['lease_token'] = uuid.uuid4()
        await self.s.export(job)
        async with self.db.pool.connection() as c:
            file = await (await c.execute('SELECT id FROM files WHERE id=%s', (jid,))).fetchone()
        self.assertIsNone(file)
