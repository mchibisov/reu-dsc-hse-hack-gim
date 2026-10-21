import asyncio
import json
import logging

import httpx

log = logging.getLogger(__name__)


class VKAPIError(RuntimeError):
    def __init__(self, method, error_code):
        self.code='vk_'+str(int(error_code))
        self.error_code=int(error_code)
        super().__init__(f'VK API {method} error {self.error_code}')


def message_event(event):
    if event.get('type') != 'message_new':
        return None
    msg = event.get('object', {}).get('message', {})
    if msg.get('out', 0) or msg.get('from_id', 0) <= 0 or msg.get('peer_id') != msg.get('from_id'):
        return None
    if msg.get('conversation_message_id'):
        event={**event,'event_id':f"message:{msg['peer_id']}:{msg['conversation_message_id']}"}
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
            raise VKAPIError(method,data['error'].get('error_code',0))
        return data['response']

    async def send(self, peer_id, text, random_id, attachment=None, role='candidate',question_slot=None,want_cmid=False):
        buttons = [[{'action': {'type': 'text', 'label': 'Начать'}, 'color': 'primary'},
                    {'action': {'type': 'text', 'label': 'Статус'}, 'color': 'secondary'},
                    {'action': {'type': 'text', 'label': 'Помощь'}, 'color': 'secondary'}]]
        options={'consent':(('Согласен','Не согласен'),),
                 'current_status':(('Студент','Работаю','Безработный'),),
                 'directions':(('Организационное','Проектное'),('Фондовое','Инклюзивное'),('Медиа','Не определился')),
                 'discovery':(('Социальные сети','От друзей'),('Сайт музея','Другое')),
                 'expectations_match':(('Задачи подходят, открыт альтернативам',),('Хочу обсудить с куратором',)),
                 'vk_url':(('Использовать мою страницу',),)}
        for row in reversed(options.get(question_slot,())):
            buttons.insert(0,[{'action':{'type':'text','label':label},'color':'positive'} for label in row])
        if question_slot=='vk_url':
            buttons.insert(0,[{'action':{'type':'open_link','label':'Открыть мою страницу VK',
                                       'link':f'https://vk.com/id{peer_id}'}}])
        if role in ('curator', 'admin'):
            buttons.extend([[{'action': {'type': 'text', 'label': command}, 'color': 'secondary'}
                             for command in row] for row in (('/top', '/export'), ('/stats', '/admin'),('/new', '/jobs'))])
        if role=='admin':
            buttons.append([{'action':{'type':'text','label':'/reset'},'color':'negative'}])
        params = {'peer_id': peer_id, 'message': text, 'random_id': random_id,
                  'keyboard': json.dumps({'one_time': False, 'buttons': buttons}, ensure_ascii=False)}
        if want_cmid:
            params['peer_ids']=str(params.pop('peer_id'))
        if attachment:
            params['attachment'] = attachment
        try:
            sent=await self.call('messages.send', **params)
            if isinstance(sent,list):
                if len(sent)!=1 or sent[0].get('error'):raise VKAPIError('messages.send',sent[0].get('error',{}).get('code',1))
                return sent[0]
            return sent
        except VKAPIError as exc:
            if exc.error_code!=912:
                raise
            # Community messages work without bot keyboards. Keep the same
            # random_id/attachment so a configuration mistake does not lose data.
            log.warning('vk_keyboard_disabled group_id=%s',self.settings.group_id)
            params.pop('keyboard')
            sent=await self.call('messages.send', **params)
            if isinstance(sent,list):
                if len(sent)!=1 or sent[0].get('error'):raise VKAPIError('messages.send',sent[0].get('error',{}).get('code',1))
                return sent[0]
            return sent

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
