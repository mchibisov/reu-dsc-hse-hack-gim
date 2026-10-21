"""Разбор проверяемых полей и выбор исключительно библиотечных уточнений."""
import re
from datetime import datetime, date
from zoneinfo import ZoneInfo

DIRECTIONS = ('organizational','project','collections','inclusive','media')
ALIASES = {
    'organizational': ('организац','мероприят'), 'project': ('проект',),
    'collections': ('фонд','коллекц'), 'inclusive': ('инклюз',), 'media': ('медиа',),
}


def parse_answer(slot, raw):
    text = raw.strip()
    low = text.casefold().replace('ё','е')
    if not text:
        return None, 'Ответ не должен быть пустым.'
    if slot == 'consent':
        accepted = low.rstrip('.!') in {'да','согласен','согласна','даю согласие','принимаю'}
        return accepted, None if accepted else 'Без явного согласия анкету подать нельзя. Для продолжения ответьте «Согласен», если принимаете условия согласия в вопросе.'
    if slot == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',text):
        return None, 'Укажите email в формате name@example.ru.'
    if slot == 'vk_url' and not re.fullmatch(r'(?:https?://)?(?:www\.)?vk\.(?:com|ru)/[A-Za-z0-9_.-]+/?',text):
        return None, 'Укажите ссылку на страницу VK: https://vk.com/имя.'
    if slot == 'birth_date':
        parsed = None
        for fmt in ('%d.%m.%Y','%Y-%m-%d','%d/%m/%Y'):
            try:
                parsed = datetime.strptime(text,fmt).date()
                break
            except ValueError:
                pass
        if parsed is None:
            return None, 'Для подачи по правилам действующей базы нужна полная дата рождения: ДД.ММ.ГГГГ.'
        today = datetime.now(ZoneInfo('Europe/Moscow')).date()
        age = today.year-parsed.year-((today.month,today.day)<(parsed.month,parsed.day))
        if parsed < date(1900,1,1) or age < 18:
            return parsed.isoformat(), 'Действующая база принимает заявки только с 18 лет. Сохранённый ответ не позволяет подать анкету; если дата указана ошибочно, введите верную полную дату.'
        return parsed.isoformat(), None
    if slot == 'directions':
        if low.rstrip('.!') in {'не определился','не определилась','пока не определился','пока не определилась','не знаю','undecided','0','6'}:
            return {'selected_directions':[], 'undecided':True},None
        selected=[]
        for i,code in enumerate(DIRECTIONS,1):
            if code in low or any(alias in low for alias in ALIASES[code]) or re.search(r'(?<!\d)'+str(i)+r'(?!\d)',low):
                selected.append(code)
        if not selected:
            return None, 'Для подачи выберите направление: 1 — организационное, 2 — проектное, 3 — фондовое, 4 — инклюзивное, 5 — медиа; либо напишите «не определился».'
        return {'selected_directions':selected,'undecided':False},None
    return text,None


def latest_slots(context):
    questions = {str(q['id']):q for q in context['questions']}
    slots={}
    for answer in sorted(context['answers'],key=lambda a:a['revision']):
        q=questions.get(str(answer['question_id']))
        if q and q['source']=='base':
            slots[q['target_slot']]=answer
    return slots


def select_followups(templates, questions, directions, maximum, answers=None):
    """Отклоняем гипотетические задания; при отсутствии подходящих вопросов пропускаем.

    Никакие ситуации/компетенции не генерируются. Уточняется только описанный
    прошлый опыт; ограничение направления шаблона требует явного выбора кандидата.
    """
    asked={str(q.get('template_id')) for q in questions}
    asked_slots={q['target_slot'] for q in questions if q['source']!='base'}
    result=[]
    for t in sorted(templates,key=lambda t:t['position']):
        if t['kind']=='base' or str(t['id']) in asked or t['target_slot'] in asked_slots:
            continue
        text=t['text'].casefold()
        if re.search(r'\b(представьте|ситуаци\w*|бы|сделаете|поступите|разработайте|придумайте)\b',text):
            continue
        directed=bool(set(t.get('directions',[])) & set(directions))
        past=bool(re.search(r'опыт|раньше|ранее|делали|участвовали|работали|занимались',text))
        experience=(answers or {}).get('experience',{}).get('answer_text','').strip().casefold()
        has_experience=bool(experience and experience.rstrip('.!') not in
                            {'нет','не было','не относится','не применимо','опыта нет','нет опыта','не имею опыта'})
        if not (past and has_experience and (not t.get('directions') or directed)):
            continue
        result.append(t)
        if len(result)>=max(0,min(3,maximum)):
            break
    return result if maximum>0 else []
