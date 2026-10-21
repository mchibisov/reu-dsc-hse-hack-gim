# S003 dialog-12: full private PostgreSQL acceptance

dialog-07/09 выявили mojibake SQL export keys; родитель исправил migrate.py encoding=utf-8 и пересоздал исключительно отдельную local test DB с 5 миграциями.
Изменение условий: корректные UTF8 SQL ключи + fail-closed snapshot из dialog-11.
Команда: PYTHONPATH=database/src TEST_DATABASE_URL=<local-test-server> ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий: 28 unit + private PostgreSQL integration проходят; реальный VK/Storage API не вызываются.

Завершён кодом 0. Полный вывод artifacts/tests.txt. PostgreSQL отдельный локальный, роли через SET ROLE, внешний VK/Storage mocked; cloud production не проверялся.
