# S006 — RED: кодировки русских конфигов

Состояние: завершено, дефекты воспроизведены. Регрессии воспроизводят UTF-8 BOM в конфигурации импорта/рубрики и Unicode вне cp1251 в приватном JSONL. Эти файлы создаются пользователем в Windows; должны сохранять исходный текст. Предыдущий baseline выявил системную зависимость от кодировки.

Команды: `python -m unittest discover -s tests -p test_config_encoding.py -v` и `python -m pytest database/tests/test_materials.py -q`.

Результаты: [1 error при начале анкеты](unittest.log), JSONDecodeError при чтении BOM системной кодировкой; [2 failed, 1 passed](pytest.log): запись JSONL с Unicode вне cp1251 и импорт UTF-8 BOM. Набор не импортировался, новая анкета не продолжалась. Исправление: явные UTF-8/UTF-8-sig, без замены/игнорирования недекодируемых символов.
