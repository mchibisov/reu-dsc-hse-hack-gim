# S003: SCRAM вместо trust

На disposable кластере localhost55439 проверен data_directory и включён только для него SCRAM-SHA256; operator test password сгенерирован и сохранён в игнорируемом runtime/test_auth.json, не попадает в отчёты/Git. [Скрипт](artifacts/enable_test_scram.py), [лог настройки](configure.log).
42shared tests прошли, включая `check-db` через три реальных LOGIN с отдельными паролями: [вывод](tests.log). Новый runtime не использует operator DSN.
Вывод: подтверждено на локальной PostgreSQL18.4; не облачная приёмка и не проверка Docker.

После проверок исходная exec-сессия сервера остановлена; последующий pg_ctl stop сообщил, что PID31364 уже отсутствует: [stop.log](stop.log). Пробный VK процесс31016 остаётся живым; тестовый кластер не был установлен как системная служба.
