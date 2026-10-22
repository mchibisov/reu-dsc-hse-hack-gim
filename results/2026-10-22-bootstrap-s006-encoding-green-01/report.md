# S006 — GREEN: UTF-8/BOM

Состояние: успешно. Явная кодировка UTF-8-sig для пользовательских JSON, UTF-8 для приватного JSONL; fixture dotenv пишет UTF-8. Причина повтора — исправление воспроизведённых UnicodeDecodeError/JSONDecodeError и ошибки экспорта Unicode. Сравнение с encoding-red-01.

Те же команды: [1 unittest OK](unittest.log), [3 SQL/material tests passed](pytest.log). Дополнение сценария: [4 passed in 1.44s](bootstrap.log): импорт 19+11 вопросов из синтетических DOCX/PDF, русская рубрика и Unicode совпали с исходными; созданы три реальные LOGIN и первый admin, набор активирован, CLI check-db прошёл. Проверен расчёт метрик по синтетическому UTF-8 BOM JSONL. Дополнение не измеряет модельную точность. По review добавлен finally для удаления временных LOGIN, проверенный общим повтором full-02.
