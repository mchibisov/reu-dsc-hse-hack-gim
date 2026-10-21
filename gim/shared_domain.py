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


def covered_followup_topics(answers,directions):
    """Skip only topics explicitly disclosed; these rules never score skills."""
    texts={slot:a.get('answer_text','').casefold().replace('ё','е') for slot,a in (answers or {}).items()}
    preferences=' '.join(texts.get(s,'') for s in ('expectations','motivation'))
    all_text=' '.join(texts.values())
    covered=set()
    if re.search(r'интерес|хочу|готов|планир|нрав',preferences) and re.search(r'пост|фото|видео|контент|редакт|дизайн|рубрик',preferences):
        covered.add('media_activity')
    if re.search(r'археолог|книжн|рукопис|нумизмат|монет',preferences):
        covered.add('collections_interest')
    if len(directions)>1 or re.search(r'рассматриваю.*друг|готов.*друг.*направлен',all_text):
        covered.add('alternatives')
    if re.search(r'гибк|регуляр|по суббот|по воскрес|по будн|выходн|график',texts.get('available_time','')):
        covered.add('schedule')
    if re.search(r'других.*программ.*нет|не состою|состою.*программ',all_text):
        covered.add('other_commitments')
    if re.search(r'(готов|хочу|предпочитаю).*работать в команде|предпочитаю.*индивидуаль',all_text):
        covered.add('teamwork')
    if not re.search(r'\bне\s+(?:хочу|планирую|готов|собираюсь|интересует)',texts.get('expectations','')) and len(texts.get('expectations','').split())>=7 and re.search(r'научи|навык|опыт|узнать|осво|разв|познаком|изуч|знакомств',texts.get('expectations','')):
        covered.add('expectation_goals')
    return covered


def question_topics(text):
    """Catch personal-contribution rephrasings even with a different model slot."""
    text=' '.join(text.casefold().replace('ё','е').split())
    return {'experience_detail'} if re.search(
        r'\bроль\b|личн\w* вклад|что .*делали лично|задач\w* .*самостоятель|выполня\w* .*самостоятель',text) else set()


def select_followups(templates, questions, directions, maximum, answers=None):
    """Музейная библиотека: выбранное направление, незаданные темы, без экзаменов."""
    asked={str(q.get('template_id')) for q in questions}
    asked_slots={q['target_slot'] for q in questions if q['source']!='base'}|covered_followup_topics(answers,directions)
    for q in questions:
        if q['source']!='base':
            asked_slots|=question_topics(q.get('text',''))
    if any(q.get('purpose')=='expectations' for q in questions):
        asked_slots|={'alternatives','expectation_goals'}
    asked_texts={' '.join(q.get('text','').split()).casefold() for q in questions}
    result=[]
    for t in sorted(templates,key=lambda t:(not bool(t.get('directions')),t['position'])):
        if t['kind']=='base' or str(t['id']) in asked or t['target_slot'] in asked_slots or question_topics(t['text']) & asked_slots:
            continue
        text=t['text'].casefold()
        if ' '.join(text.split()) in asked_texts:
            continue
        if re.search(r'\b(представьте|ситуаци\w*|бы|сделаете|поступите|разработайте|придумайте)\b',text):
            continue
        directed=bool(set(t.get('directions',[])) & set(directions))
        if t.get('directions') and not directed:
            continue
        # General library questions are useful even for a first-time volunteer.
        # Questions explicitly about prior work require actual prior experience.
        past=bool(re.search(r'раньше|ранее|делали|участвовали|работали|занимались',text))
        experience=(answers or {}).get('experience',{}).get('answer_text','').strip().casefold()
        has_experience=bool(experience and experience.rstrip('.!') not in
                            {'нет','не было','не относится','не применимо','опыта нет','нет опыта','не имею опыта'})
        if past and not has_experience:
            continue
        result.append(t)
        if len(result)>=max(0,min(3,maximum)):
            break
    return result if maximum>0 else []
