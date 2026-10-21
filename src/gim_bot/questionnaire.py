import re
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Question:
    key: str
    text: str


QUESTIONS = [
    Question('name', 'Как вас зовут? Укажите ФИО.'),
    Question('email', 'Ваш email для связи?'),
    Question('vk_link', 'Укажите ссылку на вашу страницу ВК для связи (содержимое страницы мы не изучаем).'),
    Question('birth_date', 'Дата рождения в формате ДД.ММ.ГГГГ?'),
    Question('status', 'Ваш нынешний статус: студент, работаю или безработный? Можно указать совмещение.'),
    Question('university', 'В каком вузе учитесь или учились? Если не относится, напишите «не учусь».'),
    Question('university_other', 'Укажите название другого вуза.'),
    Question('faculty', 'Ваш факультет или специальность? Если не относится, так и напишите.'),
    Question('course', 'На каком вы курсе? Если образование окончено, укажите это.'),
    Question('interests', 'Какие у вас научные или познавательные интересы?'),
    Question('experience', 'Расскажите о своём опыте работы, стажировках, проектах или волонтёрстве; можно ответить «пока нет».'),
    Question('languages', 'Какими иностранными языками владеете на уровне B1 и выше? Если таких нет, напишите «нет».'),
    Question('motivation', 'Почему выбрали волонтёрскую программу Исторического музея?'),
    Question('expectations', 'Чего ожидаете от волонтёрства в ГИМ, какие результаты для вас важны?'),
    Question('hours', 'Сколько часов в месяц готовы уделять волонтёрству?'),
    Question('hobbies', 'Ваши хобби и увлечения?'),
    Question('directions', 'Какие направления интересуют: мероприятия, квесты и мастер-классы, фонды, инклюзия, медиа? Можно несколько или «пока не определился».'),
    Question('source', 'Откуда узнали о программе: соцсети, друзья, сайт музея или другое?'),
]
LABELS = {q.key: q.text for q in QUESTIONS}
DIRECTIONS = ('организационное', 'проектное', 'фондовое', 'инклюзивное', 'медиа')


def validate_answer(key: str, text: str, max_length: int = 2000) -> str | None:
    if not text.strip():
        return 'Пожалуйста, напишите ответ текстом.'
    if len(text) > max_length:
        return f'Пожалуйста, сократите ответ до {max_length} символов.'
    if key == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', text):
        return 'Проверьте email, например name@example.org.'
    if key == 'vk_link' and not re.fullmatch(r'https?://(?:www\.)?vk\.(?:com|ru)/[A-Za-z0-9_.-]+/?', text):
        return 'Укажите ссылку вида https://vk.com/имя_страницы.'
    if key == 'birth_date':
        try:
            birthday = datetime.strptime(text, '%d.%m.%Y').date()
            if birthday > date.today() or birthday.year < 1900:
                raise ValueError
        except ValueError:
            return 'Проверьте дату рождения: ДД.ММ.ГГГГ.'
    if key == 'hours':
        match = re.search(r'\d+(?:[.,]\d+)?', text)
        if not match or not 0 <= float(match[0].replace(',', '.')) <= 744:
            return 'Укажите количество часов в месяц числом, можно диапазон.'
    return None


def applicable(key: str, answers: dict) -> bool:
    if key == 'university_other':
        return answers.get('university', '').strip().lower() in ('другое', 'другой')
    if key in ('faculty', 'course'):
        return answers.get('university', '').strip().lower() not in ('не учусь', 'нет', 'не относится')
    return True


def select_followups(answers: dict, limit: int = 3) -> list[dict]:
    direction = answers.get('directions', '').lower()
    questions = []

    def add(topic, question):
        questions.append({'topic': topic, 'question': question, 'answer': '', 'source': 'museum'})

    if 'фонд' in direction:
        add('funds', 'В фондах число мест ограничено. Какие фонды вас привлекают и рассматриваете ли другие направления?')
        add('experience', 'Какие задачи уже выполняли в архиве, коллекции или при работе с каталогом? Если опыта нет, так и напишите.')
    if 'медиа' in direction or 'фото' in direction:
        add('media', 'Какие задачи вы уже выполняли в медиа: тексты, фото, видео, дизайн или контент-план? Расскажите о конкретной работе и своей роли.')
    if 'квест' in direction or 'мастер' in direction or 'проект' in direction:
        add('project', 'Какие квесты, мастер-классы или образовательные игры вы уже помогали создавать? В чём состояла ваша работа?')
    if 'мероприят' in direction or 'организац' in direction:
        add('events', 'С какой аудиторией вы уже работали на мероприятиях и какие задачи выполняли лично?')
    if 'инклюз' in direction:
        add('inclusive', 'Для инклюзивных проектов есть отдельный отбор и обучение. Был ли у вас опыт сопровождения посетителей с инвалидностью, в чём он состоял?')
    if not questions:
        add('experience', 'Какая задача из вашего прошлого опыта могла бы пригодиться музею? Что именно делали лично вы?')
    add('schedule', 'Предпочитаете регулярный или гибкий график? Состоите ли сейчас в других волонтёрских программах и как совмещали подобные обязательства раньше?')
    add('communication', 'В каких прошлых проектах работали в команде или самостоятельно? Какова была ваша роль?')
    known = ' '.join(answers.values()).lower()
    return [q for q in questions if not (q['topic'] == 'schedule' and 'гибкий график' in known)][:limit]
