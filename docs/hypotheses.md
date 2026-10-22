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
| 22.10.2026 | S008 RED: убрать вопрос8, изменить9, сохранить snapshot | [s008-red-01](../results/2026-10-22-bootstrap-s008-red-01/report.md) |
| 22.10.2026 | S008 GREEN: новая анкета/сохранность данных | [s008-green-01](../results/2026-10-22-bootstrap-s008-green-01/report.md) |
| 22.10.2026 | S008: удаление legacy и дублирования после snapshot | [s008-cleanup-01](../results/2026-10-22-bootstrap-s008-cleanup-01/report.md) |
| 22.10.2026 | S008: новая пустая private БД и все актуальные тесты | [s008-full-01](../results/2026-10-22-bootstrap-s008-full-01/report.md) |
| 22.10.2026 | S008 final: stale template, сохранность отвеченного8, безопасный rollout | [s008-full-02](../results/2026-10-22-bootstrap-s008-full-02/report.md) |
| 22.10.2026 | S008: main/tag опубликованы; CI выявил отсутствие тестового .env для Compose | [s008-publication-01](../results/2026-10-22-bootstrap-s008-publication-01/report.md) |
| 22.10.2026 | S008: после подготовки env оба CI success, включая две Docker-сборки и Compose | [s008-publication-02](../results/2026-10-22-bootstrap-s008-publication-02/report.md) |
| 22.10.2026 | S009: повторная техническая приёмка после очистки по запросу пользователя | [s009-recheck-01](../results/2026-10-22-bootstrap-s009-recheck-01/report.md) |
| 22.10.2026 | S009 RED: receipt после миграции и нагрузочный скрипт | [s009-red-01](../results/2026-10-22-bootstrap-s009-red-01/report.md) |
| 22.10.2026 | S009 GREEN: безопасный поздний ответ и динамический прогресс нагрузки | [s009-green-01](../results/2026-10-22-bootstrap-s009-green-01/report.md) |
| 22.10.2026 | S009 final: чистый Git-архив, отдельный venv, новая БД, реальный worker | [s009-recheck-02](../results/2026-10-22-bootstrap-s009-recheck-02/report.md) |
| 22.10.2026 | S009 контроль: повтор11 критических сценариев,50анкет и реального запуска после review | [s009-final-03](../results/2026-10-22-bootstrap-s009-final-03/report.md) |
| 22.10.2026 | Docker: повтор после сообщения пользователя об установке Linux | [docker-local-02](../results/2026-10-22-bootstrap-docker-local-02/report.md) |
| 22.10.2026 | S010: текущее состояние/IT-критерии/сохранность продуктовых фишек | [s010-features-01](../results/2026-10-22-bootstrap-s010-features-01/report.md) |
| 22.10.2026 | S010 повтор: отдельный pytest temp/cache после WinError5 | [s010-features-02](../results/2026-10-22-bootstrap-s010-features-02/report.md) |
| 22.10.2026 | S011: пользовательский токен, реальная диагностика VK и доступность runtime | [s011-live-vk-01](../results/2026-10-22-bootstrap-s011-live-vk-01/report.md) |
| 22.10.2026 | S011: read-only проверка диалога указанного пользователем VK ID | [s011-live-vk-02](../results/2026-10-22-bootstrap-s011-live-vk-02/report.md) |
| 22.10.2026 | Публикация полного актуального контекста и переносимого HANDOFF | [handoff-publication-01](../results/2026-10-22-bootstrap-handoff-publication-01/report.md) |
