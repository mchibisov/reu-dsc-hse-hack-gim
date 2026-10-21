import asyncio
from datetime import timedelta

import pytest
from test_dialog import finish
from test_worker import NoModel

from gim_bot.config import Settings
from gim_bot.models import now
from gim_bot.storage import Store
from gim_bot.vk import VKError
from gim_bot.worker import run_once


async def test_cancelled_analysis_does_not_leave_processing_forever(store):
    from gim_bot.worker import analyze_application
    app = await finish(store)
    entered = asyncio.Event()

    class BlockingModel:
        async def analyze(self, answers, followups):
            entered.set()
            await asyncio.Future()

    task = asyncio.create_task(analyze_application({'store': store, 'gateway': BlockingModel()}, app.id))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await store.get(app.id)).analysis_status == 'no_analytics'


async def test_busy_analysis_job_retries_after_application_lease_expires(store, monkeypatch):
    from gim_bot.models import BackgroundJob
    from gim_bot.worker import execute_job
    app = await finish(store)
    await store.claim_analysis(app.id)
    await store.enqueue_job(f'analysis:{app.id}', 'analyze_application', [app.id])
    job = await store.claim_job()
    ctx = {'store': store, 'settings': Settings(admin_ids=''), 'gateway': NoModel()}
    await execute_job(ctx, job)
    async with store.sessions() as session:
        pending = await session.get(BackgroundJob, job.key)
    assert pending.status == 'queued'
    later = now() + timedelta(minutes=11)
    monkeypatch.setattr('gim_bot.storage.now', lambda: later)
    await run_once(ctx)
    assert (await store.get(app.id)).analysis_status == 'no_analytics'


class VK:
    def __init__(self):
        self.sent = []
        self.uploads = []
        self.broken = False

    async def send(self, user_id, text, key, **kwargs):
        if self.broken:
            raise VKError('temporary')
        self.sent.append((user_id, text, key))

    async def upload_document(self, user_id, content, name):
        self.uploads.append((user_id, content, name))
        return 'doc1_2'


async def test_two_sql_workers_analyze_notify_and_export_once(store):
    app = await finish(store)
    request = await store.request_export(99, 'test-export')
    vk = VK()
    settings = Settings(admin_ids='99', worker_max_jobs=10)
    second = Store(store.database_url)
    try:
        def context(db):
            return {'store': db, 'settings': settings, 'gateway': NoModel(), 'vk': vk}

        await asyncio.gather(run_once(context(store)), run_once(context(second)))
        await run_once(context(store))
        saved = await store.get(app.id)
        assert saved.analysis_status == 'no_analytics'
        assert saved.score is None
        assert saved.notified_admins == [99]
        assert len([key for _, _, key in vk.sent if key.startswith('notification:')]) == 1
        assert len(vk.uploads) == 1
        assert vk.uploads[0][1][:2] == b'PK'
        assert not any(r.id == request for r in await store.pending_exports())
    finally:
        await second.close()


async def test_outbox_retry_waits_until_due_and_is_not_lost(store, monkeypatch):
    vk = VK()
    vk.broken = True
    settings = Settings(admin_ids='')
    ctx = {'store': store, 'settings': settings, 'gateway': NoModel(), 'vk': vk}
    await store.queue_reply(123, 'Ваш email?', 'event-test')
    await run_once(ctx)
    assert not vk.sent
    assert len(await store.pending_replies()) == 1
    assert await run_once(ctx) == 0
    instant = now() + timedelta(minutes=2)
    monkeypatch.setattr('gim_bot.storage.now', lambda: instant)
    vk.broken = False
    await run_once(ctx)
    assert len(vk.sent) == 1
    assert not await store.pending_replies()


async def test_vk_mode_needs_no_gateway_key_or_broker(monkeypatch, tmp_path):
    from gim_bot import bot
    settings = Settings(database_url=f'sqlite+aiosqlite:///{tmp_path / "vk.db"}',
                        vk_token='test-token', vk_group_id=1, admin_ids='99',
                        internal_api_key='', gateway_url='', llm_api_key='', llm_model='')
    monkeypatch.setattr(bot, 'get_settings', lambda: settings)

    class Started(Exception):
        pass

    async def started(self):
        raise Started

    monkeypatch.setattr(bot.Bot, 'run', started)
    with pytest.raises(Started):
        await bot.main()
