# Подготовка новой БД и первого запуска

Инструкция для оператора, из корня репозитория. Не выполнять создание ролей/набора на существующем рабочем проекте ради теста. Для разработки используйте отдельную БД и отдельное сообщество VK.

## 1. Зависимости и приватные файлы

После создания `.venv` и установки `requirements.shared.txt`:

```sh
python -m pip install -e './database[materials]'
mkdir -p runtime/materials
```

Поместите исходную музейную анкету DOCX в `runtime/materials/questionnaire.docx`, PDF пяти направлений — в `runtime/materials/directions.pdf`. Загрузчик ожидает музейную анкету из кейса: 19 основных вопросов и 11 примеров уточнений. Исторические персональные анкеты не нужны. Документы и заполненные конфиги не публикуются в Git.

Создайте отдельную PostgreSQL/Supabase БД. Возьмите операторский DSN из Connect своего проекта; для миграций используйте direct/session connection, поддерживающее сессию и advisory lock. В Supabase включите SSL. Не подставляйте адрес чужого проекта из старой документации.

Задайте `DATABASE_ADMIN_URL` только в текущем операторском терминале. Не вводите секрет буквально в команду, сохраняющуюся в истории. Например, в Bash/macOS:

```sh
read -r -s DATABASE_ADMIN_URL
export DATABASE_ADMIN_URL
```

После `read` вставьте DSN и нажмите Enter: ввод скрыт. В Windows задайте переменную только для операторского процесса через свой менеджер секретов; команды ниже выполняйте без вывода её значения. Не демонстрируйте терминал с секретами на видео.

## 2. Применить миграции

Из корня проекта:

```sh
MIGRATIONS_DIR=database/supabase/migrations python -m gim_db.migrate
```

Для PowerShell задайте `$env:MIGRATIONS_DIR = 'database/supabase/migrations'`, затем `python -m gim_db.migrate`.

Применяются **все SQL-файлы каталога в порядке имён**, а не фиксированное старое количество. Runner хранит SHA-256 в `gim_meta.migrations`, повторно применённые файлы пропускает и отклоняет изменение их содержимого. Корневые `migrations/` относятся к другой старой схеме.

## 3. Создать три ограниченных LOGIN

Создайте `runtime/runtime-credentials.json` с тремя разными случайными паролями длиной не менее 24 символов. Пример структуры — значения обязательно заменить:

```json
{
  "bot": {"login": "gim_bot_login", "password": "REPLACE_WITH_RANDOM_SECRET_AT_LEAST_24_CHARS"},
  "worker": {"login": "gim_worker_login", "password": "REPLACE_WITH_ANOTHER_RANDOM_SECRET_24_CHARS"},
  "staff": {"login": "gim_staff_login", "password": "REPLACE_WITH_THIRD_RANDOM_SECRET_24_CHARS"}
}
```

На macOS/Linux ограничьте доступ: `chmod 600 runtime/runtime-credentials.json`.

```sh
python database/scripts/provision_runtime.py runtime/runtime-credentials.json
```

Скрипт создаёт LOGIN с членством в одной соответствующей группе `gim_bot` / `gim_worker` / `gim_staff`; существующие LOGIN не перезаписывает. Составьте три DSN для этих LOGIN по параметрам своего Connect, URL-кодируя пароль. У pooler Supabase имя пользователя может включать суффикс `.PROJECT_REF`; используйте параметры своего проекта, а не ID демонстрационной БД. Runtime не должен подключаться как postgres или с BYPASSRLS.

## 4. Подготовить конфигурацию музейного набора

Создайте `runtime/recruitment.json`. Возьмите `rubric` и `version` из `config/ranking-50-35-15.json`. Пример заполнения структуры:

