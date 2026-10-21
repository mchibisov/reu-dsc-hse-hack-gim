# Groq: models, structured JSON и действующий Provider

Основание: пользователь предоставил Groq key и поручил подключить модель. Ключ сохранён только в игнорируемом gim_bot/.env как GROQ_API_KEY, не записан в отчёт или исходники.
Официальные источники: [Structured Outputs](https://console.groq.com/docs/structured-outputs), [Reasoning](https://console.groq.com/docs/reasoning). Groq endpoint api.groq.com/openai/v1, модель openai/gpt-oss-120b, strict JSON Schema.
Команда: `.venv/Scripts/python.exe scripts/check_groq.py --provider --output ../results/2026-10-21-bootstrap-gim-groq-01/artifacts/access.json`.
Результат: models200, модель доступна; chat200/641ms/148tokens, JSON валиден. Существующий Provider без изменений успешно выполнил analyze3938ms/5критериев и followups2015ms/3вопроса. [Метаданные](artifacts/access.json), [лог](artifacts/check.log).
Отправлялись только synthetic ответы из скрипта; реальные анкеты из БД не читались/не отправлялись. Проверка доступности не является оценкой точности музейного скоринга, нагрузки90пользователей или длительности анкеты.
Вывод: подтверждена совместимость существующего Provider с Groq в проверенном синтетическом сценарии. Переключение работающего процесса выполняется отдельно после интеграции скрытого Excel доступа.
