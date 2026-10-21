import asyncio
import json
import logging

import httpx

log = logging.getLogger(__name__)


def message_event(event):
    if event.get('type') != 'message_new' or not event.get('event_id'):
        return None
    msg = event.get('object', {}).get('message', {})
    if msg.get('out', 0) or msg.get('from_id', 0) <= 0 or msg.get('peer_id') != msg.get('from_id'):
        return None
    return event


def poll_next(response, current):
    failed = response.get('failed')
    if failed in (2, 3):
        return None
    if failed and failed != 1:
        raise RuntimeError('Unsupported Long Poll failure')
    return {**current, 'ts': response['ts']}


class VK:
    def __init__(self, settings):
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=40)

    async def call(self, method, **params):
        response = await self.http.post('https://api.vk.com/method/' + method,
            data={**params, 'access_token': self.settings.vk_token, 'v': self.settings.api_version})
        response.raise_for_status()
        data = response.json()
        if 'error' in data:
            # Do not log request params: VK may echo access_token in errors.
            raise RuntimeError(f"VK API {method} error {data['error'].get('error_code')}")
        return data['response']

    async def send(self, peer_id, text, random_id, attachment=None):
        buttons = [[{'action': {'type': 'text', 'label': 'Старт'}, 'color': 'primary'},
                    {'action': {'type': 'text', 'label': '/status'}, 'color': 'secondary'}]]
        params = {'peer_id': peer_id, 'message': text, 'random_id': random_id,
                  'keyboard': json.dumps({'one_time': False, 'buttons': buttons}, ensure_ascii=False)}
        if attachment:
            params['attachment'] = attachment
        return await self.call('messages.send', **params)

    async def upload(self, peer_id, name, data):
        server = await self.call('docs.getMessagesUploadServer', peer_id=peer_id, type='doc')
        result = await self.http.post(server['upload_url'], files={'file': (name, data, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        result.raise_for_status()
        saved = await self.call('docs.save', file=result.json()['file'], title=name)
        doc = saved['doc']
        return f"doc{doc['owner_id']}_{doc['id']}" + ('_' + doc['access_key'] if doc.get('access_key') else '')

    async def gateway(self, db):
        current = None
        delay = 1
        while True:
            try:
                if current is None:
                    current = await self.call('groups.getLongPollServer', group_id=self.settings.group_id)
                result = await self.http.get(current['server'], params={'act': 'a_check', 'key': current['key'], 'ts': current['ts'], 'wait': 25})
                result.raise_for_status()
                payload = result.json()
                for event in payload.get('updates', []):
                    accepted = message_event(event)
                    if accepted and accepted['group_id'] == self.settings.group_id:
                        await db.ingest(accepted)
                current = poll_next(payload, current)
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning('gateway retry error_type=%s delay=%s', type(exc).__name__, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def close(self):
        await self.http.aclose()
