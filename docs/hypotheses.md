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
