# S003 gateway: GREEN

Повтор с Windows Selector и исправленными UTF8 миграциями: 2 интеграционных теста прошли на изолированной PostgreSQL18.4. [Вывод](tests.log).
Подтверждены singleton lease, dedupe события, batch/checkpoint, fencing старого токена и запрет смены группы.
