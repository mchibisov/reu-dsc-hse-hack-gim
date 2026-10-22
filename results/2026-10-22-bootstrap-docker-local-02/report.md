# Docker — повтор после установки Linux пользователем

Состояние: выполняется. Основание повтора: пользователь сообщил об установке Linux и попросил проверить Docker. Предыдущий run01/S009: Engine HTTP500, WSL не был готов. Проверить WSL2/Engine, затем запуск контейнера, сборку приложения и CLI/Compose при доступном Engine. Системные компоненты не устанавливать, данные не сбрасывать; действующий VK gateway не запускать параллельно облаку.

Первый вызов из sandbox получил Docker pipe Permission denied и WSL/E_ACCESSDENIED; это ограничение sandbox, повторяем диагностику с доступом к пользовательским службам.

## Итог: Docker работает

После установки Linux пользователем WSL показывает `docker-desktop Running 2`; Docker Desktop4.96.0, Engine29.9.1 linux/amd64 отвечает с exit0, прежний HTTP500 не воспроизводится. Compose5.6.0 доступен. [Диагностика](environment.log); русский текст wsl status в перенаправленном логе повреждён кодировкой, но ASCII-таблица list/verbose и ответ Engine читаются полностью.

Проверен актуальный исходный код main1a38e49:

- [Docker build](build.log): exit0, локальный образ `gim-local-check:20261022`, digest `sha256:ca79e2a9950728c0486448164d06987961b194d44563faca8717e78964bdbf4e`.
- [Запуск CLI в контейнере](container-cli.log): `docker run --rm --network none ... python -m gim.shared_main --help`, exit0.
- [Проверка runtime](container-runtime.log): private Repository импортируется, ranking rubric упакована и имеет binary_50_35_15, процесс работает под непривилегированным UID10001, /data/files доступен для записи; exit0.
- [Compose config](compose.log): `docker compose --env-file .env.example config --no-env-resolution --quiet`, exit0; в пустом логе ошибок нет. Рабочие секреты не подставлялись.

Одноразовые контейнеры удалены автоматически (--rm); проверочный образ оставлен. Системные компоненты/настройки и данные Docker не менялись. Полный VK gateway/worker с production не запускался: локального заполненного .env с рабочими DB LOGIN/API нет, действующий облачный транспорт не переключался. Для запуска проекта остаётся настройка подключений по README; причина сбоя самого Docker устранена установкой Linux.
