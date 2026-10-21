import asyncio
import json
import logging

import httpx

log = logging.getLogger(__name__)


def message_event(event):
    if event.get('type') != 'message_new':
        return None
    msg = event.get('object', {}).get('message', {})
    if msg.get('out', 0) or msg.get('from_id', 0) <= 0 or msg.get('peer_id') != msg.get('from_id'):
        return None
    if not event.get('event_id'):
        message_id = msg.get('conversation_message_id') or msg.get('id')
        if not message_id:
            return None
        event = {**event, 'event_id': f"message:{msg['peer_id']}:{message_id}"}
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

    async def send(self, peer_id, text, random_id, attachment=None, role='candidate'):
        buttons = [[{'action': {'type': 'text', 'label': 'Старт'}, 'color': 'primary'},
                    {'action': {'type': 'text', 'label': '/status'}, 'color': 'secondary'}]]
        if role in ('curator', 'admin'):
            buttons.extend([[{'action': {'type': 'text', 'label': command}, 'color': 'secondary'}
                             for command in row] for row in (('/top', '/export'), ('/stats', '/jobs'))])
        params = {'peer_id': peer_id, 'message': text, 'random_id': random_id,
                  'keyboard': json.dumps({'one_time': False, 'buttons': buttons}, ensure_ascii=False)}
        if attachment:
            params['attachment'] = attachment
        return await self.call('messages.send', **params)

    async def diagnose(self):
        permissions = await self.call('groups.getTokenPermissions')
        settings = await self.call('groups.getLongPollSettings', group_id=self.settings.group_id)
        return {'group_id': self.settings.group_id,
                'permissions': [p['name'] for p in permissions.get('permissions', [])],
                'longpoll_enabled': settings.get('is_enabled', False),
                'message_new': bool(settings.get('events', {}).get('message_new'))}

    async def upload(self, peer_id, name, data):
        server = await self.call('docs.getMessagesUploadServer', peer_id=peer_id, type='doc')
        result = await self.http.post(server['upload_url'], files={'file': (name, data, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        result.raise_for_status()
        saved = await self.call('docs.save', file=result.json()['file'], title=name)
        doc = saved['doc']
        return f"doc{doc['owner_id']}_{doc['id']}" + ('_' + doc['access_key'] if doc.get('access_key') else '')

    async def gateway(self, db, guard=None):
        current = None
        delay = 1
        resume_ts = await db.cursor(self.settings.group_id)
        while True:
            if guard:
                # Detect a lost singleton-lock connection before polling more events.
                await guard.execute('SELECT 1')
            try:
                if current is None:
                    current = await self.call('groups.getLongPollServer', group_id=self.settings.group_id)
                    if resume_ts:
                        current['ts'] = resume_ts
                result = await self.http.get(current['server'], params={'act': 'a_check', 'key': current['key'], 'ts': current['ts'], 'wait': 25})
                result.raise_for_status()
                payload = result.json()
                accepted = [normalized for event in payload.get('updates', [])
                            if (normalized := message_event(event)) and normalized.get('group_id') == self.settings.group_id]
                next_poll = poll_next(payload, current)
                if next_poll:
                    await db.ingest_batch(accepted, self.settings.group_id, next_poll['ts'])
                    resume_ts = next_poll['ts']
                elif payload.get('failed') == 3:
                    resume_ts = None
                    log.warning('longpoll history reset group_id=%s', self.settings.group_id)
                current = next_poll
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning('gateway retry error_type=%s delay=%s', type(exc).__name__, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def close(self):
        await self.http.aclose()
