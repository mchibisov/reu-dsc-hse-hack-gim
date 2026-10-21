# Polza: регрессия управления reasoning (RED)

Причина прошлого сбоя: Polza-02 вернул пустой content, весь лимит 1800 потрачен на reasoning. Документация https://polza.ai/docs/osobennosti/reasoning-tokens поддерживает reasoning.enabled=false. Проверяем, что явная настройка доходит до запроса, остальные провайдеры не получают лишнего поля.

Команда: gim_bot/.venv/Scripts/python.exe -m pytest tests/test_analysis.py -q --basetemp=runtime/polza-red-03 -p no:cacheprovider. Локальный Windows/Python, внешние вызовы замоканы, LLM env пуст.

Факт: 1 failed, 10 passed; KeyError reasoning в новом тесте. Подтверждена отсутствующая передача настройки; запуск завершён. Следующий шаг: адаптация и полноценный synthetic API smoke; реальных анкет этот запуск не использовал.
