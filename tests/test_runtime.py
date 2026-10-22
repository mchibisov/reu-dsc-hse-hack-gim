import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from gim.config import Settings
from gim.vk import VK


class EnvironmentTests(unittest.TestCase):
    def test_dotenv_loads_without_overriding_deployment_environment(self):
        from gim.config import load_dotenv
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text('VK_GROUP_ID=242476311\nVK_TOKEN="local-token"\n# comment\nCONSENT_TEXT=Тест\\nВторая строка\n', encoding='utf-8')
            with patch.dict(os.environ, {'VK_GROUP_ID': '999'}, clear=True):
                load_dotenv(path)
                self.assertEqual(os.environ['VK_GROUP_ID'], '999')
                self.assertEqual(os.environ['VK_TOKEN'], 'local-token')
                self.assertEqual(os.environ['CONSENT_TEXT'], 'Тест\nВторая строка')

    def test_concurrency_must_be_bounded(self):
        for value in ('0', '-1', '1000'):
            with self.subTest(value=value), patch.dict(os.environ, {'DATABASE_URL': 'postgresql://localhost/test', 'WORKER_CONCURRENCY': value}, clear=True):
                with self.assertRaises(ValueError):
                    Settings.load()


class VKRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_keyboard_is_role_aware_and_random_id_stable(self):
        seen = []
        async def handler(request):
            from urllib.parse import parse_qs
            seen.append(parse_qs(request.content.decode()))
            return httpx.Response(200, json={'response': 1})
        vk = VK(SimpleNamespace(vk_token='secret', api_version='5.199'))
        await vk.http.aclose()
        vk.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await vk.send(12, 'Привет', 42, role='curator')
            await vk.send(12, 'Привет', 42, role='candidate')
        finally:
            await vk.close()
        self.assertEqual(seen[0]['random_id'], ['42'])
        self.assertIn('/export', seen[0]['keyboard'][0])
        self.assertNotIn('/export', seen[1]['keyboard'][0])

    async def test_vk_errors_do_not_expose_token(self):
        vk = VK(SimpleNamespace(vk_token='secret', api_version='5.199'))
        await vk.http.aclose()
        vk.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
            'error': {'error_code': 5, 'error_msg': 'secret', 'request_params': [{'key': 'access_token', 'value': 'secret'}]}})))
        try:
            with self.assertRaisesRegex(RuntimeError, 'error 5') as error:
                await vk.call('messages.send')
            self.assertNotIn('secret', str(error.exception))
        finally:
            await vk.close()
