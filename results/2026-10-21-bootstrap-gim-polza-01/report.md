# Polza: первичная проверка точной модели

По новому прямому поручению пользователя основной кандидат — Polza https://polza.ai/api/v1, model deepseek/deepseek-v4.1-flash-1017. Ключ сохранён в игнорируемом .env как POLZA_API_KEY; файл не публикуется.
Официальная [документация Polza](https://polza.ai/docs) подтверждает OpenAI-compatible API; запрос корня /api/v1 через web даёт404 и не доказывает отказа конкретных API methods.
models200, точный model ID найден; generation200, strict JSON валиден,3438ms/68tokens. Однако существующий Provider не получил валидную аналитику (17219ms) и уточнения (timeout3016ms). [Метаданные](artifacts/access.json), [лог](artifacts/check.log).
Все данные синтетические. Работающий бот ещё не переключён на Polza: успешный короткий JSON smoke не равен совместимости полного pipeline. Для диагностики следующий запуск собирает только HTTP status/finish_reason/длину и usage без response content/ключей.
Вывод: доступ/модель подтверждены, готовность полного Provider недостаточна, исследование продолжается.
