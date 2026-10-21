"""Запуск опроса: python main.py. Внешние сервисы не требуются."""
import argparse
import asyncio
import os
import sys
from pathlib import Path


def main():
    project = Path(__file__).resolve().parent
    sys.path.insert(0, str(project / 'src'))
    parser = argparse.ArgumentParser(description='Опрос ГИМ: консоль или VK, без внешнего брокера.')
    parser.add_argument('--vk', action='store_true', help='Запустить VK-бота и SQL worker; настройки из .env.')
    parser.add_argument('--database', default=str(project / 'demo.db'),
                        help='Путь к SQLite с ответами; по умолчанию demo.db рядом с main.py.')
    args = parser.parse_args()
    try:
        if args.vk:
            os.chdir(project)
            from gim_bot.bot import main as run_vk
            from gim_bot.process_lock import single_vk_process
            try:
                with single_vk_process(project / 'vk-process.lock'):
                    asyncio.run(run_vk(with_worker=True))
            except RuntimeError as error:
                raise SystemExit(str(error)) from error
        else:
            from gim_bot.demo import main as run_questionnaire
            asyncio.run(run_questionnaire(args.database))
    except KeyboardInterrupt:
        print('\nОпрос остановлен. Сохранённые ответы останутся при следующем запуске.')


if __name__ == '__main__':
    main()