```json
{
  "group_id": 123456789,
  "title": "Волонтёры ГИМ — тестовый набор",
  "questionnaire_version": "museum-v1",
  "rubric_version": "gim-ranking-50-35-15-v1",
  "rubric": {
    "approved_by": "mchibisov: formula supplied 2026-10-22",
    "scoring_method": "binary_50_35_15",
    "scoring_rule": "S = 3 × (0.50 × max(0, Σm − p)/4 + 0.35 × Σe/5 + 0.15 × Σa/2), p=1 только при исключительном интересе к фондам И отказе от альтернатив. Целый балл округляется 0.5 вверх; рейтинг сортируется по S.",
    "criteria": [
      {
        "code": "motivation",
        "name": "Мотивация и осознанность",
        "max_points": 1.5
      },
      {
        "code": "experience",
        "name": "Опыт и навыки",
        "max_points": 1.05
      },
      {
        "code": "availability",
        "name": "Обучение и нагрузка",
        "max_points": 0.45
      }
    ]
  },
  "direction_info": {
    "organizational": "ЗАМЕНИТЬ: реальные задачи и ограничения организационного направления из PDF",
    "project": "ЗАМЕНИТЬ: реальные задачи и ограничения проектного направления из PDF",
    "collections": "ЗАМЕНИТЬ: реальные задачи и ограничения фондового направления из PDF",
    "inclusive": "ЗАМЕНИТЬ: реальные задачи и ограничения инклюзивного направления из PDF",
    "media": "ЗАМЕНИТЬ: реальные задачи и ограничения медиа из PDF"
  },
  "followup_policy": {"max_followups": 3}
}
```

Это шаблон, **не готовые музейные данные**: замените group_id своим числовым ID, все описания — проверенными текстами из материалов музея. Значения direction_info — строки. Веса формулы заданы командой/пользователем, не выдавайте их за официальное утверждение музея. Не меняйте frozen-правила действующего набора.

```sh
python database/scripts/load_materials.py --docx runtime/materials/questionnaire.docx --directions-pdf runtime/materials/directions.pdf --config runtime/recruitment.json
```

Скрипт напечатает UUID `recruitment_id` и создаст **draft**. Сохраните UUID для `.env`. Проверьте загруженные вопросы и описания до активации.

## 5. Назначить первого администратора и активировать набор

Проверьте принадлежность VK ID сотруднику. В следующей команде замените оба числовых примера своими ID:

```sh
python database/scripts/bootstrap_admin.py --group-id 123456789 --verified-vk-id 987654321
```

Bootstrap откажется повторно создавать первого администратора при наличии активных сотрудников. Последующих сотрудников назначает действующий администратор через защищённый `Repository.set_staff`; произвольный пользователь не может получить роль сообщением боту.

В SQL Editor **своего** проекта выполните, подставив UUID только что созданного набора:

```sql
UPDATE gim.recruitments
SET status = 'active', opened_at = now()
WHERE id = 'REPLACE_WITH_RECRUITMENT_UUID'::uuid AND status = 'draft'
RETURNING id, group_id, status;
```

Вставьте UUID в `RECRUITMENT_ID` локального `.env`; задайте тот же `VK_GROUP_ID`. Заполните три runtime DSN, VK-токен и ключ Polza по README. Уберите операторский DSN из терминала: `unset DATABASE_ADMIN_URL` (PowerShell: `Remove-Item Env:DATABASE_ADMIN_URL`). Не передавайте его runtime.

## 6. Выбрать один транспорт

- **Docker / Long Poll:** настройте сообщения, возможности ботов и Long Poll `message_new` в своём сообществе; выполните `check-db`, `check-vk`, затем `docker compose up --build -d` из README.
- **Vercel / Callback:** выполните [облачную инструкцию](deployment-guide.md). Для этого режима нужны pg_net, pg_cron, Vault и отдельные секреты Callback/worker. Docker gateway/worker одновременно не запускайте.

Если переносите действующего бота, сначала сделайте резервную копию и подготовьте новый образ, затем согласованно переключите один транспорт. Не удаляйте незавершённые анкеты, очередь или Docker volume.

## 7. Проверить результат

1. Кандидат открывает диалог, принимает согласие, проходит анкету, ожидания и персональные уточнения.
2. Администратор получает «+1 анкета», затем готовый AI-анализ; `/application UUID` открывает профиль и цитаты.
3. `/export UUID` доставляет XLSX; откройте все пять листов и проверьте ответы/баллы.
4. `/reset` → `/reset confirm` создаёт новую собственную тестовую попытку, сохраняя прежнюю в архиве.
5. Проверьте `/jobs`; при ошибке LLM анкета должна остаться сохранённой без фиктивного балла.

`check-db`, unit tests и `/health` не доказывают реальную доставку VK или успешный анализ Polza. Чистый запуск на вашей инфраструктуре считается принятым только после этого сценария.
