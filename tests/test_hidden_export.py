import asyncio
import json
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import select
from test_bot import FakeVK, event
from test_dialog import finish

from gim_bot.bot import Bot
from gim_bot.config import Settings
from gim_bot.models import MessageEvent
from gim_bot.storage import Store
from gim_bot.worker import export_applications

CODE = 'synthetic-access-fixture'


class DocumentVK(FakeVK):
    def __init__(self):
        super().__init__()
        self.uploads = []

    async def upload_document(self, user_id, content, filename):
        self.uploads.append((user_id, content, filename))
        return 'doc-fixture'


def configured(store):
    settings = Settings(_env_file=None, admin_ids='999', excel_access_code=CODE)
    store.settings = settings
    vk = DocumentVK()
    return settings, vk, Bot(settings, store, vk)


async def test_code_queues_private_export_before_questionnaire_without_secret_or_replay(store):
    settings, vk, bot = configured(store)
    await bot.process_update(event('Согласен', 1))
    before = await store.get_by_user(123)
    await bot.process_update(event('/excel ' + CODE, 2))
    requests = await store.pending_exports()
    assert len(requests) == 1
    assert requests[0].admin_id == 123
    saved = await store.get_by_user(123)
    assert saved.answers == before.answers and saved.cursor == before.cursor
    async with store.sessions() as session:
        records = list(await session.scalars(select(MessageEvent)))
    assert not any(record.event_id == '2' for record in records)
    assert CODE not in json.dumps([record.result for record in records])
    assert CODE not in repr(settings)
    sent = list(vk.sent)
    await bot.process_update(event('/excel ' + CODE, 2))
    assert vk.sent == sent
    assert CODE not in str(vk.sent)
    assert len(await store.pending_exports()) == 1


async def test_bad_empty_and_group_codes_never_export_or_enter_answers(store):
    _, vk, bot = configured(store)
    await bot.process_update(event('Согласен', 1))
    for number, text in enumerate(('/excel wrong', '/excel', '/excel ' + CODE), 2):
        await bot.process_update(event(text, number, peer=2000000001 if number == 4 else None))
    assert not await store.pending_exports()
    assert (await store.get_by_user(123)).answers == {}
    assert CODE not in str(vk.sent)


async def test_code_receiver_has_no_admin_rights_or_access_to_foreign_answers(store):
    foreign = await finish(store, uid=789)
    _, vk, bot = configured(store)
    await bot.process_update(event('/excel ' + CODE, 1))
    for number, command in enumerate(('/top', f'/candidate {foreign.id}', '/stats', '/export'), 2):
        await bot.process_update(event(command, number))
    assert len(await store.pending_exports()) == 1
    assert foreign.answers['name'] not in str(vk.sent)
    assert 'Команды куратора' not in str(vk.sent)
    assert await store.get_by_user(123) is None


async def test_worker_delivers_code_export_once_to_authenticated_user(store):
    app = await finish(store)
    settings, vk, bot = configured(store)
    await bot.process_update(event('/excel ' + CODE, 100, uid=456))
    request = (await store.pending_exports())[0]
    ctx = {'settings': settings, 'store': store, 'vk': vk}
    await export_applications(ctx, request.id, 789)
    assert not vk.uploads
    await export_applications(ctx, request.id, 456)
    await export_applications(ctx, request.id, 456)
    assert len(vk.uploads) == 1
    assert vk.uploads[0][0] == 456
    workbook = load_workbook(BytesIO(vk.uploads[0][1]))
    assert any(app.answers['name'] == c.value for row in workbook['Анкеты'] for c in row)
    assert not await store.pending_exports()
    assert len([m for m in vk.sent if m[2].startswith('export:')]) == 1


async def test_rotation_revokes_pending_code_export_even_for_admin(store):
    settings, vk, bot = configured(store)
    await bot.process_update(event('/excel ' + CODE, 1, uid=999))
    request = (await store.pending_exports())[0]
    settings.excel_access_code = 'rotated-synthetic'
    await export_applications({'settings': settings, 'store': store, 'vk': vk}, request.id, 999)
    assert not vk.uploads
    assert not await store.pending_exports()


