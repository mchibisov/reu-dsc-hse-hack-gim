"""Очередь настоящая; вместо внешних VK/AI — управляемые сетевые границы."""
import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import psycopg
import pytest

from test_database import DSN, complete_draft, env

pytestmark = pytest.mark.skipif(not DSN, reason='disposable PostgreSQL required')


def install_test_wake():
    with psycopg.connect(DSN) as connection:
        connection.execute('''CREATE OR REPLACE FUNCTION gim.wake_worker(bigint)
            RETURNS bigint LANGUAGE sql AS $$ SELECT 1::bigint $$''')
        connection.execute('REVOKE ALL ON FUNCTION gim.wake_worker(bigint) FROM PUBLIC')
        connection.execute('GRANT EXECUTE ON FUNCTION gim.wake_worker(bigint) TO gim_bot')


@asynccontextmanager
async def dispatcher(env, handlers, *, budget=245):
    from gim.serverless import drain
    bot, worker, staff, recruitment, *_ = env
    install_test_wake()
    for repository in (bot, worker, staff):
        await repository.pool.resize(min_size=1, max_size=2)

    @asynccontextmanager
    async def existing(dsn, **kwargs):
        yield {'bot': bot.pool, 'worker': worker.pool, 'staff': staff.pool}[dsn]

    settings = SimpleNamespace(database_bot_url='bot', database_worker_url='worker',
                               database_staff_url='staff', group_id=recruitment['group_id'])
    service = SimpleNamespace(worker_repo=worker, handlers=handlers)
    with patch('gim.serverless.create_pool', existing), \
         patch('gim.serverless.SharedService', return_value=service), \
         patch('gim.serverless.VK', return_value=SimpleNamespace(close=AsyncMock())):
        task = asyncio.create_task(drain(settings, budget=budget))
        try:
            yield task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def emit_event(env, topic, *, application_id=None, **payload):
    from gim_db.repository import emit
    _, worker, _, recruitment, *_ = env
    async with worker.pool.connection() as connection:
        await emit(connection, application_id, topic, 'latency-' + str(uuid.uuid4()),
                   {'group_id': recruitment['group_id'], **payload})


@pytest.mark.parametrize('analysis_count', [1, 3])
async def test_new_dialog_and_delivery_do_not_wait_for_slow_analysis(env, analysis_count):
    app, *_ = await complete_draft(env)
    entered = asyncio.Event()
    release = asyncio.Event()
    delivered = asyncio.Event()
    started = 0

    async def slow_analysis(event):
        nonlocal started
        started += 1
        if started >= min(analysis_count, 2):
            entered.set()
        await release.wait()
        return None

    async def incoming(event):
        await emit_event(env, 'vk.send', peer_id=123, text='synthetic reply')

    async def send(event):
        assert event['payload']['text'] == 'synthetic reply'
        assert not release.is_set(), 'Reply waited for unrelated analysis'
        delivered.set()

    for _ in range(analysis_count):
        await emit_event(env, 'application.analyze', application_id=app['id'], revision=1)
    async with dispatcher(env, {'application.analyze': slow_analysis,
                                 'vk.incoming': incoming, 'vk.send': send}) as task:
        await asyncio.wait_for(entered.wait(), timeout=2)
        # Let initially idle lanes reach their empty-queue branch.
        await asyncio.sleep(.15)
        start = time.monotonic()
        await emit_event(env, 'vk.incoming', peer_id=123)
        try:
            await asyncio.wait_for(delivered.wait(), timeout=1.5)
            elapsed = time.monotonic() - start
            print(f'late-dialog analysis_count={analysis_count} seconds={elapsed:.3f}')
        finally:
            release.set()
        assert await asyncio.wait_for(task, timeout=3) == 'drained'


async def test_short_remaining_budget_still_handles_plain_dialog(env):
    delivered = []

    async def incoming(event):
        await emit_event(env, 'vk.send', peer_id=123, text='synthetic tail reply')

    async def send(event):
        delivered.append(event['payload']['text'])

    await emit_event(env, 'vk.incoming', peer_id=123)
    async with dispatcher(env, {'vk.incoming': incoming, 'vk.send': send}, budget=10) as task:
        assert await asyncio.wait_for(task, timeout=3) == 'drained'
    assert delivered == ['synthetic tail reply']


async def test_empty_dispatcher_exits_without_idle_wait(env):
    started = time.monotonic()
    async with dispatcher(env, {}) as task:
        assert await asyncio.wait_for(task, timeout=2) == 'drained'
    assert time.monotonic() - started < 1


async def test_failed_lane_stops_siblings_before_releasing_owner(env):
    from gim.serverless import DELIVERY_TOPICS
    started = asyncio.Event()
    active = 0

    async def boundary(ctx, queue, limit=1, *, topics=None):
        nonlocal active
        if topics == DELIVERY_TOPICS:
            await started.wait()
            raise RuntimeError('synthetic dispatcher failure')
        active += 1
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    with patch('gim.serverless.run_once', boundary):
        async with dispatcher(env, {}) as task:
            with pytest.raises(ExceptionGroup):
                await asyncio.wait_for(task, timeout=2)
            assert active == 0
    _, worker, _, recruitment, *_ = env
    async with worker.pool.connection() as connection:
        row = await (await connection.execute(
            'SELECT expires_at<=now() AS released FROM gim.runtime_leases WHERE group_id=%s',
            (recruitment['group_id'],))).fetchone()
    assert row['released']

async def test_callback_commits_receipt_before_wake_to_close_exit_race(env):
    """The exiting owner's final scan must see the callback before wake checks its lease."""
    from gim.serverless import receive
    bot, worker, _, recruitment, _, actor, _ = env
    install_test_wake()
    event_id='commit-wake-'+str(uuid.uuid4())
    observed=[]

    class ObservedConnection:
        def __init__(self, connection):self.connection=connection
        def __getattr__(self, name):return getattr(self.connection,name)
        async def execute(self, query, params=None, **kwargs):
            if query=='SELECT gim.wake_worker(%s)':
                async with worker.pool.connection() as observer:
                    row=await (await observer.execute("SELECT count(*) n FROM gim.outbox_events WHERE dedupe_key=%s",
                        (f'vk-in:{recruitment["group_id"]}:{event_id}',))).fetchone()
                assert row['n']==1, 'Wake ran before receipt COMMIT: exiting worker can miss it until Cron'
                observed.append(True)
            return await self.connection.execute(query,params,**kwargs)

    class ObservedPool:
        @asynccontextmanager
        async def connection(self):
            async with bot.pool.connection() as connection:yield ObservedConnection(connection)

    @asynccontextmanager
    async def existing(*args, **kwargs):yield ObservedPool()

    event={'group_id':recruitment['group_id'],'secret':'test','type':'message_new','event_id':event_id,
           'object':{'message':{'from_id':actor,'peer_id':actor,'text':'/help'}}}
    settings=SimpleNamespace(group_id=recruitment['group_id'],database_bot_url='bot',excel_access_code='')
    with patch.dict('os.environ',{'VK_CALLBACK_SECRET':'test'}),patch('gim.serverless.create_pool',existing):
        assert await receive(event,settings)==(200,'ok')
    assert observed==[True]
