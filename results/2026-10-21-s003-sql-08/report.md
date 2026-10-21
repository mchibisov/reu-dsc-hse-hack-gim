# S003 SQL — запуск 08

Цель: полный database набор на изолированном localhost:55439/gim_private_test.
Команда: `pytest -q database/tests` через gim_bot/.venv с PYTHONPATH=database/src
и явным TEST_DATABASE_URL. Результат: 5 failed, 31 passed, 5.75s; завершён.

Провалы: test_zero_is_not_missing_and_no_100_application_cap,
test_evidence_manual_priority_and_staff_revocation, test_50_concurrent_candidates,
test_export_request_freezes_data — KeyError русских ключей export_bundle;
test_real_login_provisioning — subprocess provision_runtime.py exit 1.
SQLQueue/runtime targeted suite прошла отдельно в запуске 07.

Родитель установил причину неверных export keys: migrate.py читает SQL без
явного UTF-8 в Windows, создавая функции с испорченными строками.
На момент отчёта родитель исправляет loader и пересоздаёт только тестовую БД;
новые подключения остановлены до его сигнала. Причина provisioning exit 1
в этом запуске ещё не определена, stderr скрыт исходным тестом capture_output.
Вывод: регрессия полного набора опровергнута; есть инфраструктурные дефекты,
нельзя выдавать 31 passed за полную приёмку.
Доказательство: [pytest.txt](artifacts/pytest.txt).
