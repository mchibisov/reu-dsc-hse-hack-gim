# S003 dialog-13: candidate confirmation copy

После dialog-12 (29 GREEN с PostgreSQL) убрана техническая фраза об отключённой оценке из candidate confirmation/status; сотруднику режим по-прежнему поясняется в help.
Команда: PYTHONPATH=database/src TEST_DATABASE_URL=<local-test-server> ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий: все 29 unit/DB tests остаются GREEN; внешних API нет.

Завершён кодом 0. artifacts/tests.txt. Ограничения те же: separate local PostgreSQL, SET ROLE, mocked VK/Storage.
