# S006 — чистые миграции и SQL-тесты

Состояние: успешно. Одноразовая PostgreSQL 18.4, loopback 55439. Рабочая БД не используется. Проверяются чистое применение и повторное применение миграций, затем SQL-контракты. Предыдущие проверки — docs/evaluation-report.md и output/FINAL_STATUS.md; повтор нужен для новой среды и пустой БД.

Команды: `MIGRATIONS_DIR=database/supabase/migrations python -m gim_db.migrate` два раза, затем `python -m pytest database/tests -q`. Оба применения exit 0 ([первое](migrate.log), [повтор](migrate-repeat.log)); [52 passed in 7.47s](pytest.log). Покрыты ACL, цитаты, очередь/аренды, 50 синтетических кандидатов, immutable файлы и архив. Это локальная SQL-проверка; не реальная VK/LLM нагрузка и не экспертная точность.
