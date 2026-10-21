# Старый runtime public-схемы

Сохранён для совместимости: `gim.main`, корневые `migrations/`, `compose.legacy.yaml`, `compose.external.yaml`, `Dockerfile.legacy`, `.env.legacy.example`.

Это отдельная схема с `DATABASE_URL`. Не применяйте эти миграции к основной private БД и не запускайте старый gateway одновременно с новым для одного сообщества.

Текущая версия использует `python -m gim.shared_main run`, три runtime DSN и Supabase PostgreSQL. Инструкция — [README](../README.md).
