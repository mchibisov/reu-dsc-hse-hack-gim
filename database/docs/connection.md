# Подключение и запуск компонента БД

## Созданный облачный стенд

- Проект: **gim-volunteers-mvp**, ref **bytwrnvnujzscfjfmdhm**.
- Организация Макса: **mchibisov's Org**. Регион: **eu-central-1 (Frankfurt)**. Тариф Free; стоимость создания, подтверждённая плагином: $0/месяц. Платные дополнения не подключались.
- [Dashboard](https://supabase.com/dashboard/project/bytwrnvnujzscfjfmdhm).
- API/Storage URL: `https://bytwrnvnujzscfjfmdhm.supabase.co`.
- Приватный bucket: `gim-private`; 20 МиБ; PDF, DOCX, XLSX, text/plain. Публичных Storage policies нет.
- PostgreSQL облака: 17.11. Применены четыре SQL-миграции из `supabase/migrations`; журнал с SHA-256 — `gim_meta.migrations`.

## 1. Получить подключение

В Dashboard → **Connect → Direct → Transaction pooler** доступны реальные параметры этого проекта:

```text
host: aws-1-eu-central-1.pooler.supabase.com
port: 6543
database: postgres
operator username: postgres.bytwrnvnujzscfjfmdhm
```

Пароль БД берётся у владельца проекта; он не является API-ключом. Не отправлять его в чат или Git. Подставить URL-encoded пароль:

```text
DATABASE_ADMIN_URL=postgresql://postgres.bytwrnvnujzscfjfmdhm:PASSWORD@aws-1-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require
```

Для миграций использовать **session pooler 5432** или прямое IPv6-подключение:

```text
postgresql://postgres:PASSWORD@db.bytwrnvnujzscfjfmdhm.supabase.co:5432/postgres?sslmode=require
```

Не включать платный IPv4 add-on: shared pooler подходит для IPv4. Session endpoint сверяется в Connect при настройке. Для runtime transaction mode на 6543 адаптер отключает prepared statements (`prepare_threshold=None`), использует короткие транзакции и не хранит session state. Общий пул на экземпляр bot=5, worker=5, publisher=2, staff=3 — стартовая настройка, не гарантия лимитов Free. При масштабировании суммировать пулы всех реплик и смотреть pg_stat_activity.

Скопировать `.env.example` в `.env`, заполнить секреты локально. В хранилище секретов сервера хранить отдельно operator, bot, worker и staff DSN. В рабочие контейнеры operator DSN не передаётся.

## 2. Создать сервисные LOGIN-роли

Миграции создают группы `gim_bot`, `gim_worker`, `gim_staff` без возможности входа. Это не готовые пароли. У каждой Python-службы — отдельный LOGIN с членством ровно в своей группе. Скрипт не выдаёт ADMIN OPTION.

Создать локальный файл `private/runtime-credentials.json` с правами 600 и тремя независимо сгенерированными паролями длиной >=24 символов:

```json
{
  "bot": {"login": "gim_bot_login", "password": "REPLACE_WITH_GENERATED_SECRET"},
  "worker": {"login": "gim_worker_login", "password": "REPLACE_WITH_ANOTHER_SECRET"},
  "staff": {"login": "gim_staff_login", "password": "REPLACE_WITH_THIRD_SECRET"}
}
```

```sh
uv sync --extra test --extra materials
uv run --env-file .env python scripts/provision_runtime.py private/runtime-credentials.json
```

Перед выполнением проверить ref хоста и права operator. Если LOGIN уже существует, скрипт остановится; неизвестные пароли не перезаписываются. После создания service DSN для pooler имеет вид `postgresql://gim_bot_login.bytwrnvnujzscfjfmdhm:PASSWORD@aws-1-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require`. Для worker/staff меняется только имя соответствующего LOGIN и его пароль. Проверить реальный вход каждой службой.

## 3. Применять следующие миграции

```sh
uv run --env-file .env python -m gim_db.migrate
```

Runner сверяет SHA-256, сериализует deployer advisory-lock и выполняет каждую миграцию транзакционно. Все четыре применённые облачные миграции уже зарегистрированы; повторный вызов их пропускает. Не редактировать применённые файлы. Новая миграция создаётся `supabase migration new NAME`, затем тестируется на чистом PostgreSQL. Для этого проекта использовать один runner; не запускать поверх него `supabase db push` без явного согласования истории `supabase_migrations` и `gim_meta`.

## 4. Настроить первое сообщество и вопросы

Проверенный VK ID первого администратора и настоящий group ID должен сообщить владелец VK-бота. Не брать их из пользовательского payload или произвольной кнопки.

```sh
uv run --env-file .env python scripts/bootstrap_admin.py --group-id GROUP_ID --verified-vk-id VERIFIED_ADMIN_VK_ID
```

Повторное создание первого администратора запрещено, если в сообществе уже есть активный сотрудник. Следующих сотрудников добавляет действующий администратор через `Repository.set_staff`.

Для оригинального банка: `scripts/load_materials.py --docx PATH --directions-pdf PATH --config PRIVATE_CONFIG.json`. Все три аргумента относятся к локальным закрытым файлам. Конфиг содержит group_id, title, questionnaire_version, rubric_version, rubric, direction_info, followup_policy. `rubric.criteria` — массив `{code, max_points, ...}`, `rubric.approved_by` и `rubric.scoring_rule` обязательны. `direction_info` содержит пять кодов `organizational`, `project`, `collections`, `inclusive`, `media` с реальными задачами из PDF. `followup_policy.max_followups` задаёт команда.

Загрузчик проверен на оригинале: 19 обязательных вопросов с вариантами ответов и 11 примеров уточнений. Создаёт **draft**, не открывает набор автоматически. Команда проверяет правила, формулу 0–3 и реальные задачи направлений. Оператор открывает набор `UPDATE gim.recruitments SET status='active',opened_at=now() WHERE id=...`. Банк и правила после этого не меняются; новый набор/версия создаются явно.

## 5. Storage

Bucket уже создан и проверен в Dashboard и SQL. Сервисный Storage key получить в настройках проекта и поместить **только** в backend secret `SUPABASE_STORAGE_KEY`. Publishable/anon key не подходит для привилегированной загрузки. Клиенты не получают service key.

```sh
uv run --env-file .env python scripts/ensure_storage.py
```

`PrivateStorage.upload` никогда не делает upsert. После загрузки и извлечения текста вызвать `FileRepository.finish` с фактическими SHA-256/размером. Готовые файлы неизменяемы; новая версия — новый object key. При повторе после падения сверяются байты существующего объекта. Метаданные Storage нельзя вручную создавать через SQL: используются Storage API и Dashboard.

Сотруднику ссылка выдаётся через `PrivateStorage.signed_url(staff_repo, verified_vk_id, file_id)` после серверной проверки активного членства. TTL 60 секунд, максимум 300. Уже выданная signed URL действует до истечения срока; для мгновенного отзыва нужен прокси скачивания с проверкой на каждый запрос. Полная HTTP-загрузка/скачивание через сервисный ключ в этом сеансе не проверялись — ключ не запрашивался и в код не включался.

## 6. Docker и обработчики команды

Supabase размещает PostgreSQL/файлы. Для Python и Redis нужен отдельный компьютер/сервер команды. Никакой платный хостинг не создавался.

```sh
docker compose --env-file .env up -d --build redis publisher
# После добавления team_handlers в Docker-образ:
docker compose --env-file .env --profile workers up -d --build worker
```

В образ команды добавить модуль из `GIM_HANDLERS_MODULE` с `HANDLERS` (см. contracts.md). Пустого успешного LLM-обработчика здесь нет: при отсутствующем модуле worker не запускается, а при отсутствии topic handler намерение остаётся незавершённым.

Для локального стенда `docker compose --env-file .env --profile local up -d db redis`; admin/service DSN внутри Docker используют host `db:5432`, порт хоста 55432 нужен только для локальных инструментов. `docker compose --profile tools run --rm migrate` применяет миграции. Затем создать service LOGIN и первого администратора операторскими скриптами. Секретный файл можно обрабатывать host Python через отдельный localhost operator DSN; он не встраивается в образ. В Compose Redis не публикуется наружу, AOF включён.

## Резервирование и восстановление

Издатель каждые 2 с проверяет outbox; незавершённые события повторно публикуются через 90 с. Redis loss не стирает вопросы, ответы, согласия, снимки или результаты. Остановить/запустить publisher и worker можно независимо. Для VK повторять сохранённый random_id; внешняя exactly-once доставка не гарантируется. Сетевой запрос, уже выполняющийся при отзыве сотрудника, нельзя отменить проверкой БД.

Резервирование данных и Storage требуется настроить отдельно: приватные `pg_dump --format=custom --schema=gim --schema=gim_meta` через operator session/direct connection и отдельная копия файлов через Storage API. Не считать тариф Free гарантией PITR/HA. Проверять восстановление на отдельной тестовой БД; дампы/файлы не класть в Git.

Источники технических ограничений: [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres), [Storage schema](https://supabase.com/docs/guides/storage/schema/design), [ARQ](https://arq-docs.helpmanual.io/).
