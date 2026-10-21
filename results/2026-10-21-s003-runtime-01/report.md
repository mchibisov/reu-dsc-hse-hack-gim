# S003 runtime: RED

Вопрос: отдельные runtime logins, явная ошибка отсутствующей конфигурации и неизменяемое локальное хранилище без выхода за корневую папку.

Команда: `python -m unittest discover -s tests -p test_shared_runtime.py -v`.
Результат: ожидаемая ошибка импорта `gim.shared_config`, модуль ещё не реализован. [Вывод](tests.log).
Вывод: проверка начата; PostgreSQL и живой VK этим запуском не проверены.
