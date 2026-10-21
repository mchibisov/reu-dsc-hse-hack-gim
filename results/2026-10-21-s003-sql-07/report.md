# S003 SQL — запуск 07

Изменение после 06: database/tests/conftest.py и standalone SQL-worker используют
WindowsSelectorEventLoopPolicy. TEST_DATABASE_URL явно указывает только на
изолированный localhost:55439/gim_private_test, PostgreSQL 18.4.

Команда: `pytest -q database/tests/test_outbox.py database/tests/test_sql_runtime.py`
через gim_bot/.venv Python с PYTHONPATH=database/src.
Результат: 16 passed, 1.79s; завершён.
Подтверждены в проверенных условиях: SQL exclusive claim, serial FIFO,
блокировка следующего incoming во время retry, recovery просроченной аренды,
fencing finish/renew и записи анализа, конечные попытки (ошибка и авария),
изоляция сообщества, загрузка точного сохранённого вопроса, staff revoke,
runtime cancel/timeout/heartbeat и отсутствие ack до готовности экспорта.
Доказательство: [sql-pytest.txt](artifacts/sql-pytest.txt).
Ограничение: локальный PostgreSQL не доказывает облачную работоспособность.
