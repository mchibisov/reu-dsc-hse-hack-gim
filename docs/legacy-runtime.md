# Старый runtime public-схемы

Удалён из текущего дерева при очистке S008; восстановить исходники и инструкции можно из [метки «Работающая версия»](https://github.com/mchibisov/reu-dsc-hse-hack-gim/tree/working-version-2026-10-22).

Это отдельная схема с `DATABASE_URL`. Не применяйте эти миграции к основной private БД и не запускайте старый gateway одновременно с новым для одного сообщества.

Текущая версия использует `python -m gim.shared_main run`, три runtime DSN и Supabase PostgreSQL. Инструкция — [README](../README.md).
