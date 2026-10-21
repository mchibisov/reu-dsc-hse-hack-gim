# Совместимость исходного VK-бота

Корневая unittest suite без DB DSN:89tests,61passed28skipped, [лог](unit-tests.log). Compileall gim/database/src успешен.
На отдельной disposable БД `gim_legacy_test`, public migrations успешны: [лог](legacy-migrate.log). Private БД для legacy tests не использовалась.
Legacy DB suite:8tests,7passed1skipped (явный флаг multi-session не включён): [лог](legacy-db-tests.log). Legacy service suite:16passed: [лог](legacy-service-tests.log).
Реальный VK и производственная среда не проверены этим запуском.
