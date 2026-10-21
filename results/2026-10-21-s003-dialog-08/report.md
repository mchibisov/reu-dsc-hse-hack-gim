# S003 dialog-08: diagnose export snapshot

dialog-07: роли/опрос/replay/submit/analysis прошли, финальная XLSX assertion не нашла target_slot.
Гипотеза: снимок request_export пуст или изменена структура полей.
Метод: read-only SQL по последнему synthetic recruitment; сохраняются только ключи/количества/статусы, без raw/контактов.
Состояние: запущен.
`nДиагностика завершена; artifacts/diagnostic.txt.
