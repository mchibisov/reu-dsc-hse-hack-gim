"""Contextual fallback questions; optional team service may refine this plan."""
from gim.dialog import QUESTIONS

DETAILS = {
    'events': (('дет', 'посетител', 'экскурс', 'мероприят'), 'Вы уже описали опыт работы с людьми. Приведите пример сложной ситуации на мероприятии: что вы сделали и чем всё закончилось?'),
    'projects': (('квест', 'мастер', 'игр', 'рисова', 'худож'), 'Вы упомянули творческий опыт. Как адаптировали бы одну свою идею в квест или мастер-класс об истории для посетителей музея?'),
    'funds': (('архив', 'каталог', 'документ', 'оцифров', 'камис'), 'Вы описали опыт с документами или каталогами. Как проверяли точность записей и исправляли обнаруженные ошибки?'),
    'inclusion': (('инвалид', 'инклюз', 'тактиль', 'слабовид'), 'Вы упомянули опыт инклюзивной работы. Приведите пример адаптации задания под потребности конкретного посетителя. Чему ещё хотели бы научиться?'),
    'media': (('фото', 'видео', 'монтаж', 'дизайн', 'текст', 'редакт', 'контент'), 'Вы упомянули навыки фото, видео, текстов или дизайна. Выберите одну свою работу: какая была задача, что именно сделали вы и какой результат получили?'),
}


def plan_followups(directions, answers):
    context = ' '.join(str(value) for key, value in answers.items() if key in ('experience', 'strengths', 'hobbies')).casefold()
    return [{'direction': d, 'text': DETAILS[d][1] if any(term in context for term in DETAILS[d][0])
             else QUESTIONS['followup_' + d]} for d in directions]


def validate_plan(plan, directions):
    if not isinstance(plan, list) or len(plan) > min(5, len(directions)):
        raise ValueError('Invalid follow-up count')
    seen_directions, seen_text = set(), set()
    for item in plan:
        if not isinstance(item, dict):
            raise ValueError('Invalid follow-up')
        direction, text = item.get('direction'), item.get('text')
        if direction not in directions or direction in seen_directions:
            raise ValueError('Invalid or repeated direction')
        if not isinstance(text, str) or not 10 <= len(text.strip()) <= 1000 or text.casefold().strip() in seen_text:
            raise ValueError('Invalid or repeated question')
        seen_directions.add(direction)
        seen_text.add(text.casefold().strip())
    return plan
