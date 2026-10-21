# S003 dialog-04: immutable XLSX retry

В dialog-03 найден отрицательный результат: openpyxl заменяет modified timestamp при save; фиксированного ZIP времени недостаточно.
Изменение: нормализация docProps/core.xml modified на постоянную дату после сохранения.
Команда: PYTHONPATH=database/src ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий: в том числе байты двух экспортов через 1.1 секунды идентичны.

Завершён кодом 0. Полный вывод artifacts/tests.txt. Ограничение: unit без PostgreSQL/VK.
