# S006 — публикация и независимая проверка CI

Состояние: успешно. Код 551a634f7216e20cab95d2e548e444e1ef9bb4ad опубликован обычным git push в main; git ls-remote подтвердил равенство SHA. Автор — mirovif, история не переписана. Production deployment не переключался. Одноразовый локальный PostgreSQL остановлен после всех проверок.

На GitHub запущены [Tests](https://github.com/mchibisov/reu-dsc-hse-hack-gim/actions/runs/39700451456) (Linux/Python 3.13, Windows/Python 3.12) и [database](https://github.com/mchibisov/reu-dsc-hse-hack-gim/actions/runs/39700451463) (PostgreSQL 16, Python 3.11, Docker builds/smoke). Проверка выполняется чтением GitHub Actions API; не реальный VK/LLM-прогон.

Зачем повторять: на локальной Windows сборка образа недоступна из-за Docker Desktop HTTP 500; удалённая Linux-проверка проверяет упаковку config/ и обе runtime-сборки.

Оба workflow завершились success. Все три job (`test`, `windows`, `postgres`) успешны. В database успешны миграции, pytest, shared unittest, сборка database/Dockerfile, корневого Dockerfile и Dockerfile.shared, чтение default rubric внутри root image и CLI --help shared image. Снимок API со всеми шагами: [ci-summary.json](ci-summary.json). Это подтверждает Docker-сборку в Linux CI; локальный Docker Desktop не исправлялся.

После code SHA в main публикуется только дополнение документации с этими результатами. Проверяемый runtime не меняется. Человеческие мобильные тесты и независимая экспертная разметка остаются внешними задачами.
