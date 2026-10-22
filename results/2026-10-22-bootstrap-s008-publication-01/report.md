# S008 — публикация и проверка CI

Snapshot working-version-2026-10-22 указывает на 7d06b60ceae3d6bb6976cd274bbb4da5fc805b59 (проверен peeled tag); опубликован до очистки. Изменения анкеты/очистка опубликованы в main: 60d32a346253a2ba71b3f1bec2f3088700395a4a.

Первый CI: [Tests success](https://github.com/mchibisov/reu-dsc-hse-hack-gim/actions/runs/39704520815); [database failure](https://github.com/mchibisov/reu-dsc-hse-hack-gim/actions/runs/39704520831). В database успешно прошли private миграции, SQL pytest, shared unittest, две Docker-сборки, packaged rubric и image entry point. Единственная ошибка — Verify Compose: `env file .../.env not found`. В чистом checkout нет приватного .env; флаг --no-env-resolution на runner не устранил проверку существования файла.

Исправление: CI копирует публичный .env.example в тестовый .env перед стандартным `docker compose ... config --quiet`. Секреты не используются. Повтор CI ожидается.

При необязательной очистке Python-кэшей первая команда PowerShell была отклонена парсером до выполнения: `An empty pipe element is not allowed`. Ни один файл этой командой не изменён.
