# Проверка uv.lock

`uv lock --project database --python ./.venv/Scripts/python.exe --check` завершён кодом0,25 packages resolved. [Вывод](check.log).
uv0.13.4 установлен как инструмент в локальном dev venv; runtime от uv не зависит. Lock после удаления Redis/ARQ признан актуальным штатным resolver; GitHub Actions пока не запускался.
