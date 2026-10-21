# S003 dialog-14: refusal followed by consent regression

Ревью обнаружило потерю согласия после отказа: record_answer очищает active question, отдельный return не готовит повторный consent, следующий ответ только вызывает advance.
Предыдущая проверка dialog-13: 29 GREEN; сценария отказ→согласие не было.
Тест до исправления: отказ сохраняется, новая persisted consent question готова сразу; следующий «Согласен» записывается без повторной отправки. Дополнительно invalid directions→valid и уже существующая invalid date→valid.
Команда: PYTHONPATH=database/src ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий RED: consent regression падает до реализации, остальные invalid base проходят.

Завершён кодом 1. RED сохранён artifacts/tests.txt. Все данные synthetic; сети/БД нет.
