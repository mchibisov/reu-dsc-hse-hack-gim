# План S004

Спецификация: [S004](../specs/S004-hidden-export-groq.md). Оба изменения прямо поручены пользователем; скрытая команда и режим доступа уточнены в опросе.

- [x] R401–R403: скрытая одноразовая выдача Excel реализована;13 targeted,70passed1skipped в полном suite. [RED→GREEN](../../results/2026-10-21-bootstrap-hidden-export-05/report.md). Существующие анкеты/процесс не изменялись.
- [x] R404 Groq: models/chat/Provider analyze/followups успешно на synthetic. [Отчёт](../../results/2026-10-21-bootstrap-gim-groq-01/report.md). Затем пользователь выбрал Polza вместо Groq.
- [ ] R404 Polza: точная модель есть, короткий JSON200; полный analyze исчерпал1800токенов на reasoning, пустой content, followup timeout3s. [Причина](../../results/2026-10-21-bootstrap-gim-polza-02/report.md). Нужна адаптация запроса и повторный smoke.
- [x] R401–R405: full tests70passed1skipped и независимое ревью без P1/P2. Старый I001 в диагностическом скрипте исправлен, повторная ruff всего src/tests/scripts/main чистая. [Проверка](../../results/2026-10-21-bootstrap-s004-final-01/report.md).
- [x] Проверка257файлов на реальные секреты: совпадений0, .env ignored/not tracked. Checkpoint `c10fc0d` закоммичен и успешно опубликован в codex/gim-mvp, удалённый SHA сверён; подробности в HANDOFF.md.
- [ ] R405: локально настроить ключ/модель/код, безопасно перезапустить один live процесс, подтвердить загрузку конфигурации и alive; не считать это ручной приёмкой всей анкеты.
