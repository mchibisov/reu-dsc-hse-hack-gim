# S003 dialog-06: PostgreSQL integration

Предыдущая проверка: dialog-05 — 27 unit прошли, PostgreSQL skipped без DSN.
Изменение условий: предоставлен отдельный локальный PostgreSQL18 test cluster, 5 миграций уже применены.
Команда: PYTHONPATH=database/src TEST_DATABASE_URL=<local-test-server> ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Метод: уникальный synthetic recruitment, реальные три runtime роли, SQLQueue, replay, 19 base + 3 followup, submit, disabled analysis, immutable snapshot XLSX. VK и Storage mocked, без сетевых внешних API.
Критерий: все unit и один DB integration проходят; без TRUNCATE/DELETE чужих данных.
Состояние: запускается.

Завершён кодом 1. Вывод artifacts/tests.txt.
