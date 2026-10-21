# S003 dialog-16: no invented past experience

Ревью P2: directed template обходил фильтр past/has_experience, потому вопросы об интересах могли попасть в уточнения прошлого опыта.
Гипотеза до изменения: followup допускается только при реальном ответе с опытом, past wording и пустом restriction directions либо пересечении с выбранными направлениями.
Новый тест: directed interest + «нет» опыта даёт 0; при описанном опыте выбираются past по своему направлению и unrestricted past, не interest/чужое направление.
Команда: PYTHONPATH=database/src ../gim_bot/.venv/Scripts/python.exe -m unittest discover -s tests -p test_shared_service.py -v
Критерий: RED до изменения select_followups.

Завершён кодом 1, RED artifacts/tests.txt. Внешних API/БД нет.
