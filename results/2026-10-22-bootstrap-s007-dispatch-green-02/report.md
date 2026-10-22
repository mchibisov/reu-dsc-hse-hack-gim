# S007 — повтор после исправления SQL array

Состояние: успешно, 18 passed in 6.71s. Отличие от green-01: eligible topics передаются списком (psycopg text[]); TaskGroup отменяет sibling lanes при ошибке до освобождения общей аренды. Дополнены проверки пустой очереди и сбоя lane. Модель не меняется.

Команда: `python -m pytest database/tests/test_dispatch_latency.py database/tests/test_final_contracts.py -q -s`, [лог](pytest.log). Диалог во время одного анализа: 0.688с; во время трёх queued анализов: 0.672с. В обоих случаях reply отправлен до release AI. Короткий бюджет, пустая очередь, отмена siblings и прежние SQL-контракты успешны. Это локальная PostgreSQL, AI/VK — управляемые границы, не доказательство production SLA.
