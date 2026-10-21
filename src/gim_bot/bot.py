import asyncio
import logging

from arq import create_pool
from arq.connections import RedisSettings

from .admin import Admin
from .analysis import GatewayClient
from .config import Settings, get_settings
from .delivery import deliver_reply
from .storage import Store
from .vk import VKClient, VKError

logger = logging.getLogger(__name__)


async def connect_queue(settings):
    connection = RedisSettings.from_dsn(settings.redis_url)
    connection.conn_retries = 1
    return await create_pool(connection)


def configure_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    for name in ('httpx', 'httpcore', 'sqlalchemy.engine'):
        logging.getLogger(name).setLevel(logging.CRITICAL)


class Bot:
    def __init__(self, settings: Settings, store, vk, gateway, queue=None):
        self.settings = settings
        self.store = store
        self.vk = vk
        self.gateway = gateway
        self.queue = queue
        self.admin = Admin(store, settings)
        self.limit = asyncio.Semaphore(settings.bot_concurrency)
        self.locks: dict[int, asyncio.Lock] = {}

    async def process_update(self, update):
        if update.get('type') != 'message_new':
            return
        message = update.get('object', {}).get('message', {})
        user_id = message.get('from_id', 0)
        if user_id <= 0 or message.get('peer_id') != user_id or message.get('out'):
            return
        if update.get('group_id') and self.settings.vk_group_id and update['group_id'] != self.settings.vk_group_id:
            return
        event_id = update.get('event_id') or message.get('conversation_message_id') or message.get('id')
        if event_id is None:
            return
        event_id = str(event_id)
        async with self.limit, self.locks.setdefault(user_id, asyncio.Lock()):
            text = message.get('text', '')
            response = await self.admin.handle(user_id, user_id, text, event_id)
            if response is not None:
                try:
                    await self.vk.send(user_id, response, f'admin:{user_id}:{event_id}')
                except VKError:
                    logger.warning('admin_reply_undeliverable')
                return
            reply = await self.store.handle_message(user_id, event_id, text)
            if reply.ignored:
                return
            if reply.personalize:
                app = await self.store.get_by_user(user_id)
                questions = await self.gateway.followups(app.answers, app.followups) if app else None
                intro = self._direction_intro((app.answers if app else {}).get('directions', ''))
                adjusted = await self.store.replace_followups(user_id, questions or [], event_id, prefix=intro)
                reply = adjusted or reply
            delivery_key = await self.store.queue_reply(user_id, reply.text, f'reply:{event_id}')
            await deliver_reply(self.store, self.vk, delivery_key)
            if reply.completed and self.queue:
                try:
                    await self.queue.enqueue_job('analyze_application', reply.application_id,
                                                 _job_id=f'analysis:{reply.application_id}')
                    for admin_id in self.settings.admins:
                        await self.queue.enqueue_job('notify_admin', reply.application_id, admin_id,
                                                     _job_id=f'notify:{reply.application_id}:{admin_id}')
                except Exception as error:
                    logger.warning('queue_failed type=%s', type(error).__name__)

    @staticmethod
    def _direction_intro(direction):
        text = direction.lower()
        if 'фонд' in text:
            return 'В фондах помогают с оцифровкой и каталогами; число мест ограничено.'
        if 'инклюз' in text:
            return 'В инклюзивных проектах сопровождают посетителей с инвалидностью; предусмотрены отдельный отбор и обучение.'
        if 'медиа' in text:
            return 'В медиа помогают с текстами, фотографиями, видео и дизайном материалов музея.'
        if 'проект' in text or 'квест' in text or 'мастер' in text:
            return 'В проектном направлении разрабатывают квесты, игры и мастер-классы.'
        if 'мероприят' in text or 'организац' in text:
            return 'В организационном направлении помогают на мероприятиях и работают с посетителями.'
        return 'Основная анкета сохранена. Осталось несколько уточнений о вашем опыте.'

    async def poll_once(self, state):
        response = await self.vk.client.get(state['server'],
            params={'act': 'a_check', 'key': state['key'], 'ts': state['ts'], 'wait': 25}, timeout=35)
        response.raise_for_status()
        payload = response.json()
        if payload.get('failed') == 1:
            result = {**state, 'ts': payload['ts']}
        elif payload.get('failed') in (2, 3):
            result = await self.vk.call('groups.getLongPollServer', group_id=self.settings.vk_group_id)
        elif 'failed' in payload:
            raise RuntimeError('unsupported_long_poll_failure')
        else:
            await asyncio.gather(*(self.process_update(item) for item in payload.get('updates', [])))
            result = {**state, 'ts': payload['ts']}
        await self.store.save_runtime('vk_long_poll', result)
        return result

    async def run(self):
        state = await self.store.load_runtime('vk_long_poll')
        while True:
            try:
                if not state:
                    state = await self.vk.call('groups.getLongPollServer', group_id=self.settings.vk_group_id)
                    await self.store.save_runtime('vk_long_poll', state)
                state = await self.poll_once(state)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error('poll_failed type=%s', type(error).__name__)
                await asyncio.sleep(3)


async def main():
    configure_logging()
    settings = get_settings()
    if not settings.vk_token or not settings.vk_group_id or not settings.admins:
        raise SystemExit('Заполните VK_TOKEN, VK_GROUP_ID и ADMIN_IDS в .env.')
    if not settings.internal_api_key:
        raise SystemExit('Заполните INTERNAL_API_KEY в .env.')
    store = Store(settings.database_url, settings)
    await store.initialize()
    vk, gateway, queue = VKClient(settings), GatewayClient(settings), None
    try:
        try:
            queue = await connect_queue(settings)
        except Exception:
            logger.warning('redis_unavailable_saved_applications_will_be_reconciled')
        await Bot(settings, store, vk, gateway, queue).run()
    finally:
        await store.close()
        await vk.close()
        await gateway.close()
        if queue:
            await queue.aclose()


if __name__ == '__main__':
    asyncio.run(main())
