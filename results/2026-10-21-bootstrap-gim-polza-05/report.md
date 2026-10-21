# Polza GREEN: анализ и уточнение

Повтор после Polza-04: модель возвращала три одинаковых topic, строгая проверка обоснованно отклоняла весь набор. В промпте явно ограничен topic библиотекой: один вопрос на уникальную тему, не заполнять три места искусственно.

Команда: `gim_bot/.venv/Scripts/python.exe scripts/check_polza.py --provider --output ../results/2026-10-21-bootstrap-gim-polza-05/artifacts/access.json`. Windows, реальный официальный API, только synthetic данные, точная выбранная модель.

Результат: HTTP200 models/chat, analyze валиден (5 критериев, проверены цитаты), 5125ms; уточнение валидно (1 вопрос), 2516ms. Оба ответа stop, reasoning_tokens=0. [Метаданные](artifacts/access.json). Подтверждено в проверенных условиях, запуск завершён. Разные прогоны synthetic дали балл2 и3: температура0 не гарантирует повторяемость; музейная точность оценки не подтверждена.

Полный suite:72passed1skipped,33.34s (`pytest -q --basetemp=runtime/polza-full-05 -p no:cacheprovider`); PostgreSQL test пропущен без подключения. `ruff check src tests scripts main.py`: clean. Docker и полная нагрузка не проверялись.
