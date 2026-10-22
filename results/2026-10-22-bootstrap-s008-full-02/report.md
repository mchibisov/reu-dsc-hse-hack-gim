# S008 — финальная проверка после review

Состояние: успешно. Причина повтора: review исправил порядок production rollout (остановка/завершение старых workers до миграции), добавлена защита prepare_question от stale retired template и проверка ранее отвеченного вопроса8. Миграция блокирует applications ACCESS EXCLUSIVE, чтобы начатая транзакция runtime завершилась до смены банка. Новая БД gim_s008_final, не перезапись применённой миграции.

Все private миграции и повтор exit0: [migrate.log](migrate.log), [migrate-repeat.log](migrate-repeat.log). `python -m pytest -q`: [204 passed in26.01s](pytest.log), без skip. [CLI](cli.log), compileall, [pip check](pip-check.log), [Compose config](compose.log) exit0. Сохранены старые ответы, проверен поздний ответ на skipped-вопрос, active bank18, полный диалог/экспорт и очередь S007.

Независимый review: найденный риск повторного созданияq8 старым worker после migration→deploy устранён описанием остановки/ожидания и возобновления; stale template также запрещён в Repository. docs/legacy-runtime теперь ссылается на snapshot вместо несуществующих файлов. Production не менялся: подключение Vercel/Supabase пока не подтверждено.
