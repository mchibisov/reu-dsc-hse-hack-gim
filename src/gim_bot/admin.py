from collections import Counter

from .config import Settings
from .export import STATUS
from .questionnaire import LABELS

HELP = 'Команды куратора: /top [N], /candidate ID, /export, /stats. Редактирование оценок не поддерживается.'


class Admin:
    def __init__(self, store, settings: Settings):
        self.store = store
        self.settings = settings

    async def handle(self, user_id: int, peer_id: int, text: str, event_id: str) -> str | None:
        if user_id not in self.settings.admins or peer_id != user_id:
            return None
        parts = text.strip().split()
        command = parts[0].lower() if parts else ''
        if command in ('/admin', '/help'):
            return HELP
        if command == '/top':
            try:
                count = max(1, min(100, int(parts[1]) if len(parts) > 1 else 10))
            except ValueError:
                return 'Используйте /top 10.'
            apps = await self.store.list_applications()
            lines = [f"ID {a.id} · {a.score if a.score is not None else 'без балла'} · "
                     f"{(a.analysis or {}).get('recommended_direction', '')} · {a.answers.get('name', '')}"
                     for a in apps[:count]]
            return '\n'.join(lines) or 'Завершённых анкет пока нет.'
        if command == '/candidate':
            try:
                app = await self.store.get(int(parts[1]))
            except (ValueError, IndexError):
                return 'Используйте /candidate ID.'
            if not app:
                return 'Анкета не найдена.'
            analysis = app.analysis or {}
            lines = [f'Анкета ID {app.id}', f'Аналитика: {STATUS.get(app.analysis_status, app.analysis_status)}',
                     f"Балл: {app.score if app.score is not None else 'отсутствует'}",
                     f"Рубрика: {app.rubric_version or 'не применялась'}"]
            lines += [f'{LABELS.get(key, key)}\n{value}' for key, value in app.answers.items()]
            lines += [f"Уточнение: {q['question']}\n{q.get('answer', '')}" for q in app.followups]
            if analysis:
                lines += [f"Резюме: {analysis['summary']}", f"Направление: {analysis['recommended_direction']}",
                          analysis['rationale']]
                lines += [f"{c['id']}: {c['level']} — {c['explanation']}\n«{c['quote']}» ({c['field']})"
                          for c in analysis['criteria']]
                lines += ['На собеседовании: ' + q for q in analysis['interview_questions']]
            lines.append('Решение о приёме принимает сотрудник музея.')
            return '\n\n'.join(lines)
        if command == '/export':
            request_id = await self.store.request_export(user_id, f'{user_id}:{event_id}')
            return f'Выгрузка №{request_id} поставлена в очередь. Файл придёт в этот диалог.'
        if command == '/stats':
            all_apps = await self.store.list_applications(completed_only=False)
            completed = [a for a in all_apps if a.status == 'completed']
            counts = Counter(a.score for a in completed)
            directions = Counter((a.analysis or {}).get('recommended_direction', 'не определено') for a in completed)
            return (f'Начато: {len(all_apps)}\nЗавершено: {len(completed)}\n'
                    f'Без балла: {counts[None]}\n' + '\n'.join(f'Балл {n}: {counts[n]}' for n in range(4))
                    + '\nНаправления:\n' + '\n'.join(f'{k}: {v}' for k, v in directions.items()))
        if command.startswith('/') and command not in ('/start', '/status', '/delete'):
            return 'Команда не поддерживается.\n' + HELP
        return None
