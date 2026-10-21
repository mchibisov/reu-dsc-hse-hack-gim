from test_dialog import finish

from gim_bot.worker import analyze_application, reconcile


class NoModel:
    async def analyze(self, answers, followups):
        return None


async def test_no_model_retains_application_without_score(store):
    app = await finish(store)
    await analyze_application({'store': store, 'gateway': NoModel()}, app.id)
    saved = await store.get(app.id)
    assert saved.analysis_status == 'no_analytics'
    assert saved.score is None
    assert saved.answers == app.answers
    await analyze_application({'store': store, 'gateway': NoModel()}, app.id)
    assert (await store.get(app.id)).analysis_status == 'no_analytics'


async def test_reconcile_picks_up_saved_application_after_queue_failure(store):
    app = await finish(store)
    await reconcile({'store': store, 'settings': type('S', (), {'admins': []})()})
    job = await store.claim_job()
    assert job.kind == 'analyze_application'
    assert job.payload['args'] == [app.id]
