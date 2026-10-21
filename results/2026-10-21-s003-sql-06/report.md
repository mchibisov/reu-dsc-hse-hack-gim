# S003 SQL — запуск 06

Цель: настоящие SQLQueue/runtime проверки на изолированном PostgreSQL 18.4,
localhost:55439/gim_private_test (пять миграций применены родителем).
Команда: TEST_DATABASE_URL явно задан; Python gim_bot/.venv,
`pytest -q database/tests/test_outbox.py database/tests/test_sql_runtime.py`.
Результат: запуск не завершился, прерван Ctrl+C; код выхода 1.
Изолирующая диагностика: синхронный psycopg SELECT 1 вернул (1,),
pg_stat_activity не показал асинхронных соединений. Минимальный AsyncConnectionPool
с timeout=3 воспроизвёл ошибку `Psycopg cannot use the ProactorEventLoop`
и PoolTimeout. Это несовместимый Windows event loop, не результат SQLQueue-проверки.
Повтор одиночного теста -vv -s имел ту же остановку и также прерван.
Вывод: недостаточно данных о SQLQueue; инфраструктурная причина установлена.
Следующий запуск: WindowsSelectorEventLoopPolicy в tests/conftest.py и standalone
outbox entrypoint, затем повтор targeted/full database suite на той же тестовой БД.
Доказательство частичного запуска: [sql-pytest.txt](artifacts/sql-pytest.txt).
