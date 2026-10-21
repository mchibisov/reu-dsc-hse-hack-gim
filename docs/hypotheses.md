# Журнал гипотез и проверок

Перед проверкой добавь запись по [шаблону](templates/hypothesis.md).
Каждый повторный запуск добавляй отдельной строкой в таблицу запусков внутри записи гипотезы.
Перед повторением прочитай предыдущие отчёты и укажи изменение условий или причину повторения.

## Продуктовые гипотезы

### H001: длительность полного опроса

- Спецификация: [S002](specs/S002-gim-vk-bot.md), R004–R005.
- Гипотеза: кандидат проходит все применимые исходные поля и персональные уточнения за 5–7 минут.
- Метод: 5 добровольцев, естественные ответы без заготовок, время от согласия до подтверждения получения; отдельно фиксировать незавершённые попытки.
- Критерий до проверки: все 5 завершили за ≤7 минут; время <5 минут само по себе не ошибка при содержательных ответах.
- Статус: не запущена, нужны реальное сообщество и участники. Вывод: недостаточно данных.

### H002: изоляция 90 конкурентных диалогов

- Спецификация: [S002](specs/S002-gim-vk-bot.md), R003/R014.
- Гипотеза: 90 конкурентно исполняемых сценариев завершаются без потери и смешивания ответов.
- Метод: synthetic asyncio на локальной SQLite; 90 уникальных пользователей и уникальный проверяемый ответ; отдельно 20 одинаковых событий одной заявки.
- Критерий до проверки: 90 завершённых уникальных заявок, 0 ошибок и 0 смешиваний; замер p95, без экстраполяции на VK/LLM.
- Текущий вывод: подтверждена изоляция в локальной SQLite после исправления; реальная нагрузка полного стека не проверена, p95 локальной записи 1,5 с.

| Запуск | Дата / часовой пояс | Причина | Состояние | Вывод | Отчёт |
| --- | --- | --- | --- | --- | --- |
| 01 | 2026-10-21 Europe/Moscow | первичная проверка локального хранилища | завершён, ошибка SQLite | опровергнута в проверенных условиях | [H002-01](../results/2026-10-21-H002-gim-concurrency-01/report.md) |
| 02 | 2026-10-21 Europe/Moscow | запись SQLite сериализована, busy timeout 30 с; PostgreSQL без глобального замка | завершён | подтверждена только изоляция локальных состояний | [H002-02](../results/2026-10-21-H002-gim-concurrency-02/report.md) |
| 03 | 2026-10-21 Europe/Moscow | регрессия в общем suite после gateway/bot | завершён | тест изоляции пройден; новые метрики задержки не сохранялись | [suite-01](../results/2026-10-21-bootstrap-gim-suite-01/report.md) |
| 04 | 2026-10-21 Europe/Moscow | регрессия в общем suite после исправлений ревью | завершён | тест изоляции пройден; полный стек не проверен | [suite-02](../results/2026-10-21-bootstrap-gim-suite-02/report.md) |
| 05 | 2026-10-21 Europe/Moscow | финальный suite с дополнительным студенческим сценарием | завершён | тест изоляции пройден; полный стек не проверен | [suite-03](../results/2026-10-21-bootstrap-gim-suite-03/report.md) |
| 06 | 2026-10-21 Europe/Moscow | повтор после отключения LLM и усиления теста отсутствия HTTP | завершён | локальная изоляция пройдена; новые метрики не снимались | [no-llm-01](../results/2026-10-21-bootstrap-gim-no-llm-01/report.md) |

### H003: приближение к экспертной оценке

- Спецификация: [S002](specs/S002-gim-vk-bot.md), R006/R016.
- Гипотеза: предварительная рубрика gim-5-v1 достигает MAE ≤0,5 и accuracy ≥0,6 при coverage ≥0,9 на отложенных исторических анкетах; это исследовательский ориентир команды, а не подтверждённое требование жюри.
- Метод: детерминированный holdout 20% (seed=42), оценка только содержательных полей; исходы и экспертные баллы не передаются модели. Зафиксировать SHA256/количество строк источников, матрицу ошибок, coverage и долю unknown. Не настраивать промпт по holdout.
- Критерий: совместное достижение указанных порогов; при недоступности модели/неполной разметке — недостаточно данных.
- Статус: выполнена подготовка данных/holdout/baseline, модельная часть не запущена; интеграция LLM отложена пользователем, актуальность данных не согласована. Следующий ID — H004.

| Запуск | Дата / часовой пояс | Причина | Состояние | Вывод | Отчёт |
| --- | --- | --- | --- | --- | --- |
| 01 | 2026-10-21 Europe/Moscow | подготовка воспроизводимого holdout и majority-baseline, без платной модели | частично выполнен | недостаточно данных для модельной гипотезы | [H003-01](../results/2026-10-21-H003-gim-scoring-01/report.md) |

## Технические проверки

