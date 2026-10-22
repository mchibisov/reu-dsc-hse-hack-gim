# Запуск на macOS, Linux и Windows через Docker

Один сценарий для всех ОС: Python и PostgreSQL на компьютере устанавливать не нужно. Docker поднимает отдельную PostgreSQL, применяет миграции, загружает 18 музейных вопросов и 11 библиотечных уточнений, создаёт три ограниченных подключения и первого администратора. Исторические анкеты и документы из Downloads не нужны.

## 1. Установить Docker

- **macOS:** Docker Desktop для Apple Silicon или Intel, запустить приложение.
- **Windows 10/11:** Docker Desktop с WSL 2, режим Linux containers; запустить приложение. Команды выполнять в PowerShell.
- **Linux:** Docker Engine и плагин Compose v2 либо Docker Desktop.

Проверка: `docker version` и `docker compose version`. Docker должен быть запущен.

## 2. Получить проект и параметры

Склонируйте репозиторий либо скачайте ZIP ветки main и распакуйте:

```sh
git clone https://github.com/mchibisov/reu-dsc-hse-hack-gim.git
cd reu-dsc-hse-hack-gim
```

В собственном сообществе VK включите сообщения, возможности ботов и Bots Long Poll с событием `message_new`. Создайте токен сообщества с доступом к сообщениям, документам, фотографиям и управлению сообществом для API Long Poll. Не запускайте этот режим для сообщества, которое уже обслуживается облачным Callback: используйте отдельное тестовое сообщество.

Создайте файл настроек:

**macOS / Linux:** `cp .env.quickstart.example .env.quickstart`

**Windows PowerShell:** `Copy-Item .env.quickstart.example .env.quickstart`

Откройте `.env.quickstart` в редакторе и заполните:

| Поле | Что указать |
|---|---|
| `VK_GROUP_ID` | Числовой ID своего сообщества без минуса |
| `VK_TOKEN` | Токен этого сообщества |
| `ADMIN_VK_ID` | Проверенный числовой VK ID первого администратора |
| `LLM_API_KEY` | Ключ Polza для DeepSeek |
| `POSTGRES_PASSWORD` | Свой случайный пароль не короче 24 символов |
| `EXCEL_ACCESS_CODE` | Необязательно: секрет для отдельного доступа только к Excel |

Имена, пароли ролей и UUID набора Docker создаёт сам. Пароль PostgreSQL после первого запуска не меняйте простым редактированием файла: он уже сохранён в БД. Заполненный файл не публикуйте. Для локальной проверки схема использует публичные незаполненные вопросы кейса; правовое основание и текст согласия при передаче в музей проверяет владелец программы.

## 3. Запустить

Одинаковая команда на трёх ОС, из корня проекта:

```sh
docker compose --env-file .env.quickstart -f compose.quickstart.yaml up --build -d
```

Первый запуск скачивает образы и зависимости. Последующие запуски используют сохранённую БД. Проверка:

```sh
docker compose --env-file .env.quickstart -f compose.quickstart.yaml ps -a
docker compose --env-file .env.quickstart -f compose.quickstart.yaml logs --tail=40 setup bot
```

Нормальное состояние: `postgres` — healthy, `setup` — Exited (0), `bot` — Up. `setup` завершается после успешной подготовки — это штатно.

Откройте `https://vk.me/clubВАШ_GROUP_ID`, разрешите сообщения и нажмите «Начать». Первый администратор из `ADMIN_VK_ID` отправляет `/admin`.

## 4. Проверить анкету и Excel

Пройдите согласие, 18 вопросов, проверку ожиданий и до трёх уточнений. Администратору приходят «+1 анкета» и результат анализа. `/top` открывает рейтинг, `/application UUID` — доказательную карточку, `/export` — Excel вложением в VK.

Проверки без запуска второго бота:

```sh
docker compose --env-file .env.quickstart -f compose.quickstart.yaml run --rm bot python -m gim.local_setup check-db
docker compose --env-file .env.quickstart -f compose.quickstart.yaml run --rm bot python -m gim.local_setup check-vk
```

Без ключа Polza анкета сохраняется, но AI-оценка не появляется. С ключом используется `deepseek/deepseek-v4.1-flash-1017`; искусственный ноль при сбое не выставляется.

## 5. Остановка, перезапуск, обновление

```sh
docker compose --env-file .env.quickstart -f compose.quickstart.yaml down
docker compose --env-file .env.quickstart -f compose.quickstart.yaml up -d
```

Данные остаются в трёх volumes: БД, закрытая конфигурация ограниченных ролей, Excel. **Не используйте `down -v`: это удаляет данные.** База не публикует порт на компьютере. Бот не получает операторский пароль PostgreSQL; его корневая файловая система доступна только для чтения.

Перед обновлением сохраните резервную копию БД, конфигурационный volume и `.env.quickstart`; затем обновите код и выполните исходную команду с `--build`. Повторный setup применяет только новые проверенные миграции и не создаёт второй набор, не меняет администратора и не стирает ответы. Изменение VK ID на существующей установке отклоняется.

Для долгосрочного музейного сервера: [передача проекта ГИМ](transfer-to-gim.md). Для готовой внешней Supabase вместо локальной БД остаётся прежний [расширенный запуск](setup-from-scratch.md) и `compose.yaml`.
