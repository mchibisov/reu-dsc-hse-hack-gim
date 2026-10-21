# S003 SQL — запуск 02

Вопрос: удалена ли внешняя очередь из зависимостей нового runtime?
Критерий: pyproject без arq/redis и новая миграция SQL runtime.
Команда: `pytest -q database/tests/test_sql_runtime.py -k no_external_queue`.
Результат: 1 failed, 4 deselected; assert обнаружил arq в dependencies, ожидаемый RED.
Вывод: гипотеза опровергнута до реализации; состояние завершён.
Доказательство: [pytest.txt](artifacts/pytest.txt). Следующий шаг: заменить executor, зависимости и миграцию.
