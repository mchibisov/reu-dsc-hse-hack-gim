# S003 SQL — запуск 09

Вопрос: почему test_real_login_provisioning child Python возвращает exit 1?
Метод: без подключения к БД сравнить `import psycopg` в дочернем процессе
с PATH-only (как в исходном тесте) и с белым списком Windows runtime variables.
Команда и воспроизводимый скрипт: [check_subprocess.py](artifacts/check_subprocess.py).
Результат: PATH-only — exit 1, WinError10106 при import asyncio/_overlapped;
PATH/SYSTEMROOT/WINDIR/TEMP/TMP — exit 0, imported.
Состояние: завершён; причина подтверждена в проверенных условиях.
Доказательство: [diagnostic.txt](artifacts/diagnostic.txt).
Исправление с разрешения родителя: test_access.py передаёт только этот белый список
и DATABASE_ADMIN_URL, а не полное окружение с потенциальными ключами.
Предварительная диагностическая печать stderr как Unicode отдельно дала ошибку
cp1251 UnicodeEncodeError, поэтому доказательство печатает ascii(bytes).
Ограничение: provisioning заново не запускался до готовности пересозданной тестовой БД.
