# S003 dialog-01: контракт SharedService

Цель: fake Repository без DSN проверяет replay, сохранение raw и prepare-before-send, закрытый staff и неизменный XLSX.
Команда: ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Окружение: локальная Windows, синтетические данные; внешний API и БД не вызываются.
Критерий: тесты сначала показывают отсутствие нового модуля, затем после реализации проходят.
Состояние: подготовлен RED-запуск.

RED завершён, код 1. Проверяемый модуль отсутствует; ожидаемый ModuleNotFoundError сохранён в artifacts/tests.txt. Вывод: недостаточно данных до реализации.
