# S009 — первый повтор

Состояние: выполняется. Новая проверка по прямому запросу пользователя после очистки. Начальный HEAD23e05ba. План: одноразовая БД gim_s009_first, текущий Python3.12.14, полный набор тестов, CLI, зависимости, Docker/health. Никаких production-данных и исходящих VK-сообщений.

Предварительно: рабочая копия чиста. Git в новой sandbox-учётной записи требует process-local safe.directory; глобальные настройки не менялись. Прямой docker version из sandbox не получил доступ к пользовательскому pipe/config; это пока ограничение доступа, а не доказательство поломки Engine. Временный PostgreSQL остановлен. Локального .env в main нет (только.example).

Итог первого повтора: **204 passed in24.94s**, [pytest.log](pytest.log), миграции exit0. Новая disposable БД gim_s009_first, PostgreSQL18.4, localhost52782; не production. Первый старт прежнего кластера на55439 не удался (bind Permission denied); fresh initdb из sandbox успешен, старт из sandbox упёрся в restricted token87. Запуск нового кластера на свободном порту вне sandbox успешен; эти инфраструктурные ошибки не выданы за ошибки кода.

Чистая установка: первая попытка pip из sandbox не имела сетевого доступа, также команда была вызвана из родительского cwd; [clean-install.log](clean-install.log). Повтор из Git-архива с отдельным venv и сетевым разрешением успешен: [clean-install-02.log](clean-install-02.log). Повтор тестов после исправлений будет отдельным run02.

Docker version вне sandbox: desktop-linux Engine возвращает HTTP500 на /version. Локальный контейнер запустить нельзя в нынешнем состоянии Docker Desktop; Windows/WSL не изменялись. Публичный [health](public-health.log): HTTP200, status ok, transport vk-callback. Это не проверка рабочей БД, очереди или ответа реального VK.
