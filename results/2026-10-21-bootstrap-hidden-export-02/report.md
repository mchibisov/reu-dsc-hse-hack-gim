# S004: скрытая выгрузка, RED 02

- Дата: 2026-10-21, Europe/Moscow; завершён с отрицательным результатом.
- Предыдущая проверка: [01](../2026-10-21-bootstrap-hidden-export-01/report.md); исправлен аргумент fixture.
- Критерий и окружение: прежние, только synthetic SQLite/VK fake без сети.
- Команда из gim_bot: `.venv/Scripts/python.exe -m pytest tests/test_hidden_export.py -q -p no:cacheprovider --basetemp=runtime/pytest-hidden-red2`.
- Факт: 6 failed, 2 passed; код не создаёт запрос ни обычному пользователю, ни куратору. Ошибки аргумента больше нет.
- [Вывод pytest](artifacts/pytest.txt).
- Вывод: RED подтверждён, следующий шаг — реализация S004; реальная приёмка не выполнялась.
