# Database MVP Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; implement inline in this session.

**Goal:** Рабочий компонент БД для команды хакатона.
**Architecture:** private PostgreSQL schema, 12 tables, transactional operations; ARQ + durable outbox, private Supabase Storage.
**Tech Stack:** PostgreSQL >=16, Python >=3.11, psycopg3, pytest, ARQ.
**Spec:** ../specs/2026-10-21-database-mvp-design.md

## Global Constraints
Сохранять границы компонентов; не публиковать закрытые исходники/ПДн; никаких платных ресурсов; отдельная ветка Макса. Не считать отсутствие оценки нулём. Не использовать будущую активность как вход оценки.

## Review Focus
1. Повтор события с другой заявкой или изменённым телом — отклонение, а не подмена.
2. Две конкурентные операции и устаревший снимок — CAS/блокировки, сохранность версии.
3. Новое резюме и старая оценка — точный снимок и признак stale.
4. Отзыв сотрудника между постановкой и отправкой — проверка перед внешним вызовом.
5. Исчерпанные повторы ARQ/потеря Redis — повторная публикация outbox, отсутствие ложного completed.

### Task 1: Schema and access
Files: supabase/migrations, tests/test_database.py, src/gim_db/migrate.py.
- [x] Write real PostgreSQL invariant/security tests and run RED (missing schema).
- [x] Implement 12 tables, integrity/security functions and migration runner.
- [x] Run schema/security tests GREEN.

### Task 2: Service contract
Files: src/gim_db/{repository,export,outbox,storage}.py; tests/test_database.py.
Interfaces: Repository(pool), start_application, prepare_question, record_answer, submit, evaluation_snapshot, save_evaluation, export_bundle; publish_pending(redis).
- [x] Write tests for questions, revisions, submissions, evaluations, snapshots and exports; run RED.
- [x] Implement transactional contract with pool, locking and idempotency.
- [x] Run tests GREEN, including 50 candidates and outbox recovery.

### Task 3: Delivery and cloud
Files: Dockerfile, compose.yaml, .env.example, README.md, docs/contracts.md, scripts/load_materials.py, tests/test_storage.py.
- [x] Test private file contract and restricted historical feature mapping.
- [x] Add Docker configuration, private loaders, schema PNG and instructions.
- [x] Apply identical reviewed migrations to chosen free Supabase project; cloud smoke test, advisors. If access unavailable record exact blocker without claiming deployment.
- [x] Whole branch independent review; fix important findings with reproducing tests; commit and push Max branch only.

## Выполнение

23 теста прошли на реальных Docker PostgreSQL/Redis; облачные SQL smoke и advisors проверены отдельно. Важное замечание независимого ревью устранено с RED→GREEN. Итоговая интеграция отделена: все новые paths относительно database/, общий предок Vova/ff0b44b, чужие файлы не изменены. Полный Storage HTTP и cloud load ожидают секретов/интеграции команды, что явно отражено в verification.md.
