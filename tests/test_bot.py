from test_dialog import ANSWERS

from gim_bot.bot import Bot
from gim_bot.config import Settings


class FakeVK:
    def __init__(self):
        self.sent = []

    async def send(self, user_id, text, key, **kwargs):
        self.sent.append((user_id, text, key))


class FakeGateway:
    async def followups(self, answers, library):
        return [{'topic': 'media', 'question': 'Вы снимали мероприятия: какие задачи выполняли лично?',
                 'field': 'experience', 'anchor': 'Снимал мероприятия'}]


def event(text, number, uid=123, peer=None):
    return {'type': 'message_new', 'event_id': str(number), 'object': {'message': {
        'from_id': uid, 'peer_id': peer or uid, 'text': text, 'id': number}}}


async def test_bot_ignores_group_chat(store):
    vk = FakeVK()
    bot = Bot(Settings(), store, vk, FakeGateway())
    await bot.process_update(event('/start', 1, peer=2000000001))
    assert not vk.sent
    assert await store.get_by_user(123) is None


async def test_bot_uses_personalized_questions_and_keeps_candidate_score_private(store):
    vk = FakeVK()
    bot = Bot(Settings(), store, vk, FakeGateway())
    await bot.process_update(event('Согласен', 1))
    for i in range(40):
        app = await store.get_by_user(123)
        if app.status == 'completed':
            break
        key = await store.current_key(123)
        await bot.process_update(event(ANSWERS.get(key, 'Снимал музейные мероприятия'), i + 2))
    assert any('какие задачи выполняли лично' in text for _, text, _ in vk.sent)
    assert 'получена' in vk.sent[-1][1]
    assert 'балл' not in vk.sent[-1][1].lower()


async def test_duplicate_vk_event_has_one_transition(store):
    vk = FakeVK()
    bot = Bot(Settings(), store, vk, FakeGateway())
    await bot.process_update(event('Согласен', 1))
    await bot.process_update(event('Тестовый Кандидат', 2))
    sent_before_replay = list(vk.sent)
    await bot.process_update(event('Тестовый Кандидат', 2))
    assert await store.current_key(123) == 'email'
    assert vk.sent == sent_before_replay


async def test_bot_can_use_library_followups_without_model_or_broker(store):
    vk = FakeVK()
    bot = Bot(Settings(), store, vk)
    await bot.process_update(event('Согласен', 1))
    for i in range(40):
        app = await store.get_by_user(123)
        if app.status == 'completed':
            break
        key = await store.current_key(123)
        await bot.process_update(event(ANSWERS.get(key, 'Снимал музейные мероприятия'), i + 2))
    saved = await store.get_by_user(123)
    assert saved.status == 'completed'
    assert saved.score is None
    assert all(q['source'] == 'museum' for q in saved.followups)
