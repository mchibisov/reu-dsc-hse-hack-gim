import asyncio
import json
import os
import statistics
import time
from pathlib import Path

from test_dialog import ANSWERS


async def test_90_concurrent_candidates_keep_independent_progress(store):
    latencies = []

    async def run(uid):
        await store.handle_message(uid, 'consent', 'Согласен')
        for index in range(40):
            app = await store.get_by_user(uid)
            if app.status == 'completed':
                assert app.answers['email'] == f'candidate{uid}@example.org'
                return
            key = await store.current_key(uid)
            text = f'candidate{uid}@example.org' if key == 'email' else ANSWERS.get(key, 'Работал с посетителями')
            start = time.perf_counter()
            await store.handle_message(uid, str(index), text)
            latencies.append((time.perf_counter() - start) * 1000)
        raise AssertionError('Незавершённый диалог')

    start = time.perf_counter()
    await asyncio.gather(*(run(uid) for uid in range(1000, 1090)))
    apps = await store.list_applications()
    assert len(apps) == 90
    assert len({app.user_id for app in apps}) == 90
    assert len({app.answers['email'] for app in apps}) == 90
    metrics = {'concurrent_candidates': 90, 'completed': len(apps), 'errors': 0,
               'elapsed_seconds': round(time.perf_counter() - start, 3),
               'messages': len(latencies), 'p95_store_latency_ms': round(statistics.quantiles(latencies, n=100)[94], 2),
               'scope': 'local SQLite Store only; excludes VK, Redis, PostgreSQL and LLM'}
    output = os.environ.get('GIM_LOAD_REPORT')
    if output:
        Path(output).write_text(json.dumps(metrics, indent=2), encoding='utf-8')


async def test_duplicate_messages_from_one_candidate_are_serialized(store):
    await store.handle_message(123, 'consent', 'Согласен')
    replies = await asyncio.gather(*(store.handle_message(123, 'same', 'Тестовый Кандидат') for _ in range(20)))
    assert all(reply == replies[0] for reply in replies)
    assert await store.current_key(123) == 'email'
