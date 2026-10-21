"""Интеграция только с отдельной тестовой PostgreSQL/Redis; локально пропускается без env."""
import os
import uuid

import pytest
from arq import create_pool
from arq.connections import RedisSettings
from arq.worker import Worker
from test_dialog import finish
from test_worker import NoModel

from gim_bot.storage import Store
from gim_bot.worker import analyze_application


@pytest.mark.skipif(not os.getenv('GIM_TEST_DATABASE_URL') or not os.getenv('GIM_TEST_REDIS_URL'),
                    reason='Нужны отдельные тестовые PostgreSQL и Redis')
async def test_postgres_and_real_arq_worker_without_llm():
    store = Store(os.environ['GIM_TEST_DATABASE_URL'])
    await store.initialize()
    user_id = uuid.uuid4().int % 2_000_000_000 + 10000
    queue_name = 'gim-test-' + uuid.uuid4().hex
    queue = await create_pool(RedisSettings.from_dsn(os.environ['GIM_TEST_REDIS_URL']))
    worker = None
    try:
        app = await finish(store, user_id)
        await queue.enqueue_job('analyze_application', app.id, _queue_name=queue_name)
        worker = Worker([analyze_application], redis_pool=queue, queue_name=queue_name, burst=True,
                        ctx={'store': store, 'gateway': NoModel()}, handle_signals=False,
                        health_check_key=queue_name + ':health', keep_result=0, log_results=False)
        await worker.async_run()
        saved = await store.get(app.id)
        assert saved.analysis_status == 'no_analytics'
        assert saved.score is None
    finally:
        await store.handle_message(user_id, 'cleanup-request', '/delete')
        await store.handle_message(user_id, 'cleanup-confirm', 'УДАЛИТЬ')
        if worker:
            await worker.close()
        await queue.aclose()
        await store.close()
