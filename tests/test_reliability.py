import httpx
import pytest
from test_bot import event

from gim_bot.analysis import sanitize_answers, validate_analysis
from gim_bot.bot import Bot
from gim_bot.config import Settings
from gim_bot.rubric import CRITERIA
from gim_bot.vk import VKError


async def test_replayed_batch_cannot_resurrect_deleted_application(store):
    batch = [('consent', 'Согласен'), ('name', 'Тестовый Кандидат'),
             ('delete', '/delete'), ('confirm', 'УДАЛИТЬ')]
    old_id = None
    for key, text in batch:
        reply = await store.handle_message(123, key, text)
        old_id = reply.application_id or old_id
    assert await store.get_by_user(123) is None
    for key, text in batch:
        await store.handle_message(123, key, text)
    assert await store.get_by_user(123) is None
    await store.handle_message(123, 'new-consent', 'Согласен')
    new = await store.get_by_user(123)
    assert new is not None
    assert new.id > old_id
    assert not new.answers


async def test_one_unreachable_recipient_does_not_stall_long_poll_cursor(store):
    class PartlyBrokenVK:
        def __init__(self):
            self.sent = []
            self.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
                200, json={'ts': '2', 'updates': [event('Согласен', 1, uid=123),
                                                event('Согласен', 2, uid=456)]})))

        async def send(self, user_id, text, key, **kwargs):
            if user_id == 123:
                raise VKError('recipient unavailable')
            self.sent.append(user_id)

    vk = PartlyBrokenVK()
    bot = Bot(Settings(), store, vk, None)
    state = {'server': 'https://vk-test.invalid/lp', 'key': 'test', 'ts': '1'}
    try:
        result = await bot.poll_once(state)
        assert result['ts'] == '2'
        assert (await store.load_runtime('vk_long_poll'))['ts'] == '2'
        assert 456 in vk.sent
        assert await store.get_by_user(123) is not None
        pending = await store.pending_replies()
        assert len(pending) == 1
        assert pending[0].user_id == 123
    finally:
        await vk.client.aclose()


async def test_database_failure_still_prevents_checkpoint_advance(store, monkeypatch):
    class VK:
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={'ts': '2', 'updates': [event('Согласен', 1)]})))

    async def fail(*args):
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(store, 'handle_message', fail)
    state = {'server': 'https://vk-test.invalid/lp', 'key': 'test', 'ts': '1'}
    await store.save_runtime('vk_long_poll', state)
    try:
        with pytest.raises(RuntimeError, match='database'):
            await Bot(Settings(), store, VK(), None).poll_once(state)
        assert (await store.load_runtime('vk_long_poll'))['ts'] == '1'
    finally:
        await VK.client.aclose()


def test_followup_question_is_not_candidate_evidence():
    safe = sanitize_answers({'experience': 'Нет опыта'}, [
        {'question': 'Есть конкретная мотивация помогать музею?', 'answer': 'Не знаю'}])
    raw = {'criteria': [{'id': key, 'level': 2, 'field': 'followup_1_question',
                        'quote': 'Есть конкретная мотивация помогать музею',
                        'explanation': 'Тест проверки источника.'} for key in CRITERIA],
           'summary': 'Тест.', 'recommended_direction': 'не определено',
           'rationale': 'Тест.', 'interview_questions': ['Расскажите об опыте?']}
    with pytest.raises(ValueError, match='источник'):
        validate_analysis(raw, safe)


async def test_pending_reply_is_recovered_without_reprocessing_answer(store, monkeypatch):
    from gim_bot.delivery import deliver_reply

    class VK:
        broken = True
        sent = []

        async def send(self, uid, text, key):
            if self.broken:
                raise VKError('temporary error')
            self.sent.append((uid, text))

    vk = VK()
    await store.handle_message(123, 'consent', 'Согласен')
    key = await store.queue_reply(123, 'Ваш email?', 'event-2')
    assert await deliver_reply(store, vk, key) is False
    from datetime import timedelta

    from gim_bot.models import now
    monkeypatch.setattr('gim_bot.storage.now', lambda: now() + timedelta(minutes=2))
    vk.broken = False
    assert await deliver_reply(store, vk, key) is True
    assert not await store.pending_replies()
    assert vk.sent == [(123, 'Ваш email?')]


async def test_deletion_removes_pending_personalized_replies(store):
    await store.handle_message(123, 'consent', 'Согласен')
    await store.queue_reply(123, 'Уточнение о вашем опыте', 'pending-event')
    await store.handle_message(123, 'delete', '/delete')
    await store.handle_message(123, 'confirm', 'УДАЛИТЬ')
    assert not await store.pending_replies()


async def test_new_prompt_supersedes_old_undelivered_prompt(store):
    await store.queue_reply(123, 'Как вас зовут?', 'old-event')
    await store.queue_reply(123, 'Ваш email?', 'new-event')
    pending = await store.pending_replies()
    assert len(pending) == 1
    assert pending[0].text == 'Ваш email?'
