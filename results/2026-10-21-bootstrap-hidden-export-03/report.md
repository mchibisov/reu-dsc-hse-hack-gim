# S004: скрытая выгрузка, GREEN 03

- Дата: 2026-10-21, Europe/Moscow; завершён.
- Предыдущая проверка: [02](../2026-10-21-bootstrap-hidden-export-02/report.md); добавлены скрытый router, durable попытки/разрешения и проверки worker.
- Критерий: пройти 8 ранее подготовленных сценариев S004.
- Команда из gim_bot: `.venv/Scripts/python.exe -m pytest tests/test_hidden_export.py -q -p no:cacheprovider --basetemp=runtime/pytest-hidden-green`.
- Факт: 8 passed, [вывод](artifacts/pytest-targeted.txt).
- Вывод: подтверждено в локальных synthetic условиях; ещё нужны пограничные проверки rate limiter и full regression. Сеть, реальный процесс и база не затронуты.
