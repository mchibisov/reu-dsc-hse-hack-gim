import asyncio
from datetime import timedelta
from pathlib import Path

import yaml

from gim_bot.models import now
from gim_bot.storage import Store


async def test_durable_jobs_survive_restart_and_deduplicate(store):
    await store.enqueue_job('analysis:7', 'analyze_application', [7])
    await store.enqueue_job('analysis:7', 'analyze_application', [7])
    reopened = Store(store.database_url)
    try:
        job = await reopened.claim_job()
        assert job.key == 'analysis:7'
        assert job.payload == {'args': [7]}
        assert await reopened.claim_job() is None
        assert await reopened.finish_job(job.key, job.lease_token, True)
        await store.enqueue_job('analysis:7', 'analyze_application', [7])
        assert await store.claim_job() is None
    finally:
        await reopened.close()


async def test_two_workers_cannot_claim_the_same_job(store):
    await store.enqueue_job('export:1', 'export_applications', [1, 99])
    other = Store(store.database_url)
    try:
        claims = await asyncio.gather(store.claim_job(), other.claim_job())
        assert sum(job is not None for job in claims) == 1
    finally:
        await other.close()


async def test_expired_lease_recovers_and_old_worker_cannot_ack(store, monkeypatch):
    await store.enqueue_job('export:1', 'export_applications', [1, 99])
    old = await store.claim_job()
    later = now() + timedelta(minutes=11)
    monkeypatch.setattr('gim_bot.storage.now', lambda: later)
    recovered = await store.claim_job()
    assert recovered.key == old.key
    assert recovered.lease_token != old.lease_token
    assert recovered.attempts == 2
    assert not await store.finish_job(old.key, old.lease_token, True)
    assert await store.finish_job(recovered.key, recovered.lease_token, True)


async def test_failed_jobs_stop_after_three_attempts(store, monkeypatch):
    await store.enqueue_job('notify:1:99', 'notify_admin', [1, 99])
    instant = now()
    for attempt in range(1, 4):
        monkeypatch.setattr('gim_bot.storage.now', lambda: instant)
        job = await store.claim_job()
        assert job.attempts == attempt
        assert await store.finish_job(job.key, job.lease_token, False)
        instant += timedelta(minutes=2)
    await store.enqueue_job('notify:1:99', 'notify_admin', [1, 99])
    assert await store.claim_job() is None


def test_runtime_has_no_redis_or_arq_dependency():
    project = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((project / 'compose.yaml').read_text(encoding='utf-8'))
    assert 'redis' not in compose['services']
    assert compose['services']['worker']['command'] == ['python', '-m', 'gim_bot.worker']
    import tomllib
    dependencies = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))['project']['dependencies']
    assert not any(item.lower().startswith(('redis', 'arq', 'hiredis')) for item in dependencies)
    for source in (project / 'src/gim_bot').glob('*.py'):
        assert 'from redis' not in source.read_text(encoding='utf-8')
        assert 'from arq' not in source.read_text(encoding='utf-8')
