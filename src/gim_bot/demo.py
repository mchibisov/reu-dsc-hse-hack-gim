"""Локальный интерактивный прогон настоящей FSM без VK/LLM-ключей."""
import asyncio
import uuid
from pathlib import Path

from .config import Settings
from .storage import Store


async def main(database: str = 'demo.db'):
    database_path = Path(database).resolve()
    print('Локальный опрос в консоли. VK и Mistral не подключены; саммари и оценки отключены.')
    print('Используйте вымышленные данные. Выход: /quit. Удаление анкеты: /delete.')
    print(f'Ответы сохраняются в: {database_path}')
    store = Store(f'sqlite+aiosqlite:///{database_path.as_posix()}',
                  Settings(llm_api_key='', llm_model=''))
    await store.initialize()
    try:
        print((await store.handle_message(1, str(uuid.uuid4()), '/start')).text)
        while True:
            try:
                text = await asyncio.to_thread(input, '> ')
            except EOFError:
                break
            if text == '/quit':
                break
            reply = await store.handle_message(1, str(uuid.uuid4()), text)
            if reply.completed and await store.claim_analysis(reply.application_id):
                await store.save_analysis(reply.application_id, None, None, None)
            print(reply.text)
    finally:
        await store.close()


if __name__ == '__main__':
    asyncio.run(main())
