# S003: frozen CI environment GREEN

Повтор в database/ с `uv run --frozen python -m pytest -q --basetemp=../runtime/pytest-ci-03 -p no:cacheprovider`:36passed, без ошибок и skips. [Лог](database-tests.log).
Отличие от ci-02: отдельные basetemp и UV_CACHE_DIR в workspace, без общего ACL-конфликтующего temp/cache. PostgreSQL18.4, SCRAM-SHA256, synthetic данные.
Frozen dependency install и shared unittest из того же uv env проверены в ci-01; migrate idempotence — в ci-02. Docker/GitHub-hosted runner не запускались.
