# Повтор анализа: SQL NULL и JSON null

Первое исправление с analysis IS NULL отклоняло сохранённый SQLAlchemy JSON null. `pytest tests/test_worker.py -q --basetemp=runtime/backfill-green-02 -p no:cacheprovider`:1failed2passed. Запуск завершён, первая реализация опровергнута.

Исправлено условием SQL NULL OR JSON.NULL, атомарное обновление статуса и новая задача в одной транзакции, отдельный UUID исключает столкновение со старой done задачей. Итоговый полный прогон описан в Polza-05:72passed1skipped. Повторный вызов не ставит вторую задачу; ответы сохраняются. Операторский scripts/reanalyze.py без --apply только показывает технические ID.