async def test_rotation_during_upload_prevents_sending_document(store):
    settings, vk, bot = configured(store)
    await bot.process_update(event('/excel ' + CODE, 1))
    request = (await store.pending_exports())[0]
    upload = vk.upload_document

    async def rotate(*args):
        result = await upload(*args)
        settings.excel_access_code = 'rotated-synthetic'
        return result

    vk.upload_document = rotate
    await export_applications({'settings': settings, 'store': store, 'vk': vk}, request.id, 123)
    assert not any(m[2].startswith('export:') for m in vk.sent)


async def test_code_rate_limit_persists_across_store_reopen_and_replay(store):
    settings, vk, bot = configured(store)
    for number in range(1, 6):
        await bot.process_update(event('/excel wrong', number))
        await bot.process_update(event('/excel wrong', number))
    reopened = Store(store.database_url, settings)
    try:
        await Bot(settings, reopened, vk).process_update(event('/excel ' + CODE, 6))
        assert not await reopened.pending_exports()
        await Bot(settings, reopened, vk).process_update(event('/excel ' + CODE, 7, uid=456))
        assert len(await reopened.pending_exports()) == 1
    finally:
        await reopened.close()


async def test_normal_help_and_questionnaire_do_not_prompt_for_code(store):
    _, vk, bot = configured(store)
    await bot.process_update(event('/help', 1))
    await bot.process_update(event('Согласен', 2))
    await bot.process_update(event('/help', 3))
    await bot.process_update(event('/help', 4, uid=999))
    text = str(vk.sent).lower()
    assert '/excel' not in text and 'код' not in text


async def test_failed_event_replay_does_not_spend_another_attempt(store):
    _, _, bot = configured(store)
    for number in range(1, 5):
        await bot.process_update(event('/excel wrong', number))
        await bot.process_update(event('/excel wrong', number))
    await bot.process_update(event('/excel ' + CODE, 5))
    assert len(await store.pending_exports()) == 1


async def test_rate_limit_uses_rolling_ten_minutes_and_expires(store, monkeypatch):
    configured(store)
    instant = [1000.0]
    monkeypatch.setattr('gim_bot.storage.time', lambda: instant[0])
    for number in range(4):
        await store.request_code_export(123, str(number), 'wrong')
    instant[0] = 1599.0
    await store.request_code_export(123, 'fifth', 'wrong')
    instant[0] = 1601.0
    for number in range(4):
        await store.request_code_export(123, 'new-' + str(number), 'wrong')
    await store.request_code_export(123, 'blocked', CODE)
    assert not await store.pending_exports()
    instant[0] = 2202.0
    await store.request_code_export(123, 'expired', CODE)
    assert len(await store.pending_exports()) == 1


async def test_concurrent_replayed_code_event_from_two_store_connections_is_one_request(store):
    settings, _, _ = configured(store)
    other = Store(store.database_url, settings)
    try:
        await asyncio.gather(*[
            db.request_code_export(123, 'same-event', CODE)
            for db in (store, other, store, other)
        ])
        assert len(await store.pending_exports()) == 1
    finally:
        await other.close()


async def test_plain_request_cannot_grant_export_to_non_admin(store):
    settings, vk, _ = configured(store)
    request_id = await store.request_export(123, 'untrusted-request')
    await export_applications({'settings': settings, 'store': store, 'vk': vk}, request_id, 123)
    assert not vk.uploads


async def test_regular_admin_export_still_delivers(store):
    settings, vk, bot = configured(store)
    await bot.process_update(event('/export', 1, uid=999))
    request = (await store.pending_exports())[0]
    await export_applications({'settings': settings, 'store': store, 'vk': vk}, request.id, 999)
    assert len(vk.uploads) == 1 and vk.uploads[0][0] == 999
