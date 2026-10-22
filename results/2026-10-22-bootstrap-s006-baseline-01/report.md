# S006 — исходные тесты приложения

Состояние: завершено с ошибкой. Python 3.12.14, чистая venv, main 3f95b67. TEST_DATABASE_URL не задан: ожидаются явные пропуски DB-тестов. Проверяются unit-контракты перед исправлениями. Артефакт: [unittest.log](unittest.log).

Команда: `python -m unittest discover -s tests -v`. 190 тестов, 37 skip; 1 error: `EnvironmentTests.test_dotenv_loads_without_overriding_deployment_environment`, UnicodeDecodeError. Причина: fixture записывала русскую строку default cp1251, а загрузчик правильно читал UTF-8. Это дефект теста, не основание ослаблять формат .env. Следующий шаг: явный UTF-8 в fixture и регрессии для остальных пользовательских конфигов.
