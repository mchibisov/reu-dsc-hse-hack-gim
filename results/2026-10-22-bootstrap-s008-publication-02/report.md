# S008 — повтор CI после исправления подготовки Compose

Состояние: успешно. Причина повтора — в publication-01 отсутствовал тестовый .env в чистом checkout. Изменён только шаг CI: копирование публичного .env.example перед config. Код/миграции анкеты не менялись.

Проверяемый main: e3053296bbef77a17719c40a5a3202e9633af1ea. Git push origin main exit0.

- [Tests 39704930701: success](https://github.com/mchibisov/reu-dsc-hse-hack-gim/actions/runs/39704930701): Windows/Python3.12 и Linux/Python3.13.
- [database 39704930683: success](https://github.com/mchibisov/reu-dsc-hse-hack-gim/actions/runs/39704930683): private миграции, PostgreSQL tests, shared unittest, обе Docker-сборки, default rubric, entry point и Compose.
- Snapshot tag working-version-2026-10-22 неизменён: 7d06b60ceae3d6bb6976cd274bbb4da5fc805b59.

Локальный полный набор ранее:204 passed (full-02). Временная БД остановлена. Облачные Vercel/Supabase и реальный VK не обновлялись; локальный Docker Desktop по-прежнему требует исправления WSL. Успешные Docker-сборки в CI не доказывают готовность локального Engine.
