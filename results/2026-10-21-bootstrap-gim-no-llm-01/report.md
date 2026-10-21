# Проверка запуска без модели

- Дата: 2026-10-21, Europe/Moscow.
- Причина: пользователь отложил Mistral; API_KEY и MODEL очищены, шаблон обновлён.
- Метод: полный pytest, ruff/compileall/pip check, чтение Settings без вывода секретов.
- Критерий: тесты проходят; analyze/followups без ключа не делают HTTP-запросов; локальный Settings имеет пустые key/model.
- Предыдущий прогон: suite-03, 43 passed / 1 skipped. Изменены конфигурация, документация и проверка отсутствия внешних запросов.
- Состояние: завершён.
- Итог: **43 passed, 1 skipped in 25.94s**; ruff, compileall, pip check и проверка Settings — exit 0.
- Доказательства: [pytest](artifacts/pytest.txt), [ruff](artifacts/ruff.txt), [compileall](artifacts/compileall.txt), [pip check](artifacts/pip-check.txt), [Settings](artifacts/settings.txt).
- Изменение теста: MockTransport аварийно завершил бы тест при любом внешнем запросе отключённого Provider; analyze и followups вернули None без HTTP.
- Вывод: подтверждён локальный режим без модели. Worker сохраняет ответы со score=null и no_analytics (test_no_model_retains_application_without_score).
- Ограничения: пропущена живая PostgreSQL/Redis-интеграция; VK, Docker, реальная нагрузка и хронометраж не подтверждены.
- Следующий шаг: подключить сообщество VK и выполнить живые проверки; LLM отложена пользователем.
