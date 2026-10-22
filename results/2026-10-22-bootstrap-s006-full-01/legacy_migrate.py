"""Одноразовая подготовка legacy-тестов; DSN задаётся оператором теста."""
import asyncio
import os
import sys

from gim.db import Database


async def setup():
    database = Database(os.environ['TEST_DATABASE_URL'])
    await database.open()
    try:
        await database.migrate()
    finally:
        await database.close()


if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(setup())
