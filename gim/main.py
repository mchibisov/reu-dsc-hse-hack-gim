import argparse
import asyncio
import logging
import signal

from gim.config import Settings, load_dotenv
from gim.db import Database
from gim.service import Service
from gim.vk import VK


async def run(mode):
    settings = Settings.load()
    if mode == 'check-vk':
        vk = VK(settings)
        try:
            import json
            print(json.dumps(await vk.diagnose(), ensure_ascii=False))
        finally:
            await vk.close()
        return
    db = Database(settings.database_url, group_id=settings.group_id)
    await db.open()
    vk = VK(settings)
    tasks = []
    try:
        if mode == 'check-db':
            async with db.pool.connection() as c:
                await c.execute('SELECT 1')
            print('PostgreSQL connection OK')
            return
        if mode == 'migrate':
            await db.migrate()
            await db.bootstrap(settings.admin_ids)
            return
        if not settings.vk_token or settings.group_id <= 0:
            raise ValueError('Set VK_TOKEN and VK_GROUP_ID')
        service = Service(db, vk, settings)
        if mode == 'gateway':
            async def guarded_gateway():
                async with db.gateway_guard(settings.group_id) as guard:
                    await vk.gateway(db, guard)
            tasks = [asyncio.create_task(guarded_gateway())]
        else:
            tasks = [asyncio.create_task(service.worker()) for _ in range(settings.concurrency)]
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        stopper = asyncio.create_task(stop.wait())
        tasks.append(stopper)
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task is not stopper:
                task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await vk.close()
        await db.close()


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['migrate', 'gateway', 'worker', 'check-vk', 'check-db'])
    asyncio.run(run(parser.parse_args().mode))


if __name__ == '__main__':
    main()
