# Передача MVP команде

Основная ветка: `main`. База: Supabase PostgreSQL, private schema `gim`. Redis/ARQ не нужны.
Запуск: `python -m gim.shared_main run` или `docker compose up --build -d`.

## Перед запуском

- Применить пять миграций, подготовить три runtime LOGIN и активный набор.
- Загрузить музейные вопросы, направления и утверждённую рубрику. Для текущего адаптера сумма максимумов равна 3, итог округляется до целого (0.5 вверх), явный `scoring_method` — `sum_round_half_up`; другая формула требует отдельной реализации.
- Зарегистрировать сотрудников; заполнить локальный `.env` с ключами VK/LLM и тремя DSN.
- Остановить старого бота этого сообщества, выполнить `check-db`, `check-vk`, затем пройти синтетический опрос и получить Excel.
- Не переносить автоматически реальные анкеты из старого SQLite-прототипа; нужен отдельный проверенный импорт.

## Если модель недоступна

Анкеты сохраняются. Анализ повторяется пять раз, затем требует вмешательства оператора.
После исправления ключа/модели/рубрики оператор может повторить только неоценённые задачи нужного набора:

```sql
UPDATE gim.outbox_events e
SET completed_at=NULL,failed_at=NULL,attempts=0,available_at=now(),
    lease_until=NULL,lease_token=NULL,last_error_code=NULL
FROM gim.applications a
WHERE e.application_id=a.id AND a.recruitment_id=:'recruitment_id'::uuid
  AND e.topic='application.analyze'
  AND (e.failed_at IS NOT NULL OR e.last_error_code='analysis_disabled')
  AND NOT EXISTS (SELECT 1 FROM gim.evaluations v WHERE v.source_event_id=e.id);
```

Это операторская процедура для конкретного набора, не команда из бота. Живую задачу с действующей арендой она не перезапускает.

## Что ещё проверить на стенде

Реальный Polza/DeepSeek pipeline и задержку ответа, права VK и доставку Excel, резервирование БД и volume. Локальные тесты и сборка не подтверждают доступность внешних сервисов. Оплаченный ключ и рабочие DSN в этом репозитории отсутствуют.
