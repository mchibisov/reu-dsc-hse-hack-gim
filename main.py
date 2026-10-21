"""Запуск опроса: python main.py. Внешние сервисы не требуются."""
import argparse
import asyncio
import sys
from pathlib import Path


def main():
    project = Path(__file__).resolve().parent
    sys.path.insert(0, str(project / 'src'))
    parser = argparse.ArgumentParser(description='Локальный опрос ГИМ без VK, LLM и саммари.')
    parser.add_argument('--database', default=str(project / 'demo.db'),
                        help='Путь к SQLite с ответами; по умолчанию demo.db рядом с main.py.')
    args = parser.parse_args()
    from gim_bot.demo import main as run_questionnaire

    try:
        asyncio.run(run_questionnaire(args.database))
    except KeyboardInterrupt:
        print('\nОпрос остановлен. Сохранённые ответы останутся при следующем запуске.')


if __name__ == '__main__':
    main()
