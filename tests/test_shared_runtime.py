import os
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from gim.shared_config import SharedSettings
from gim.shared_storage import LocalPrivateStorage


class SettingsTests(unittest.TestCase):
    def test_missing_connections_names_are_clear_and_secret_free(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'DATABASE_BOT_URL'):
                SharedSettings.load()

    def test_runtime_rejects_operator_login(self):
        env = dict(DATABASE_BOT_URL='postgresql://postgres:secret@localhost/test',
                   DATABASE_WORKER_URL='postgresql://gim_worker_login@localhost/test',
                   DATABASE_STAFF_URL='postgresql://gim_staff_login@localhost/test',
                   VK_GROUP_ID='123', RECRUITMENT_ID='00000000-0000-0000-0000-000000000001')
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError) as error:
                SharedSettings.load()
            self.assertNotIn('secret', str(error.exception))
            self.assertIn('runtime', str(error.exception))

    def test_three_service_logins_and_bounded_concurrency(self):
        env = {f'DATABASE_{role}_URL': f'postgresql://gim_{role.lower()}_login@localhost/test'
               for role in ('BOT', 'WORKER', 'STAFF')}
        env.update(VK_GROUP_ID='123', RECRUITMENT_ID='00000000-0000-0000-0000-000000000001',
                   WORKER_CONCURRENCY='4', VK_TOKEN='synthetic')
        with patch.dict(os.environ, env, clear=True):
            settings = SharedSettings.load()
            self.assertEqual(settings.group_id, 123)
            self.assertEqual(settings.max_followups, 3)
            self.assertEqual(settings.concurrency, 4)
            self.assertNotIn('synthetic', repr(settings))
            os.environ['WORKER_CONCURRENCY'] = '0'
            with self.assertRaises(ValueError):
                SharedSettings.load()


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_objects_immutable_and_retry_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalPrivateStorage(directory)
            meta = {'storage_key': 'recruitment/file', 'status': 'pending'}
            await storage.upload(meta, b'xlsx')
            await storage.upload(meta, b'xlsx')
            self.assertEqual(await storage.read(meta), b'xlsx')
            with self.assertRaises(ValueError):
                await storage.upload(meta, b'replaced')
            with self.assertRaises(ValueError):
                await storage.upload({**meta, 'status': 'ready'}, b'xlsx')

    async def test_rejects_paths_outside_private_root(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalPrivateStorage(directory)
            for key in ('../outside', '/absolute', 'C:/outside', 'a\\..\\outside', ''):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    await storage.upload({'storage_key': key, 'status': 'pending'}, b'no')
            self.assertEqual(list(Path(directory).iterdir()), [])

    async def test_read_detects_corrupted_export(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalPrivateStorage(directory)
            meta = {'storage_key': 'file', 'status': 'pending'}
            await storage.upload(meta, b'xlsx')
            with self.assertRaises(ValueError):
                await storage.read({**meta, 'sha256': '0' * 64})


class MainTests(unittest.IsolatedAsyncioTestCase):
    async def test_sigterm_cancellation_runs_cleanup_and_unregisters_handler(self):
        import asyncio
        import signal
        from gim.shared_main import run_with_shutdown
        loop=asyncio.get_running_loop()
        with patch.object(loop,'add_signal_handler') as add, \
             patch.object(loop,'remove_signal_handler') as remove, \
             patch('gim.shared_main.run',new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await run_with_shutdown('gateway',SimpleNamespace())
        if os.name!='nt':
            self.assertEqual(add.call_args.args[0],signal.SIGTERM)
            remove.assert_called_once_with(signal.SIGTERM)

    async def test_gateway_does_not_need_a_writable_file_directory(self):
        from gim.shared_main import run
        pools = [MagicMock() for _ in range(3)]
        for pool in pools:
            pool.__aenter__ = AsyncMock(return_value=pool)
            pool.__aexit__ = AsyncMock(return_value=False)
            pool.wait = AsyncMock()
        vk = SimpleNamespace(close=AsyncMock())
        settings = SimpleNamespace(database_bot_url='bot', database_worker_url='worker', database_staff_url='staff',
                   concurrency=4, vk_token='synthetic', group_id=123, storage_dir='/unwritable/runtime')
        with patch('gim.shared_main.create_pool', side_effect=pools), \
             patch('gim.shared_main.check_database', new=AsyncMock()), \
             patch('gim.shared_main.VK', return_value=vk), \
             patch('gim.shared_main.gateway_loop', new=AsyncMock()) as gateway, \
             patch('gim.shared_main.LocalPrivateStorage', side_effect=PermissionError) as storage:
            await run('gateway', settings)
            storage.assert_not_called()
            gateway.assert_awaited_once_with(vk, pools[0], 123)
        vk.close.assert_awaited_once()
