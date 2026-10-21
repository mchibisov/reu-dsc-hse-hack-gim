"""Локальный интерактивный прогон настоящей FSM без VK/LLM-ключей."""
import asyncio
import uuid

from .config import Settings
from .storage import Store


async def main():
    print('Локальный тест, не сообщество ВК. Используйте вымышленные данные. Выход: /quit.')
    store = Store('sqlite+aiosqlite:///demo.db', Settings())
    await store.initialize()
    try:
        print((await store.handle_message(1, str(uuid.uuid4()), '/start')).text)
        while True:
            text = await asyncio.to_thread(input, '> ')
            if text == '/quit':
                break
            print((await store.handle_message(1, str(uuid.uuid4()), text)).text)
    finally:
        await store.close()


if __name__ == '__main__':
    asyncio.run(main())
