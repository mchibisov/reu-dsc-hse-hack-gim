# S003: frozen uv, неправильный каталог pytest

`uv sync --frozen --extra test --extra materials --project database` успешен: [лог](sync.log).
Запуск `uv run --project database pytest` из корня собрал root tests вместо database suite и получил12 import errors: [лог](database-tests.log). Это ошибка команды запуска; рабочий каталог CI явно `database/`.
Отдельный корректный root shared unittest из uv окружения успешен:42tests, [лог](shared-tests.log). Отрицательный запуск не заменяет проверку database suite.
