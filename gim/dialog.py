from copy import deepcopy

DIRECTIONS = {
    'events': ('Мероприятия', ('мероприят', '1')),
    'projects': ('Квесты и мастер-классы', ('проект', 'квест', 'мастер', '2')),
    'funds': ('Фонды', ('фонд', '3')),
    'inclusion': ('Инклюзия', ('инклюз', '4')),
    'media': ('Медиа', ('медиа', '5')),
}
QUESTIONS = {
    'name': 'Как к вам обращаться?',
    'interests': 'Где и чему вы учитесь или работаете? Какие у вас научные и другие интересы?',
    'experience': 'Расскажите об опыте работы, стажировок, проектов или волонтёрства. Если опыта нет, так и напишите.',
    'languages': 'Какими иностранными языками вы владеете на уровне B1 и выше? Можно ответить «нет».',
    'directions': 'Что вам интересно? Можно выбрать несколько номеров:\n1. Мероприятия\n2. Квесты и мастер-классы\n3. Фонды\n4. Инклюзия\n5. Медиа',
    'motivation': 'Чего вы ожидаете от волонтёрства в Историческом музее?',
    'availability': 'Сколько времени вы готовы уделять волонтёрству? В какие дни и часы вам удобно?',
    'hobbies': 'Какие у вас увлечения?',
    'strengths': 'В чём ваша суперсила? Какие навыки вы хотели бы применить?',
    'source': 'Откуда вы узнали о наборе?',
    'expectations': 'Совпали ли эти задачи с вашими ожиданиями? Какие альтернативные направления вы готовы рассмотреть? Можно ответить «никакие».',
}
BASE = ['name', 'interests', 'experience', 'languages', 'directions', 'motivation',
        'availability', 'hobbies', 'strengths', 'source']
TASKS = {
    'events': 'Мероприятия: координация посетителей и помощь в проведении событий.',
    'projects': 'Проекты: разработка игр, квестов и мастер-классов.',
    'funds': 'Фонды: оцифровка, каталоги и маркировка; доступность мест уточняет куратор.',
    'inclusion': 'Инклюзия: помощь на специальных мероприятиях, отдельный отбор и обучение.',
    'media': 'Медиа: тексты, контент-план, фото, видео и дизайн.',
}


def transition(state, text, require_consent=True):
    """Return new state, answered code, reply, and first-submission flag."""
    s = deepcopy(state)
    text = text.strip()
    step = s.get('step')
    if step == 'submitted':
        return s, None, 'Анкета уже отправлена. Решение принимает куратор после собеседования.', False
    if not step:
        fresh = {**s, 'step': 'consent' if require_consent else 'name', 'directions': []}
        if not require_consent:
            return fresh, None, s.get('questions', {}).get('name', QUESTIONS['name']), False
        return fresh, None, 'Перед началом прочитайте условия обработки данных. Для продолжения напишите «Согласен».', False
    if step == 'planning':
        return s, None, 'Готовлю уточняющие вопросы по вашим ответам. Пришлю следующий вопрос отдельным сообщением.', False
    if step == 'consent':
        if text.casefold() not in ('согласен', 'согласна'):
            return s, None, 'Без согласия заполнение не начнётся. Для продолжения напишите «Согласен» или вернитесь позже.', False
        s['step'] = 'name'
        return s, 'consent', s.get('questions', {}).get('name', QUESTIONS['name']), False
    if not text or len(text) > 10000:
        return s, None, 'Отправьте текстовый ответ длиной от 1 до 10000 символов.\n' + s.get('questions', {}).get(step, QUESTIONS.get(step, '')), False
    if step == 'directions':
        import re
        words = re.split(r'[\s,;]+', text.casefold())
        selected = [key for key, (_, terms) in DIRECTIONS.items()
                    if any((term in words if term.isdigit() else term in text.casefold()) for term in terms)]
        if not selected:
            return s, None, QUESTIONS['directions'], False
        s['directions'] = selected
    if step == 'expectations':
        s['step'] = 'submitted'
        return s, step, 'Спасибо! Анкета сохранена и передана куратору. Окончательное решение принимает человек.', True
    if step.startswith('followup_') or step == s.get('base_codes', BASE)[-1]:
        s['step'] = 'planning'
        return s, step, 'Ответ сохранён. Готовлю следующий вопрос по всей анкете.', False
    sequence = s.get('base_codes', BASE)
    index = sequence.index(step)
    s['step'] = sequence[index + 1]
    reply = s.get('questions', {}).get(s['step'], QUESTIONS.get(s['step'], ''))
    if s['step'] == 'expectations':
        reply = '\n'.join(s.get('tasks', TASKS)[d] for d in s['directions']) + '\n\n' + reply
    return s, step, reply, False
