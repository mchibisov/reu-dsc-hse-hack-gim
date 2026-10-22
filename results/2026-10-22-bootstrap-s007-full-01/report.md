# S007 — полный прогон

Состояние: успешно. После исправления dispatcher и регрессий, включая отмену siblings и освобождение общей аренды. Проверяется весь набор приложения/SQL на отдельной PostgreSQL; REAL_POSTGRES_TESTS=1. Внешние VK/LLM и облачный deployment не затрагиваются.

`python -m pytest -q`: [251 passed in 26.99s](pytest.log), без ошибок/skip. Модель/рубрика не изменены. Следующий ограниченный повтор проверит только новые тесты при max_size=2 у всех трёх pools, как у production drain; SQL tests до этого использовали fixture worker pool=4.
