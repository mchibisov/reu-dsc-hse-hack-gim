# S003 dialog-03: crash/ACL/export boundary

Повтор после dialog-02: добавлены replay непосредственно после record_answer, SQL binding lease CAS, staff revoke перед отправкой, ready-file reuse и deterministic bytes тест.
Команда: PYTHONPATH=database/src ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Состояние: запущен; все данные синтетические, без сети/DSN.

Завершён, код 1. Вывод сохранён artifacts/tests.txt.
