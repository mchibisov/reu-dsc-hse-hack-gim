# S003 dialog-07: Windows asyncio compatibility

dialog-06 отрицательный: psycopg отказался работать с Windows ProactorEventLoop до подключения БД.
Изменено: tests явно выбирают WindowsSelectorEventLoopPolicy; production loop policy принадлежит runtime.
Команда: PYTHONPATH=database/src TEST_DATABASE_URL=<local-test-server> ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Состояние: запускается, внешний API не вызывается.

Завершён кодом 1. Вывод artifacts/tests.txt.
