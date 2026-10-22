# Журнал проверок S006

Предыдущие продуктовые эксперименты: [оценка](evaluation-report.md), [статус](../output/FINAL_STATUS.md), [безопасность](security-review.md). Проверка S006 повторяет технические сценарии на новой Windows-среде и пустой БД, не эксперимент экспертной точности.

| Дата | Проверка | Отчёт |
|---|---|---|
| 22.10.2026 | Чистая установка успешна; локальный Docker Engine HTTP 500 | [environment-01](../results/2026-10-22-bootstrap-s006-environment-01/report.md) |
| 22.10.2026 | Исходные 190 unittest: 1 ошибка кодировки, 37 skip | [baseline-01](../results/2026-10-22-bootstrap-s006-baseline-01/report.md) |
| 22.10.2026 | Чистые private миграции/повтор и 52 SQL-теста успешны | [database-01](../results/2026-10-22-bootstrap-s006-database-01/report.md) |
| 22.10.2026 | RED: воспроизведены три дефекта Unicode/BOM | [encoding-red-01](../results/2026-10-22-bootstrap-s006-encoding-red-01/report.md) |
| 22.10.2026 | GREEN: Unicode/BOM, импорт и операторский bootstrap успешны | [encoding-green-01](../results/2026-10-22-bootstrap-s006-encoding-green-01/report.md) |
| 22.10.2026 | 191 unittest успешны; bare pytest: 47 async-тестов не исполнялись из-за config | [full-01](../results/2026-10-22-bootstrap-s006-full-01/report.md) |
| 22.10.2026 | Исправлен root pytest config; 246 passed без skip; CLI/Compose/pip успешны | [full-02](../results/2026-10-22-bootstrap-s006-full-02/report.md) |
| 22.10.2026 | main опубликована, SHA подтверждён; оба CI success, Windows/Linux и три Docker-сборки прошли | [publication-01](../results/2026-10-22-bootstrap-s006-publication-01/report.md) |
| 22.10.2026 | Локальный Docker: WSL runtime отсутствует, backend не видит VMP; установка отклонена авто-проверкой до явного согласия | [docker-local-01](../results/2026-10-22-bootstrap-docker-local-01/report.md) |
| 22.10.2026 | S007: задержки обычных вопросов, диагностика очереди/dispatcher выполняется | [s007-diagnosis-01](../results/2026-10-22-bootstrap-s007-diagnosis-01/report.md) |
| 22.10.2026 | S007 RED: обычный диалог во время анализа и в конце бюджета | [dispatch-red-01](../results/2026-10-22-bootstrap-s007-dispatch-red-01/report.md) |
| 22.10.2026 | S007 GREEN: lanes/приём обычных событий, выполняется | [dispatch-green-01](../results/2026-10-22-bootstrap-s007-dispatch-green-01/report.md) |
| 22.10.2026 | S007 GREEN-02: SQL array и отмена sibling lanes | [dispatch-green-02](../results/2026-10-22-bootstrap-s007-dispatch-green-02/report.md) |
| 22.10.2026 | S007 полный набор после исправления очереди | [full-01](../results/2026-10-22-bootstrap-s007-full-01/report.md) |
| 22.10.2026 | S007: узкие пулы max_size=2, как в облаке | [small-pools-01](../results/2026-10-22-bootstrap-s007-small-pools-01/report.md) |
