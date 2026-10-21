# S003 dialog-11: reject malformed saved snapshot

dialog-10 показал RED: неполный snapshot сохранялся как пустая XLSX.
Изменение: export требует все четыре реальных ключа до сериализации/Storage, не угадывает и не перечитывает live данные.
Команда: PYTHONPATH=database/src ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий: новый regression и предыдущие unit проходят; DB skipped до исправления загрузчика локальных миграций.

Завершён кодом 0. artifacts/tests.txt. Unit подтверждены только в синтетических условиях.
