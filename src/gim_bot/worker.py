import asyncio
import logging

from .analysis import create_model_client
from .config import get_settings
from .delivery import deliver_reply
from .export import build_excel
from .storage import Store
from .vk import VKClient

logger = logging.getLogger(__name__)


class AnalysisBusy(RuntimeError):
    pass


async def analyze_application(ctx, application_id: int):
    store = ctx['store']
    if not await store.claim_analysis(application_id):
        existing = await store.get(application_id)
        if existing and existing.analysis_status == 'processing':
            raise AnalysisBusy('application lease is still active')
        return
    app = await store.get(application_id)
    if not app:
        return
    try:
        analysis = await ctx['gateway'].analyze(app.answers, app.followups)
        await store.save_analysis(application_id, analysis, analysis.get('score') if analysis else None,
                                  analysis.get('rubric_version') if analysis else None)
    except asyncio.CancelledError:
        await asyncio.shield(store.save_analysis(application_id, None, None, None))
        raise
    except Exception as error:
        logger.warning('analysis_failed application_id=%d type=%s', application_id, type(error).__name__)
        await store.save_analysis(application_id, None, None, None)


async def notify_admin(ctx, application_id: int, admin_id: int):
    if admin_id not in ctx['settings'].admins:
        return
    app = await ctx['store'].get(application_id)
    if not app or app.status != 'completed' or admin_id in app.notified_admins:
        return
    await ctx['vk'].send(admin_id, f'+1 заполненная заявка · ID {app.id}\n/candidate {app.id}',
                         f'notification:{application_id}:{admin_id}')
    await ctx['store'].mark_notified(application_id, admin_id)


async def export_applications(ctx, request_id: int, admin_id: int):
    if admin_id not in ctx['settings'].admins:
        return
    pending = await ctx['store'].pending_exports()
    if not any(r.id == request_id and r.admin_id == admin_id for r in pending):
        return
    apps = await ctx['store'].list_applications()
    all_apps = await ctx['store'].list_applications(completed_only=False)
    content = await asyncio.to_thread(build_excel, apps, len(all_apps))
    attachment = await ctx['vk'].upload_document(admin_id, content, f'gim-{request_id}.xlsx')
    await ctx['vk'].send(admin_id, 'Анкеты ГИМ и сводка. Решение о приёме принимает сотрудник.',
                         f'export:{request_id}', attachment=attachment)
    await ctx['store'].export_done(request_id)


async def deliver_candidate_reply(ctx, key: str):
    await deliver_reply(ctx['store'], ctx['vk'], key)


async def reconcile(ctx):
    store = ctx['store']
    await store.recover_stale()
    for app in await store.list_applications():
        if app.analysis_status == 'queued':
            await store.enqueue_job(f'analysis:{app.id}', 'analyze_application', [app.id])
        for admin_id in ctx['settings'].admins:
            if admin_id not in app.notified_admins:
                await store.enqueue_job(f'notify:{app.id}:{admin_id}', 'notify_admin', [app.id, admin_id])
    for request in await store.pending_exports():
        await store.enqueue_job(f'export:{request.id}', 'export_applications', [request.id, request.admin_id])
    for reply in await store.pending_replies(due_only=True):
        await store.enqueue_job(f'reply:{reply.key}:{reply.attempts}', 'deliver_candidate_reply', [reply.key])


HANDLERS = {fn.__name__: fn for fn in (
    analyze_application, notify_admin, export_applications, deliver_candidate_reply)}


async def execute_job(ctx, job):
    try:
        await asyncio.wait_for(HANDLERS[job.kind](ctx, *job.payload['args']), timeout=120)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning('job_failed kind=%s attempt=%d type=%s', job.kind, job.attempts, type(error).__name__)
        await ctx['store'].finish_job(job.key, job.lease_token, False,
                                      retry_delay=600 if job.kind == 'analyze_application' else None)
    else:
        await ctx['store'].finish_job(job.key, job.lease_token, True)


async def run_once(ctx):
    await reconcile(ctx)
    jobs = []
    for _ in range(ctx['settings'].worker_max_jobs):
        job = await ctx['store'].claim_job()
        if job is None:
            break
        jobs.append(job)
    await asyncio.gather(*(execute_job(ctx, job) for job in jobs))
    return len(jobs)


async def run_loop(ctx):
    while True:
        try:
            await run_once(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error('worker_cycle_failed type=%s', type(error).__name__)
        await asyncio.sleep(ctx['settings'].worker_poll_interval)


async def main():
    from .bot import configure_logging
    configure_logging()
    settings = get_settings()
    store = Store(settings.database_url, settings)
    await store.initialize()
    gateway, vk = create_model_client(settings), VKClient(settings)
    try:
        await run_loop({'settings': settings, 'store': store, 'gateway': gateway, 'vk': vk})
    finally:
        await store.close()
        await gateway.close()
        await vk.close()


if __name__ == '__main__':
    asyncio.run(main())
