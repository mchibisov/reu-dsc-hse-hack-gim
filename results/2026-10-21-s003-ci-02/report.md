# S003: CI-команды из database/, локальный ACL temp

Повтор migrate через frozen окружение: код0, ранее применённые миграции не изменены: [лог](migrate.log).
Database pytest:33passed,3setup errors из-за WinError5 на общем `Temp/pytest-of-User`: [лог](database-tests.log). Конфликт локальных прав временного каталога; следующие проверки используют отдельный basetemp внутри игнорируемого runtime.
Это не успешная полная suite; в предыдущем sql-10 на другой dev среде36passed. Ограничение текущего запуска сохранено отдельно.
