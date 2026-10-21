# S003 gateway: RED

Критерий: одна аренда gateway на группу, атомарный batch+cursor, повтор события без дублирования, устаревший токен не изменяет checkpoint.
Запуск на отдельной localhost PostgreSQL18.4, ожидаемая ошибка отсутствующего модуля `gim.shared_gateway`. [Вывод](tests.log).
