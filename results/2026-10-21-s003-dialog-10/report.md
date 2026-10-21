# S003 dialog-10: incomplete snapshot must fail closed

dialog-09: БД snapshot содержит 22 ответа, но имена SQL ключей повреждены загрузчиком миграций (UTF8 интерпретирован как cp1251).
Гипотеза: SharedService обязан остановить неполный/повреждённый snapshot до upload, иначе пустая выгрузка маскирует потерю данных.
Команда: PYTHONPATH=database/src ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий RED: новый тест incomplete snapshot падает до добавления проверки.

Завершён кодом 1. Ожидаемый RED отражён в artifacts/tests.txt; DB не вызывается.
