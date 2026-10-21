# S003 dialog-15: persisted consent retry before next answer

dialog-14 воспроизвёл P2 RED: current_question=None сразу после отказа; invalid date/directions regression уже проходили.
Изменение: убран специальный ранний return отказа; общий advance сохраняет повторную base consent question через Repository до ожидания ответа. Согласие/контакты не выставляются при отказе, raw обеих версий остаётся.
Реальный PostgreSQL integration теперь начинает отказ→согласие→replay до ack; итог 23 ответа (20 base с отказом +3 followup).
Команда: PYTHONPATH=database/src TEST_DATABASE_URL=<local-test-server> ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий: все 31 unit/DB tests GREEN, включая invalid date/directions correction. Внешних API нет.

Завершён кодом 0. artifacts/tests.txt. Проверено только на отдельной локальной PostgreSQL с SET ROLE, VK/Storage mocked.
