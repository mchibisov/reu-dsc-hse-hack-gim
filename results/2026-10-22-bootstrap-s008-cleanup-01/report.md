# S008 — удаление дублирующего runtime

Состояние: завершено, активный runtime проверен полным прогоном. До удаления опубликован working-version-2026-10-22 / 7d06b60. По графу импортов main использует shared_main/serverless, private Repository и shared_*; public runtime и его единственные потребители-тесты выделены отдельно. Удалено28 восстановимых tracked-файлов legacy и дублей Docker/Compose/README/env. Данные, .venv, результаты экспериментов и активная DB-схема сохранены.

Остаточные legacy Settings и LLM.next_question/evaluate вырезаются фиксированным cleanup.py; актуальный complete, VK, model и рубрика не меняются. CI переводится на единственный runtime. Полный список удалений — git diff --name-status относительно сохранённой метки.

[changes.txt](changes.txt) сохраняет diff; поиск imports удалённых модулей в актуальных gim/tests/scripts/database не нашёл ссылок. Проверка нового runtime — S008 full-02,204 passed. Удалённые legacy-модули восстанавливаются из snapshot; исторические scripts в results воспроизводятся на соответствующем старом коде.

Дополнение: после всех Python-проверок удалены7 каталогов генерируемых __pycache__/.pytest_cache только внутри актуальных исходников/тестов; [список](caches.log). .venv, .git, runtime/data и секреты не затронуты. Временный PostgreSQL остановлен штатно (pg_ctl fast stop, exit0).
