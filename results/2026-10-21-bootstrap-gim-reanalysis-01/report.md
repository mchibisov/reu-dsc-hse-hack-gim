# Повтор анализа: RED

Проверяется явная повторная обработка no_analytics при уже завершённой старой задаче. Тест должен создавать новую durable задачу ровно один раз, сохранять ответы, не затрагивать processing/ready.

`pytest tests/test_worker.py -q --basetemp=runtime/backfill-red-01 -p no:cacheprovider`:1failed2passed; Store.requeue_analysis отсутствует. Запуск завершён, гипотеза об отсутствии функции подтверждена. Только тестовая SQLite, реальные анкеты не использовались.
