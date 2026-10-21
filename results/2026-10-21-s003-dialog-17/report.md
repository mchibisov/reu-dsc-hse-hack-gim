# S003 dialog-17: past experience AND allowed direction

dialog-16 подтвердил RED: directed interest выбирался даже при experience=«нет».
Изменение: past AND has_experience AND (unrestricted OR selected direction); отрицательные «нет/опыта нет/не применимо» не служат основанием. Точный library text не меняется; допустимо 0 уточнений.
Команда: PYTHONPATH=database/src TEST_DATABASE_URL=<local-test-server> ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий: 32 unit/DB tests GREEN; DB past followups с описанным опытом остаются тремя, без опыта/с interest вопросом — ноль.

Завершён кодом 0, artifacts/tests.txt. Отдельная local PostgreSQL, SET ROLE, mocked VK/Storage; cloud не проверялся.
