# S003 gateway: запуск остановлен

Проверка начата на локальной PostgreSQL18.4. Асинхронный пул не подключился из Windows ProactorEventLoop, при этом sync psycopg SELECT работал. Вывод: недостаточно данных, запуск остановлен; это не успешная проверка gateway. [Лог](tests.log).
Исправление: SelectorEventLoop для Windows runtime и тестов. Параллельная DB-проверка также выявила чтение UTF8 SQL как cp1251; миграционный loader исправлен отдельно.
