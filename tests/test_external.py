"""Интеграция с отдельной тестовой PostgreSQL; локально пропускается без env."""
import os
import uuid

import pytest
from test_dialog import finish
from test_worker import NoModel

from gim_bot.config import Settings
from gim_bot.storage import Store
from gim_bot.worker import run_once


@pytest.mark.skipif(not os.getenv('GIM_TEST_DATABASE_URL'), reason='Нужна отдельная тестовая PostgreSQL')
async def test_postgres_and_sql_worker_without_llm():
    store = Store(os.environ['GIM_TEST_DATABASE_URL'])
    await store.initialize()
    user_id = uuid.uuid4().int % 2_000_000_000 + 10000
    try:
        app = await finish(store, user_id)
        await run_once({'store': store, 'gateway': NoModel(), 'settings': Settings(admin_ids='')})
        saved = await store.get(app.id)
        assert saved.analysis_status == 'no_analytics'
        assert saved.score is None
    finally:
        await store.handle_message(user_id, 'cleanup-request', '/delete')
        await store.handle_message(user_id, 'cleanup-confirm', 'УДАЛИТЬ')
        await store.close()
