# S004: скрытая выгрузка, RED 01

- Дата: 2026-10-21, Europe/Moscow; запуск завершён с отрицательным результатом.
- Критерий до проверки: скрытая команда создаёт одноразовый запрос без изменения анкеты; replay, неверный код и ротация не выдают повторный/неразрешённый файл.
- Окружение: Windows, локальная SQLite на synthetic данных, рабочая ветка codex/gim-mvp, `.venv/Scripts/python.exe`.
- Команда из gim_bot: `.venv/Scripts/python.exe -m pytest tests/test_hidden_export.py -q -p no:cacheprovider --basetemp=runtime/pytest-hidden-red`.
- Факт: 6 failed, 2 passed. Главный тест получил 0 запросов вместо 1: скрытой команды ещё нет. В одном тесте обнаружена ошибка аргумента fixture (`user_id` вместо `uid`); её исправление проверяется отдельно.
- Доказательство: [pytest.txt](artifacts/pytest.txt).
- Вывод: требования пока не реализованы; реальные VK, .env, база и процесс не затронуты.
