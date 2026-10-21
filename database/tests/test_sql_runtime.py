"""Dispatcher contract; PostgreSQL lease semantics are covered in test_outbox."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

@pytest.fixture
def outbox_module():
    from gim_db import outbox
    return outbox


class QueueBoundary:
    lease_seconds = 30

    def __init__(self, topic):
        self.event = {'id': 'opaque-event', 'topic': topic, 'lease_token': 'token',
                      'application_id': 'app', 'payload': {'revision': 2}}
        self.receipts = []

    async def claim(self, topics=None):
        event, self.event = self.event, None
        return event

    async def finish(self, event_id, token, success, error_code=None):
        self.receipts.append((event_id, token, success, error_code))
        return True

    async def renew(self, event_id, token):
        return True


async def test_disabled_analysis_acknowledges_without_evaluation(outbox_module):
    queue = QueueBoundary('application.analyze')
    async def snapshot(app_id, revision):
        assert app_id == 'app' and revision == 2
        return {'saved': True}
    async def disabled(event):
        assert event['snapshot'] == {'saved': True}
        return None
    repo = SimpleNamespace(evaluation_snapshot=snapshot)
    count = await outbox_module.run_once({'repository': repo, 'handlers': {'application.analyze': disabled}}, queue)
    assert count == 1
    assert queue.receipts == [('opaque-event', 'token', True, 'analysis_disabled')]


async def test_handler_failure_records_only_exception_type(outbox_module):
    queue = QueueBoundary('vk.incoming')
    async def broken(event):
        raise ValueError('private payload must not be logged')
    await outbox_module.run_once({'repository': object(), 'handlers': {'vk.incoming': broken}}, queue)
    assert queue.receipts == [('opaque-event', 'token', False, 'ValueError')]


async def test_cancellation_keeps_event_retryable_and_propagates(outbox_module):
    queue = QueueBoundary('vk.send')
    async def cancelled(event):
        raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await outbox_module.run_once({'repository': object(), 'handlers': {'vk.send': cancelled}}, queue)
    assert queue.receipts == [('opaque-event', 'token', False, 'cancelled')]


async def test_timeout_releases_for_retry(outbox_module):
    queue = QueueBoundary('vk.send')
    async def blocked(event):
        await asyncio.Event().wait()
    await outbox_module.run_once({'repository': object(), 'handlers': {'vk.send': blocked}, 'job_timeout': .01}, queue)
    assert queue.receipts == [('opaque-event', 'token', False, 'TimeoutError')]


async def test_lost_lease_stops_handler_before_retry_receipt(outbox_module):
    queue = QueueBoundary('vk.incoming')
    queue.lease_seconds = .003
    stopped = asyncio.Event()
    async def expired(event_id, token):
        return False
    queue.renew = expired
    async def blocked(event):
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    finish = queue.finish
    async def receipt(*args):
        assert stopped.is_set()
        return await finish(*args)
    queue.finish = receipt
    await outbox_module.run_once({'repository': object(), 'handlers': {'vk.incoming': blocked}}, queue)
    assert queue.receipts == [('opaque-event', 'token', False, 'LeaseLostError')]


async def test_export_without_ready_file_is_never_acknowledged(outbox_module):
    from contextlib import asynccontextmanager
    queue = QueueBoundary('file.export')
    queue.event['file_id'] = 'file'
    class Connection:
        async def execute(self, query, args):
            assert args == ('file',)
            return self
        async def fetchone(self):
            return {'status': 'pending'}
    class Pool:
        @asynccontextmanager
        async def connection(self):
            yield Connection()
    async def unfinished(event):
        return None
    await outbox_module.run_once({'repository': SimpleNamespace(pool=Pool()), 'handlers': {'file.export': unfinished}}, queue)
    assert queue.receipts == [('opaque-event', 'token', False, 'ValueError')]


async def test_analysis_commit_receives_claim_token(outbox_module):
    queue = QueueBoundary('application.analyze')
    persisted = []
    async def snapshot(app_id, revision):
        return {'persisted_revision': revision}
    async def analyze(event):
        return {'score': 2}
    async def save(app_id, **kwargs):
        persisted.append((app_id, kwargs))
    repo = SimpleNamespace(evaluation_snapshot=snapshot, save_evaluation=save)
    await outbox_module.run_once({'repository': repo, 'handlers': {'application.analyze': analyze}}, queue)
    assert persisted == [('app', {'snapshot': {'persisted_revision': 2}, 'request_key': 'opaque-event',
                                  'source_event_id': 'opaque-event', 'source_lease_token': 'token', 'score': 2})]


def test_sql_runtime_has_no_external_queue_dependencies():
    import tomllib
    root = Path(__file__).parents[1]
    dependencies = tomllib.loads((root / 'pyproject.toml').read_text())['project']['dependencies']
    assert all(not name.startswith(('arq', 'redis')) for name in dependencies)
    migration = root / 'supabase/migrations/20261021170000_sql_runtime.sql'
    assert migration.exists()
