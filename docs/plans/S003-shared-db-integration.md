# План S003: существующий бот + private БД

Спецификация: [S003](../specs/S003-shared-db-integration.md). Пользователь явно поручил интеграцию и публикацию. Режим: независимые области SQL outbox и private dialog, затем сквозная проверка.

- [x] R303: SQLQueue и новая миграция lease/checkpoint/topics; Redis/ARQ удалены из runtime, зависимостей, Compose и CI. Claim/ack/retry/fencing/heartbeat: [36 PostgreSQL tests](../../results/2026-10-21-s003-ci-03/report.md).
- [x] R301–R305: SharedService поверх Repository и существующего VK-клиента; persisted binding, raw answers, staff ACL и snapshot XLSX. [Отказ согласия и followup RED→GREEN](../../results/2026-10-21-s003-dialog-index.md), [42 shared tests](../../results/2026-10-21-s003-postgres-03/report.md).
- [x] R305–R306: LocalPrivateStorage, SharedSettings, gateway adapter, main и Windows launchers. [Настройки/запуск](../../results/2026-10-21-s003-runtime-08/report.md), [gateway PostgreSQL](../../results/2026-10-21-s003-runtime-05/report.md). Второй живой poller не запускался.
- [x] R307: чистая установка, frozen lock, изолированная PostgreSQL18.4 и три LOGIN с SCRAM. [CI-команды](../../results/2026-10-21-s003-ci-03/report.md), [legacy regression](../../results/2026-10-21-s003-regression-01/report.md). Все отрицательные запуски сохранены в журнале.
- [ ] Живая приёмка: operator применяет новую миграцию к облачной БД, выдаёт три DSN и UUID активного набора. Docker build/run,90одновременных пользователей и время5–7мин пока не проверены. Четыре предыдущие миграции не изменены.
- [x] R308: независимое ревью и исправления, сканирование152 staged файлов без совпадений API ключей, локальный коммит `9b9c485` в codex/shared-db-integration. [Подготовка](../../results/2026-10-21-s003-publication-01/report.md), [ревью](../../results/2026-10-21-s003-review-01/report.md).
- [ ] R308: push и проверка удалённого SHA заблокированы внешними правами: реальная попытка push вернула403/exit128, denied to mirovif. [Отчёт](../../results/2026-10-21-s003-publication-02/report.md). Нужен Write либо авторизация владельца; повторять без изменения доступа бессмысленно.

2026-10-21: пользователь поручил подготовить промпт агенту для самостоятельной настройки облачных подключений и сообщил, что добавит mirovif Write. [Промпт](../prompts/S003-cloud-setup-agent.md) сохранён локально; его подготовка не означает выполнения облачной настройки или изменения прав GitHub.
