# Docker — диагностика локального запуска

Состояние: диагностика выполнена, восстановление ожидает согласия на системную установку. Основание: пользователь просит проверить Docker и добиться работы. Предыдущая проверка S006: Linux CI собрал образы, локальный Docker Desktop возвращал HTTP 500. Повтор нужен для поиска причины на этой Windows, а не повторения проверки кода в CI.

Критерии: Engine отвечает; образ собирается; контейнер выполняет CLI/чтение рубрики, Compose корректен. Внешние VK/LLM и production gateway не запускать параллельно облаку. Не удалять Docker/WSL данные, не сбрасывать Docker Desktop вслепую.

План: проверить backend/WSL/службы и журналы; устранить подтверждённую причину минимальным действием; повторить engine/build/run и сохранить доказательства.

## Результат диагностики

Docker Desktop работает как приложение, но Linux Engine не стартует. В журнале причина `WslVirtualMachinePlatformNotEnabled`; `wsl --status`/`--version` сообщают, что WSL не установлен. Firmware virtualization уже включена; отключение BIOS не установлено. CIM показывает компоненты Windows как включённые, но работающих служб WSL/VMCompute нет; pending reboot через требующий администратора DISM не подтверждён. [Доказательства](backend-precondition.txt), [вывод штатной diagnose](diagnose.log), ограниченная по времени диагностика [check_engine.py](check_engine.py).

Актуальная main 7c9631f независимо проверена: [Tests success](https://github.com/mchibisov/reu-dsc-hse-hack-gim/actions/runs/39700716766), [database/Docker success](https://github.com/mchibisov/reu-dsc-hse-hack-gim/actions/runs/39700716748). Это проверка Linux CI, не работающий локальный daemon.

## Неисполненное исправление и причина остановки

Подготовлен [install-wsl.ps1](install-wsl.ps1): официальный `wsl --install --no-distribution --web-download --no-launch`. По [документации Microsoft](https://learn.microsoft.com/en-us/windows/wsl/basic-commands) это установка WSL без дистрибутива; [Docker](https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/topics/) требует работающий WSL/Virtual Machine Platform, после изменения компонентов может потребоваться перезагрузка.

Автоматическая проверка разрешений отклонила запуск `wsl --install`: это постоянное системное изменение, возможны изменения компонентов Windows/сети и необходимость перезагрузки; требуется явное согласие пользователя на установку. Команда установки не выполнялась, через обход не запускалась. Не были удалены данные, сброшены настройки Docker или перезагружена Windows.

Следующий шаг после явного согласия: установка WSL; если Windows требует перезагрузку, согласовать её отдельно; затем Docker Engine → build → run CLI/rubric и изолированная проверка Compose. До этого локальная работоспособность Docker **не подтверждена**.
