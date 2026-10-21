"""Пользовательский запуск из произвольной папки, без VK/LLM/Redis."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / 'main.py'


def test_console_launcher_completes_and_saves_questionnaire(tmp_path):
    database = tmp_path / 'console.db'
    answers = '\n'.join([
        'Согласен', 'Тестовый Кандидат', 'example@example.org',
        'https://vk.com/id123', '01.01.2000', 'работаю', 'не учусь',
        'История Москвы', 'Снимал музейные мероприятия и отбирал фотографии.',
        'Английский B2', 'Хочу помогать Историческому музею',
        'Получить опыт музейной фотографии', '10', 'Фотография', 'медиа', 'друзья',
        'Снимал музейные события камерой.', 'Готов совмещать по выходным.',
        'Работал фотографом в команде.', '/quit', '',
    ])
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), '--database', str(database)],
        input=answers, text=True, encoding='utf-8', capture_output=True,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, cwd=tmp_path, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert 'получена' in result.stdout.lower()
    assert 'traceback' not in result.stderr.lower()
    with sqlite3.connect(database) as connection:
        row = connection.execute('SELECT status, score, analysis_status FROM applications').fetchone()
    assert row == ('completed', None, 'no_analytics')


def test_console_launcher_exits_cleanly_at_end_of_input(tmp_path):
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), '--database', str(tmp_path / 'empty.db')],
        input='', text=True, encoding='utf-8', capture_output=True,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, cwd=tmp_path, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert 'соглас' in result.stdout.lower()
