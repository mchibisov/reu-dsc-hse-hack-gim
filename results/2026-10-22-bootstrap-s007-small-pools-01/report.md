# S007 — ограниченные пулы как в serverless

Состояние: успешно. Единственное отличие от полного прогона: все три fixture pool ограничены max_size=2 как в production drain. Проверяются новые latency/cancellation/empty regressions, не повторяется весь неизменённый код без причины.

`python -m pytest database/tests/test_dispatch_latency.py -q -s`: [5 passed in 4.45s](pytest.log). Ответ до release AI: 0.671/0.672с. Независимый review замечаний не нашёл; FIFO/lease сохранены. Реальные VK/Polza не вызываются.
