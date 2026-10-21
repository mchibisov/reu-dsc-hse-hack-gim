import asyncio
import hashlib
import logging
import time

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class VKError(RuntimeError):
    pass


def random_id(key: str) -> int:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], 'big') % 2147483646 + 1


class VKClient:
    def __init__(self, settings: Settings, transport=None, rate_interval=.35):
        self.settings = settings
        self.client = httpx.AsyncClient(transport=transport, timeout=35)
        self.rate_interval = rate_interval
        self._rate_lock = asyncio.Lock()
        self._last_call = 0.0

    async def close(self):
        await self.client.aclose()

    async def call(self, method: str, **params):
        for attempt in range(3):
            async with self._rate_lock:
                wait = self.rate_interval - (time.monotonic() - self._last_call)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_call = time.monotonic()
            try:
                response = await self.client.post('https://api.vk.com/method/' + method,
                    data={**params, 'access_token': self.settings.vk_token, 'v': self.settings.vk_api_version})
                response.raise_for_status()
                body = response.json()
                if 'error' not in body:
                    return body['response']
                code = body['error'].get('error_code')
                if code not in (6, 9, 10, 29):
                    raise VKError(f'VK method={method} code={code}')
            except (httpx.HTTPError, ValueError, KeyError):
                pass
            if attempt < 2:
                await asyncio.sleep(0.1 if self.rate_interval == 0 else 1 + attempt)
        raise VKError(f'VK method={method} unavailable')

    async def send(self, user_id: int, text: str, key: str, attachment: str | None = None):
        chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)] or ['']
        for index, chunk in enumerate(chunks):
            params = {'peer_id': user_id, 'message': chunk, 'random_id': random_id(f'{key}:{index}')}
            if attachment and index == len(chunks) - 1:
                params['attachment'] = attachment
            await self.call('messages.send', **params)

    async def upload_document(self, user_id: int, content: bytes, title: str) -> str:
        server = await self.call('docs.getMessagesUploadServer', type='doc', peer_id=user_id)
        response = await self.client.post(server['upload_url'],
            files={'file': (title, content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        response.raise_for_status()
        file_token = response.json()['file']
        saved = await self.call('docs.save', file=file_token, title=title)
        doc = saved['doc']
        result = f"doc{doc['owner_id']}_{doc['id']}"
        if doc.get('access_key'):
            result += '_' + doc['access_key']
        return result
