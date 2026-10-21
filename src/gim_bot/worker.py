import asyncio
import logging

from arq import cron
from arq.connections import RedisSettings

from .analysis import GatewayClient
from .config import get_settings
from .export import build_excel
from .storage import Store
from .vk import VKClient

logger = logging.getLogger(__name__)


async def analyze_application(ctx, application_id: int):
    store = ctx['store']
    if not await store.claim_analysis(application_id):
        return
    app = await store.get(application_id)
    if not app:
        return
    try:
        analysis = await ctx['gateway'].analyze(app.answers, app.followups)
        await store.save_analysis(application_id, analysis, analysis.get('score') if analysis else None,
                                  analysis.get('rubric_version') if analysis else None)
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


async def reconcile(ctx):
    store = ctx['store']
    await store.recover_stale()
    for app in await store.list_applications():
        if app.analysis_status == 'queued':
            await ctx['redis'].enqueue_job('analyze_application', app.id, _job_id=f'analysis:{app.id}')
        for admin_id in ctx['settings'].admins:
            if admin_id not in app.notified_admins:
                await ctx['redis'].enqueue_job('notify_admin', app.id, admin_id,
                                                _job_id=f'notify:{app.id}:{admin_id}')
    for request in await store.pending_exports():
        await ctx['redis'].enqueue_job('export_applications', request.id, request.admin_id,
                                       _job_id=f'export:{request.id}')


async def startup(ctx):
    from .bot import configure_logging
    configure_logging()
    settings = get_settings()
    ctx['settings'] = settings
    ctx['store'] = Store(settings.database_url, settings)
    await ctx['store'].initialize()
    ctx['gateway'] = GatewayClient(settings)
    ctx['vk'] = VKClient(settings)
    await reconcile(ctx)


async def shutdown(ctx):
    for key in ('store', 'gateway', 'vk'):
        await ctx[key].close()


class WorkerSettings:
    functions = [analyze_application, notify_admin, export_applications]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    cron_jobs = [cron(reconcile, second={0, 30}, run_at_startup=False)]
    max_jobs = get_settings().worker_max_jobs
    job_timeout = 120
    max_tries = 3
    keep_result = 0
    health_check_interval = 30
    log_results = False
