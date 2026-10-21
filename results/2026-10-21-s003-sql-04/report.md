# S003 SQL — запуск 04

Цель: полный регрессионный набор database и целостность сокращённого lock-файла.
Изменения с запуска 03: проверки потерянной аренды (handler остановлен до release),
экспорта без ready, передачи lease token в save_evaluation; реальные DB-тесты
переписаны на SQLQueue вместо Publisher/ARQ.

Команды: Python gim_bot/.venv, `pytest -q database/tests`; TOML parser и проверка
замкнутости dependencies/optional-dependencies всех оставшихся packages в uv.lock.
Результат: 11 passed, 23 skipped, 0.44s; lock TOML корректен, ссылки зависимостей
разрешаются, arq/redis/hiredis/async-timeout/click/pyjwt отсутствуют.
TEST_DATABASE_URL не задан; никаких попыток облачного подключения или VK не было.

Вывод: локальные проверки подтверждены в проверенных условиях, настоящая DB-приёмка
имеет недостаточно данных. Состояние запуска завершён с пропусками.
Доказательства: [pytest.txt](artifacts/pytest.txt), [lock-check.txt](artifacts/lock-check.txt).
Побайтовая проверка четырёх старых миграций (с нормализацией CRLF):
[migrations-check.txt](artifacts/migrations-check.txt), все неизменны.
Ограничения: uv отсутствует, resolver uv sync --locked не запускался; pins остальных
пакетов сохранены. Миграция, реальные SELECT FOR UPDATE/SKIP LOCKED, lease recovery,
FIFO и SQL-привилегии не проверены PostgreSQL. Для них нужен disposable TEST_DATABASE_URL
и применение всех пяти миграций. Четыре старые миграции не изменены.
