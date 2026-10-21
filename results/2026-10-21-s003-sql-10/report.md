# S003 SQL — запуск 10

Цель: полный регрессионный набор database после Windows-исправлений и пересоздания
изолированной тестовой БД с UTF-8 загрузчиком миграций.
Окружение: PostgreSQL 18.4 localhost:55439/gim_private_test, TEST_DATABASE_URL задан
явно, пять миграций применены родителем, PYTHONPATH=database/src,
Python gim_bot/.venv. Никакая иная БД/облако/VK/модель не использовались.

Изменения с 08: родитель исправил чтение SQL UTF-8 в migrate.py и пересоздал только
тестовую БД; test_access передаёт Windows runtime variables дочернему Python
по белому списку. Selector event loop уже включён с запуска 07.

Команда: `pytest -q database/tests`.
Результат: 36 passed, 5.74s; 0 failed, 0 skipped; состояние завершён.
Вывод: подтверждена в проверенных условиях полная локальная регрессия database,
включая SQLQueue lease/fencing/retry/FIFO, работу backend ролей, 13 private tables,
точный сохранённый вопрос, атомарную запись оценки, revocation и экспорт.
Доказательство: [pytest.txt](artifacts/pytest.txt).
Ограничение: локальный PostgreSQL не доказывает облачные DSN, настоящий VK,
работоспособность live набора или модель; сетевые внешние вызовы не выполнялись.
