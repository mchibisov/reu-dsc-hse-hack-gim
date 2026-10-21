import asyncio

from .config import get_settings
from .storage import Store


async def main():
    store = Store(get_settings().database_url)
    try:
        await store.initialize()
        print('Схема базы ГИМ готова.')
    finally:
        await store.close()


if __name__ == '__main__':
    asyncio.run(main())
