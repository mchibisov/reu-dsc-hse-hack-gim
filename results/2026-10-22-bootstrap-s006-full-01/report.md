# S006 — полный прогон приложения и SQL

Состояние: завершено с найденным дефектом конфигурации тестов. PostgreSQL только локальная одноразовая. Private миграции применены и 52 теста прошли. Добавляются legacy public migrations, чтобы включить ранее пропущенные DB-тесты; на production это не требуется. Повтор после исправления UTF-8/BOM. Логи рядом с отчётом.

Первая inline-команда подготовки legacy получила SyntaxError из-за shell quoting: [legacy-migrate.log](legacy-migrate.log), БД не изменилась. Команда заменена отдельным [скриптом](legacy_migrate.py); подготовка прошла, [лог](legacy-migrate-02.log).

`python -m unittest discover -s tests -v`: [191 tests OK](unittest.log), без skip. Полный SQL-диалог, права и XLSX включены.

`python -m pytest -q`: [47 failed, 199 passed](pytest-all.log). Все 47 ошибок: async functions are not natively supported — root pytest не использовал asyncio_mode вложенного database/pyproject.toml. Это не 47 подтверждённых ошибок продукта: async-тесты не исполнялись. Следующий шаг: корневой pytest.ini с auto и повтор всего набора.
