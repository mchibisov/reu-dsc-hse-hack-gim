# VK-бот с общей БД, без Redis и LLM

Новый запуск использует код VK-клиента из ветки Vova и `Repository` из `max/database-mvp`: private schema `gim`, три роли, SQL outbox и файловое хранилище на диске. Старый `python -m gim.main` работает с другой public-схемой: для общей БД его не запускайте и `migrations/001_init.sql` к ней не применяйте.

## Что нужно от оператора БД

1. Применить новую миграцию `database/supabase/migrations/20261021170000_sql_runtime.sql`. Четыре предыдущие миграции не изменены. Для управляемого применения: установить `database`, задать `DATABASE_ADMIN_URL` только в операторском окружении, из `database/` выполнить `python -m gim_db.migrate`. Runtime не выполняет миграции.
2. Создать три разных LOGIN через `database/scripts/provision_runtime.py`: наследование только `gim_bot`, `gim_worker`, `gim_staff` соответственно; без SUPERUSER/BYPASSRLS. Инструкция — [подключение БД](database/docs/connection.md). Не передавать пароль postgres/оператора приложению.
3. Загрузить музейный банк вопросов/направлений и зарегистрировать сотрудника; активировать набор. Взять его `RECRUITMENT_ID`. Автоматически выдумывать вопросы и утверждённые критерии приложение не будет. Схема требует 18+, согласие и выбранное направление либо «не определился».

## Локально на Windows

1. Установить Python3.12 с `py` launcher, открыть `setup_shared.cmd`.
2. Заполнить созданный `.env` по `.env.shared.example`: `VK_TOKEN`, `VK_GROUP_ID`, `RECRUITMENT_ID`, `DATABASE_BOT_URL`, `DATABASE_WORKER_URL`, `DATABASE_STAFF_URL`. Для Supabase — отдельные service logins, SSL, transaction pooler6543; подробности в документации БД. Секреты в Git не попадут.
3. Остановить предыдущий Long Poll процесс для этого же сообщества. `run_shared.cmd` сначала проверяет БД, затем запускает gateway и четыре асинхронных воркера. Ctrl+C завершает процесс. Аренда gateway защищает только экземпляры нового runtime; прежний legacy poller нужно остановить отдельно.
4. Включить сообщения сообщества, Bots Long Poll с `message_new`, разрешить сообществу писать вашему аккаунту и отправить `/start`.

Вручную: `.venv\Scripts\python.exe -m gim.shared_main check-db`, затем `check-vk` или `run`. На Linux/macOS: `python -m venv .venv`, активировать окружение, `pip install -r requirements.shared.txt`, заполнить `.env`, `python -m gim.shared_main run`.

## Сервер

`docker compose -f compose.shared.yaml up --build -d` запускает gateway и worker отдельно, PostgreSQL берётся из трёх DSN. Redis, LLM API и публичные HTTP-порты не нужны. XLSX лежат в закрытом volume `shared_files`; резервируйте его вместе с БД. Облачный Storage не используется этим runtime. Контейнеры здесь не проверены: локально Docker отсутствует.

## Поведение

Кандидат проходит основные вопросы из БД и до трёх библиотечных уточнений по прошлому опыту. Ответы сохраняются до продолжения; повтор VK-события не превращается в ответ на следующий вопрос. После завершения — подтверждение подачи. Никаких фиктивных баллов или саммари: оценок нет, они отображаются как «не оценена».

Активный сотрудник своего сообщества: `/admin`, `/top`, `/stats`, `/application UUID` (алиас `/candidate UUID`), `/export [UUID]`. Выгрузка XLSX содержит четыре листа контракта БД и точные исходные ответы; длинные ответы продолжаются в следующих строках. Корректировка оценок, резюме и PDF не входят в этот запуск. Уведомления и Excel требуют, чтобы сотрудник разрешил сообщения сообщества.

Автоматическое удаление персональных данных и неизменяемой истории пока не реализовано; `/delete` объясняет обращение к оператору, не подтверждает фиктивное удаление. Длительность5–7мин и90 одновременно работающих пользователей не подтверждены этой интеграцией.

## Проверка

`pip install -r requirements.shared.txt pytest pytest-asyncio`, затем `python -m unittest discover -s tests -p 'test_shared*.py' -v` и из `database/` — `python -m pytest`.
Реальные DB-тесты требуют отдельную локальную `TEST_DATABASE_URL` с уже применёнными private миграциями; содержат только synthetic fixtures. Не указывайте production БД. Legacy tests с `test_service.py` требуют отдельную public test БД, не смешивайте DSN.
Результаты и ограничения — [план S003](docs/plans/S003-shared-db-integration.md), каталог `results/`.
