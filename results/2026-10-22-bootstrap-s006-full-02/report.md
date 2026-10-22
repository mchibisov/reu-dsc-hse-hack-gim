# S006 — повтор полного pytest после настройки обнаружения

Состояние: успешно. Предыдущий bare pytest собрал 246 тестов, но 47 async SQL tests упали: корневой запуск не читает asyncio_mode из database/pyproject.toml. Добавлен корневой pytest.ini с asyncio_mode=auto и обоими каталогами тестов. Исправлена очистка временных LOGIN по независимому review. Повтор проверяет весь набор и устраняет неопределённость полного запуска.

`TEST_DATABASE_URL` указывает только одноразовую локальную PostgreSQL, `REAL_POSTGRES_TESTS=1`, `PYTHONIOENCODING=utf-8` (кодировку чтения файлов это не меняет).

`python -m pytest -q`: [246 passed in 21.32s](pytest.log), без пропусков и предупреждений. Включены 191 тест приложения и 55 БД. `python -m pip check`: [зависимости согласованы](pip-check.log). `python -m compileall -q gim database/src database/scripts api`: exit 0. [CLI --help](cli.log) и [Compose config --no-env-resolution --quiet](compose.log) exit 0; `git diff --check` чистый.

Независимый review выявил отсутствие config/ в root Dockerfile и неочищенные временные LOGIN нового теста. Оба замечания устранены. Локальная Docker-сборка недоступна (Engine HTTP 500); для образов добавлен CI build/smoke. Production VK/LLM, человеческая мобильная приёмка и экспертное качество этим прогоном не проверены. Итог по критериям: [отчёт](../../output/S006_IT_REPORT.md).
