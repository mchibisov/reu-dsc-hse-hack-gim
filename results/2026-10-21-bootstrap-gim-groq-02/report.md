# Регрессия анализатора/экспорта после Groq smoke

Команда: `.venv/Scripts/python.exe -m pytest tests/test_analysis.py tests/test_admin.py tests/test_no_key_flow.py -q --basetemp=runtime/pytest-groq-02 -p no:cacheprovider`.
Для тестового процесса LLM_API_KEY/LLM_MODEL заданы пустыми через env; live .env не менялся. Все вызовы в тестах — mocks, реальные API не вызываются. Результат15passed,2.15s: [лог](artifacts/tests.log).
Скрипт check_groq.py: ruff чистый, [лог](artifacts/ruff.log). Новый start_vk.ps1 разобран штатным PowerShell parser:0errors. Это синтаксическая проверка launcher, не запуск процесса.
Реальный Groq Provider уже прошёл отдельный synthetic smoke groq-01; полный suite с новой скрытой выдачей выполняется после завершения её реализации.
