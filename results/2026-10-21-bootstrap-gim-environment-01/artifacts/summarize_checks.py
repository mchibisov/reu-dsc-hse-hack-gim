"""Сохранение отдельных отчётов фактических локальных проверок (без перезаписи)."""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[3]
results = root / 'results'
for directory in sorted(results.glob('2026-10-21-bootstrap-gim-*')):
    report = directory / 'report.md'
    log = directory / 'artifacts' / 'pytest.txt'
    if report.exists() or not log.exists():
        continue
    data = log.read_bytes()
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        text = data.decode('cp1251', errors='replace')
    lines = [line.strip('= \r\n') for line in text.splitlines()
             if re.search(r'\d+ (?:passed|failed|errors?|skipped)', line)]
    if not lines:
        continue
    summary = lines[-1]
    failed = bool(re.search(r'\b[1-9]\d* (?:failed|errors?)\b', summary))
    status = 'ошибка' if failed else 'завершён'
    conclusion = 'недостаточно данных о работоспособности реализации' if failed else 'подтверждена в проверенных условиях'
    report.write_text(f'''# Bootstrap: {directory.name}

- Дата: 2026-10-21, Europe/Moscow.
- Состояние запуска: {status}.
- Спецификация: [S002](../../docs/specs/S002-gim-vk-bot.md).
- Окружение: Windows, Python 3.12.14, отдельная venv в `gim_bot`; зависимости в requirements.lock.
- Метод и критерий: pytest на соответствующем модуле; RED должен воспроизвести отсутствие реализации/дефект, GREEN — пройти после изменения. Конкретные имена тестов и трассировка в артефакте.
- Фактический итог: **{summary}**.
- Доказательства: [pytest.txt](artifacts/pytest.txt).

## Вывод и ограничения

Вывод: {conclusion}. Этот запуск проверяет только указанные в логе локальные сценарии. Настоящие VK, LLM, PostgreSQL/Redis, Docker, длительность человеческого опроса и качество экспертного ранжирования не подтверждены.

Следующий шаг: при RED — реализовать/исправить и сохранить следующий отдельный запуск; при GREEN — интеграционное и независимое ревью. Прошлые результаты не перезаписываются.
''', encoding='utf-8')

journal = root / 'docs/hypotheses.md'
text = journal.read_text(encoding='utf-8')
for directory in sorted(results.glob('2026-10-21-bootstrap-gim-*')):
    if not (directory / 'report.md').exists() or f'../results/{directory.name}/report.md' in text:
        continue
    text += f'\n| 2026-10-21 | {directory.name.removeprefix("2026-10-21-bootstrap-")} | [отчёт](../results/{directory.name}/report.md) |'
journal.write_text(text.rstrip() + '\n', encoding='utf-8')
