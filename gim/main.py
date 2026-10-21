import argparse
import asyncio
import logging
import signal

from gim.config import Settings
from gim.db import Database
from gim.service import Service
from gim.vk import VK


async def run(mode):
    settings = Settings.load()
    db = Database(settings.database_url)
    await db.open()
    vk = VK(settings)
    tasks = []
    try:
        if mode == 'migrate':
            await db.migrate()
            await db.bootstrap(settings.admin_ids)
            return
        if not settings.vk_token or settings.group_id <= 0:
            raise ValueError('Set VK_TOKEN and VK_GROUP_ID')
        service = Service(db, vk, settings)
        if mode == 'gateway':
            tasks = [asyncio.create_task(vk.gateway(db))]
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
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['migrate', 'gateway', 'worker'])
    asyncio.run(run(parser.parse_args().mode))


if __name__ == '__main__':
    main()
