# S004: скрытая выгрузка и регрессия, GREEN 05

- Дата: 2026-10-21, Europe/Moscow; запуск завершён.
- Предыдущая проверка: [04](../2026-10-21-bootstrap-hidden-export-04/report.md); заменено фиксированное окно на SQL timestamps неуспешных попыток за скользящие 600 секунд.
- Критерий до проверки: все 13 сценариев скрытой выгрузки и полный suite проходят; существующий admin export сохраняет поведение.
- Окружение: Windows, `.venv/Scripts/python.exe`, SQLite в `runtime/pytest-hidden-full`, synthetic ответы, VK fake, без HTTP.
- Воспроизведение из gim_bot: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=runtime/pytest-hidden-full`; `.venv/Scripts/python.exe -m ruff check src/gim_bot/config.py src/gim_bot/export_access.py src/gim_bot/storage.py src/gim_bot/bot.py src/gim_bot/worker.py tests/test_hidden_export.py`.
- Факт: **70 passed, 1 skipped за 44.19s**, lint: **All checks passed**; [pytest](artifacts/pytest.txt).
- Покрыто: `/excel` до анкеты; отсутствие секрета в MessageEvent/ответах/repr; отсутствие подсказок; неверный/пустой код и чужой peer; отсутствие staff-доступа к чужой анкете; выдача Excel получателю; повтор события и worker; ротация до отправки и во время upload; restart limiter; границы скользящего окна; replay без расхода попыток; конкурентный event из двух соединений SQLite; обычный admin export.
- Реализация создаёт только три новые технические таблицы `code_export_attempts`, `code_export_limits`, `code_export_permits` через create_all. Существующие таблицы и анкеты не мигрируются.
- Вывод: требования R401–R402 подтверждены локально в перечисленных условиях. Реальные .env, два существующих ответа, процесс и VK не затронуты; PostgreSQL и реальная доставка не проверялись.
- Ограничение: между финальной проверкой permit и сетевым send остаётся обычное неатомарное окно; VK send использует детерминированный export request key, а запрос помечается sent после успешного send. Файл, загруженный перед ротацией во время upload, не отправляется сообщением.
