# S003 dialog-02: реализация и unit проверка

Предыдущий RED: ../2026-10-21-s003-dialog-01/report.md, ожидаемый отсутствующий модуль.
Изменено: SharedService, parse/plan helpers, snapshot XLSX; внешние API/DSN не используются.
Команда: PYTHONPATH=database/src ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий: все синтетические контрактные тесты проходят.
Состояние: выполняется.

Завершён кодом 0, полный вывод artifacts/tests.txt. Локальный fake-контракт не заменяет DB/VK приёмку.
