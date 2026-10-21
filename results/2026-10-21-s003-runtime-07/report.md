# S003 gateway Docker permissions: RED

Независимое ревью выявило создание LocalPrivateStorage в gateway mode под непривилегированным пользователем Docker; относительный runtime/files внутри /app недоступен.
Регрессионный тест воспроизвёл PermissionError: 6passed,1error. [Вывод](tests.log). Исправление — gateway не создаёт файловое хранилище, оно требуется worker/run.
