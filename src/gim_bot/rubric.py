from decimal import ROUND_HALF_UP, Decimal

RUBRIC_VERSION = 'gim-5-v1'
CRITERIA = {
    'motivation': 'Мотивация: конкретная причина выбора ГИМ, осознанные ожидания и интерес к музею; общие фразы — слабое соответствие.',
    'experience': 'Опыт и навыки: личные задачи в музеях, архивах, волонтёрстве, медиа, мероприятиях, инклюзии; профильность образования и опыта учитывается по данным музея.',
    'workload': 'Курс и нагрузка: первый курс и совмещение работы/учёбы учитываются как ограничения; старшие курсы и конкретный доступный график — положительные признаки.',
    'form_quality': 'Качество анкеты: конкретность и полнота содержательных ответов; пустые ответы и отсутствие конкретики — минусы. Закрытость и содержимое ВК не оцениваются.',
    'logistics': 'Логистика: возможность посещать музей, реалистичное время, совмещение программ и готовность к диалогу; неизвестный город не считать отсутствием доступности.',
}


def score_evidence(criteria) -> int | None:
    known = [item for item in criteria if item.level is not None]
    if len(known) < 3 or not any(item.id == 'motivation' for item in known):
        return None
    total = Decimal(sum(item.level for item in known)) * 3 / Decimal(2 * len(known))
    return int(total.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