| Дата | Что проверялось | Отчёт |
| --- | --- | --- |
| 2026-10-21 | gim-analysis-01 | [отчёт](../results/2026-10-21-bootstrap-gim-analysis-01/report.md) |
| 2026-10-21 | gim-analysis-02 | [отчёт](../results/2026-10-21-bootstrap-gim-analysis-02/report.md) |
| 2026-10-21 | gim-analysis-03 | [отчёт](../results/2026-10-21-bootstrap-gim-analysis-03/report.md) |
| 2026-10-21 | gim-analysis-04 | [отчёт](../results/2026-10-21-bootstrap-gim-analysis-04/report.md) |
| 2026-10-21 | gim-bot-01 | [отчёт](../results/2026-10-21-bootstrap-gim-bot-01/report.md) |
| 2026-10-21 | gim-bot-02 | [отчёт](../results/2026-10-21-bootstrap-gim-bot-02/report.md) |
| 2026-10-21 | gim-dialog-01 | [отчёт](../results/2026-10-21-bootstrap-gim-dialog-01/report.md) |
| 2026-10-21 | gim-dialog-02 | [отчёт](../results/2026-10-21-bootstrap-gim-dialog-02/report.md) |
| 2026-10-21 | gim-environment-01 | [отчёт](../results/2026-10-21-bootstrap-gim-environment-01/report.md) |
| 2026-10-21 | gim-evaluate-01 | [отчёт](../results/2026-10-21-bootstrap-gim-evaluate-01/report.md) |
| 2026-10-21 | gim-evaluate-02 | [отчёт](../results/2026-10-21-bootstrap-gim-evaluate-02/report.md) |
| 2026-10-21 | gim-hardening-01 | [отчёт](../results/2026-10-21-bootstrap-gim-hardening-01/report.md) |
| 2026-10-21 | gim-hardening-02 | [отчёт](../results/2026-10-21-bootstrap-gim-hardening-02/report.md) |
| 2026-10-21 | gim-integration-01 | [отчёт](../results/2026-10-21-bootstrap-gim-integration-01/report.md) |
| 2026-10-21 | gim-integration-02 | [отчёт](../results/2026-10-21-bootstrap-gim-integration-02/report.md) |
| 2026-10-21 | gim-suite-01 | [отчёт](../results/2026-10-21-bootstrap-gim-suite-01/report.md) |
| 2026-10-21 | gim-deploy-01 | [отчёт](../results/2026-10-21-bootstrap-gim-deploy-01/report.md) |
| 2026-10-21 | gim-deploy-02 | [отчёт](../results/2026-10-21-bootstrap-gim-deploy-02/report.md) |
| 2026-10-21 | gim-review-01 | [отчёт](../results/2026-10-21-bootstrap-gim-review-01/report.md) |
| 2026-10-21 | gim-review-fix-01 | [отчёт](../results/2026-10-21-bootstrap-gim-review-fix-01/report.md) |
| 2026-10-21 | gim-review-fix-02 | [отчёт](../results/2026-10-21-bootstrap-gim-review-fix-02/report.md) |
| 2026-10-21 | gim-review-fix-03 | [отчёт](../results/2026-10-21-bootstrap-gim-review-fix-03/report.md) |
| 2026-10-21 | gim-review-fix-04 | [отчёт](../results/2026-10-21-bootstrap-gim-review-fix-04/report.md) |
| 2026-10-21 | gim-suite-02 | [отчёт](../results/2026-10-21-bootstrap-gim-suite-02/report.md) |
| 2026-10-21 | gim-suite-03 | [отчёт](../results/2026-10-21-bootstrap-gim-suite-03/report.md) |
| 2026-10-21 | gim-mistral-01 | [отчёт](../results/2026-10-21-bootstrap-gim-mistral-01/report.md) |
| 2026-10-21 | gim-mistral-02 | [отчёт](../results/2026-10-21-bootstrap-gim-mistral-02/report.md) |
| 2026-10-21 | gim-mistral-03 | [отчёт](../results/2026-10-21-bootstrap-gim-mistral-03/report.md) |
| 2026-10-21 | gim-mistral-04 | [отчёт](../results/2026-10-21-bootstrap-gim-mistral-04/report.md) |
| 2026-10-21 | gim-delivery-01: целостность и состав архива | [отчёт](../results/2026-10-21-bootstrap-gim-delivery-01/report.md) |
| 2026-10-21 | gim-presence-01: наличие файлов и запуск | [отчёт](../results/2026-10-21-bootstrap-gim-presence-01/report.md) |
| 2026-10-21 | gim-launcher-01: наличие файлов и запуск | [отчёт](../results/2026-10-21-bootstrap-gim-launcher-01/report.md) |
| 2026-10-21 | gim-launcher-02: наличие файлов и запуск | [отчёт](../results/2026-10-21-bootstrap-gim-launcher-02/report.md) |
| 2026-10-21 | gim-launcher-03: наличие файлов и запуск | [отчёт](../results/2026-10-21-bootstrap-gim-launcher-03/report.md) |
| 2026-10-21 | gim-launcher-04: наличие файлов и запуск | [отчёт](../results/2026-10-21-bootstrap-gim-launcher-04/report.md) |
| 2026-10-21 | gim-openrouter-01 | [отчёт](../results/2026-10-21-bootstrap-gim-openrouter-01/report.md) |
| 2026-10-21 | gim-openrouter-02 | [отчёт](../results/2026-10-21-bootstrap-gim-openrouter-02/report.md) |
| 2026-10-21 | gim-openrouter-03 | [отчёт](../results/2026-10-21-bootstrap-gim-openrouter-03/report.md) |
| 2026-10-21 | gim-vk-live-01 | [отчёт](../results/2026-10-21-bootstrap-gim-vk-live-01/report.md) |
| 2026-10-21 | gim-no-redis-01 | [отчёт](../results/2026-10-21-bootstrap-gim-no-redis-01/report.md) |
| 2026-10-21 | gim-no-redis-02 | [отчёт](../results/2026-10-21-bootstrap-gim-no-redis-02/report.md) |
| 2026-10-21 | gim-no-redis-03 | [отчёт](../results/2026-10-21-bootstrap-gim-no-redis-03/report.md) |
| 2026-10-21 | gim-no-redis-04 | [отчёт](../results/2026-10-21-bootstrap-gim-no-redis-04/report.md) |
| 2026-10-21 | gim-no-redis-05 | [отчёт](../results/2026-10-21-bootstrap-gim-no-redis-05/report.md) |
| 2026-10-21 | gim-no-redis-06 | [отчёт](../results/2026-10-21-bootstrap-gim-no-redis-06/report.md) |
| 2026-10-21 | gim-no-redis-review-01 | [отчёт](../results/2026-10-21-bootstrap-gim-no-redis-review-01/report.md) |
| 2026-10-21 | gim-vk-start-01 | [отчёт](../results/2026-10-21-bootstrap-gim-vk-start-01/report.md) |
| 2026-10-21 | gim-openai-01: проверка предоставленного ключа, HTTP 401 | [отчёт](../results/2026-10-21-bootstrap-gim-openai-01/report.md) |
| 2026-10-21 | gim-no-key-01: сквозной режим без LLM | [отчёт](../results/2026-10-21-bootstrap-gim-no-key-01/report.md) |
| 2026-10-21 | gim-no-key-02: сквозной режим без LLM | [отчёт](../results/2026-10-21-bootstrap-gim-no-key-02/report.md) |
| 2026-10-21 | gim-no-key-03: сквозной режим без LLM | [отчёт](../results/2026-10-21-bootstrap-gim-no-key-03/report.md) |
| 2026-10-21 | gim-no-key-04: сквозной режим без LLM | [отчёт](../results/2026-10-21-bootstrap-gim-no-key-04/report.md) |
| 2026-10-21 | S004 hidden-export-01: до реализации проверка скрытой команды, изоляции, replay и ротации | [отчёт](../results/2026-10-21-bootstrap-hidden-export-01/report.md) |
| 2026-10-21 | S004 hidden-export-02: повтор RED после исправления аргумента тестовой fixture | [отчёт](../results/2026-10-21-bootstrap-hidden-export-02/report.md) |
| 2026-10-21 | S004 hidden-export-03: после реализации durable разрешений и rate limiter; targeted/full regression | [отчёт](../results/2026-10-21-bootstrap-hidden-export-03/report.md) |
| 2026-10-21 | S004 hidden-export-04: RED rolling-window границы, replay попыток, concurrency и admin regression | [отчёт](../results/2026-10-21-bootstrap-hidden-export-04/report.md) |
| 2026-10-21 | S004 hidden-export-05: GREEN rolling-window, targeted/full suite, lint | [отчёт](../results/2026-10-21-bootstrap-hidden-export-05/report.md) |
| 2026-10-21 | 2026-10-21-bootstrap-gim-groq-01 | [отчёт](../results/2026-10-21-bootstrap-gim-groq-01/report.md) |
| 2026-10-21 | 2026-10-21-bootstrap-gim-groq-02 | [отчёт](../results/2026-10-21-bootstrap-gim-groq-02/report.md) |
| 2026-10-21 | 2026-10-21-bootstrap-gim-polza-01 | [отчёт](../results/2026-10-21-bootstrap-gim-polza-01/report.md) |
| 2026-10-21 | 2026-10-21-bootstrap-gim-polza-02 | [отчёт](../results/2026-10-21-bootstrap-gim-polza-02/report.md) |
| 2026-10-21 | 2026-10-21-bootstrap-s004-review-01 | [отчёт](../results/2026-10-21-bootstrap-s004-review-01/report.md) |
| 2026-10-21 | 2026-10-21-bootstrap-s004-final-01 | [отчёт](../results/2026-10-21-bootstrap-s004-final-01/report.md) |
