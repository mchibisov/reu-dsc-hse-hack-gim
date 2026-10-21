"""Запуск существующего VK клиента с private БД, без Redis и LLM."""
import argparse
import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack, suppress

from gim.config import load_dotenv
from gim.shared_config import SharedSettings
from gim.shared_gateway import GatewayLedger
from gim.shared_service import SharedService
from gim.shared_storage import LocalPrivateStorage
from gim.vk import VK
from gim_db.outbox import SQLQueue, run_once
from gim_db.repository import Repository, all_rows, create_pool, one

log = logging.getLogger(__name__)


class StartupError(RuntimeError):
    """Сообщение без секретов, безопасное для оператора."""


async def check_database(settings, pools):
    for expected, pool in zip(('gim_bot', 'gim_worker', 'gim_staff'), pools):
        async with pool.connection() as c:
            auth = await one(c, """SELECT rolsuper,rolbypassrls,
                pg_has_role(current_user,'gim_bot','USAGE') AS gim_bot,
                pg_has_role(current_user,'gim_worker','USAGE') AS gim_worker,
                pg_has_role(current_user,'gim_staff','USAGE') AS gim_staff
                FROM pg_roles WHERE rolname=current_user""")
            if not auth or auth['rolsuper'] or auth['rolbypassrls'] or any(auth[role] != (role == expected) for role in ('gim_bot', 'gim_worker', 'gim_staff')):
                raise StartupError(f'Нужен отдельный login только с ролью {expected}, без SUPERUSER/BYPASSRLS')
    async with pools[0].connection() as c:
        recruitment = await one(c, 'SELECT group_id,status,questionnaire_version FROM gim.recruitments WHERE id=%s', (settings.recruitment_id,))
        if not recruitment or recruitment['group_id'] != settings.group_id or recruitment['status'] != 'active':
            raise StartupError('RECRUITMENT_ID должен указывать активный набор своего VK_GROUP_ID')
        templates = await all_rows(c, "SELECT target_slot FROM gim.question_templates WHERE recruitment_id=%s AND kind='base'", (settings.recruitment_id,))
        if not {'consent', 'birth_date', 'directions'} <= {t['target_slot'] for t in templates}:
            raise StartupError('В банке обязательны согласие, дата рождения и выбор направлений')
        # Fail before Long Poll if the new SQL runtime migration has not been applied.
        await c.execute('SELECT group_id,ts,lease_token,lease_until FROM gim.gateway_checkpoints LIMIT 0')
        await c.execute('SELECT lease_until,lease_token,attempts,failed_at FROM gim.outbox_events LIMIT 0')
    return {'schema': 'gim', 'recruitment_id': str(settings.recruitment_id), 'base_questions': len(templates),
            'analysis': 'disabled', 'redis': False, 'storage': 'local-private'}


async def worker_loop(service, pool, group_id):
    queue = SQLQueue(pool, group_id=group_id)
    ctx = {'repository': service.worker_repo, 'handlers': service.handlers}
    while True:
        try:
            if not await run_once(ctx, queue, limit=1):
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning('worker_retry error_type=%s', type(exc).__name__)
            await asyncio.sleep(2)


async def gateway_loop(vk, pool, group_id):
    ledger = GatewayLedger(pool, group_id)
    await ledger.acquire()
    try:
        await vk.gateway(ledger, guard=ledger)
    finally:
        with suppress(Exception):
            await asyncio.shield(ledger.release())


async def run(mode, settings):
    async with AsyncExitStack() as stack:
        pools = []
        for dsn in (settings.database_bot_url, settings.database_worker_url, settings.database_staff_url):
            pool = create_pool(dsn, max_size=max(2, settings.concurrency))
            await stack.enter_async_context(pool)
            await pool.wait(timeout=15)
            pools.append(pool)
        info = await check_database(settings, pools)
        if mode == 'check-db':
            print(json.dumps(info, ensure_ascii=False))
            return
        if not settings.vk_token:
            raise StartupError('Заполните VK_TOKEN в локальном .env')
        vk = VK(settings)
        stack.push_async_callback(vk.close)
        if mode == 'check-vk':
            print(json.dumps(await vk.diagnose(), ensure_ascii=False))
            return
        if mode == 'gateway':
            await gateway_loop(vk, pools[0], settings.group_id)
            return
        storage = LocalPrivateStorage(settings.storage_dir)
        stack.push_async_callback(storage.close)
        service = SharedService(*(Repository(pool) for pool in pools), vk, settings, storage)
        log.info('shared_runtime_start group_id=%s mode=%s workers=%s analysis=disabled', settings.group_id, mode, settings.concurrency)
        async with asyncio.TaskGroup() as tasks:
            if mode in {'run', 'gateway'}:
                tasks.create_task(gateway_loop(vk, pools[0], settings.group_id))
            if mode in {'run', 'worker'}:
                for _ in range(settings.concurrency):
                    tasks.create_task(worker_loop(service, pools[1], settings.group_id))


def main():
    parser = argparse.ArgumentParser(description='VK-бот: private PostgreSQL, SQL очередь, без LLM')
    parser.add_argument('mode', choices=('check-db', 'check-vk', 'run', 'gateway', 'worker'))
    args = parser.parse_args()
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        settings = SharedSettings.load()
        asyncio.run(run(args.mode, settings))
    except KeyboardInterrupt:
        log.info('shared_runtime_stopped')
    except (ValueError, StartupError) as exc:
        parser.exit(2, str(exc) + '\n')
    except Exception as exc:
        # No traceback/DSNs/answers in operator logs; diagnose permissions via check-db.
        parser.exit(2, f'Запуск не выполнен ({type(exc).__name__}); проверьте доступ к БД и логи сервера.\n')


if __name__ == '__main__':
    main()
