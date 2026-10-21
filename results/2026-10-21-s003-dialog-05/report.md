# S003 dialog-05: расширенный контракт и conditional DB fixture

Предыдущая проверка dialog-04: 26 unit GREEN.
Изменено: явный loopback-only integration test; возрастной parse value стабилен на retry; XLSX emoji <UTF16 cell limit, XML-control strings JSON-encoded с field_encodings.
Команда: PYTHONPATH=database/src ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий: unit проходят; DB честно skipped без предоставленного локального TEST_DATABASE_URL.

Завершён кодом 0. Полный вывод artifacts/tests.txt; реальная PostgreSQL не проверялась без DSN.
