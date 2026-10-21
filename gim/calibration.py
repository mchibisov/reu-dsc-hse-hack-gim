"""Командная рубрика MVP и закрытые ориентиры по экспертной разметке музея.

Исходные анкеты не входят в Git. Обучение модели не заявляется: используются
восемь примеров с экспертными метками, отдельно от воспроизводимого holdout.
"""
import hashlib

from gim.shared_analysis import safe_answers


def split_history(records):
    ordered=sorted(records,key=lambda r:r['id'])
    holdout=lambda r:int(hashlib.sha256(r['id'].encode()).hexdigest(),16)%5==0
    return ([r for r in ordered if not holdout(r)],[r for r in ordered if holdout(r)])


def reference_examples(records, per_score=2):
    examples=[]
    for score in range(4):
        candidates=sorted((r for r in records if r['expert_score']==score),
                          key=lambda r:hashlib.sha256(r['id'].encode()).hexdigest())
        selected=[]
        # Prefer different recruitment years when this label exists in both.
        for record in candidates:
            if record.get('cohort') not in {r.get('cohort') for r in selected}:
                selected.append(record)
            if len(selected)>=per_score:
                break
        for record in candidates:
            if len(selected)>=per_score:
                break
            if record not in selected:
                selected.append(record)
        for record in selected:
            answers=safe_answers([{'id':f'{record["id"]}:{slot}', 'target_slot':slot,'answer_text':str(text)}
                                  for slot,text in record['features'].items() if text is not None])
            budget=2400; compact=[]
            for answer in sorted(answers,key=lambda a:(a['slot'] not in {'expectations','experience','interests'},a['slot'])):
                if budget<=0:
                    break
                text=answer['text'][:min(600,budget)]
                compact.append({'slot':answer['slot'],'text':text})
                budget-=len(text)
            examples.append({'id':record['id'],'expert_score':score,'answers':compact})
    return examples


def museum_rubric(records):
    train,holdout=split_history(records)
    return {
        'approved_by':'MVP: реализация задания пользователя от 21.10.2026; веса команды, не утверждены музеем',
        'scoring_method':'sum_available_round_half_up',
        'minimum_evidence_weight':0.7,
        'scoring_rule':'3 * сумма баллов подтверждённых групп / сумма их максимумов; округление 0.5 вверх до 0–3. Неизвестная группа: points=0, needs_review=true, исключена из числителя и знаменателя. Нужны цитаты не менее чем для 70% веса, иначе только ручная проверка. 0 — не приглашали, 1 — слабая, 2 — средняя, 3 — хорошая анкета. Ориентир — экспертные примеры; не подгонять балл отдельно от критериев.',
        'criteria':[
            {'code':'motivation','name':'Мотивация и осознанность','max_points':0.9,
             'description':'Конкретные ожидания, интерес к истории и задачам ГИМ, понимание своего вклада. Общие фразы слабее конкретных целей. Не штрафовать за фондовое направление само по себе: выяснить гибкость интересов.'},
            {'code':'experience','name':'Опыт и навыки','max_points':0.9,
             'description':'Подтверждённый музейный или смежный опыт, личный вклад, применимые навыки. Учитывать переносимые навыки из других сфер; отсутствие записи об опыте не доказывает неспособность.'},
            {'code':'availability','name':'Учёба и нагрузка','max_points':0.45,
             'description':'Ясность текущей занятости и реалистичность обещанного времени. Курс и образование дают контекст; не штрафовать автоматически за первый курс или работу. Последующие фактические часы участия запрещены.'},
            {'code':'completeness','name':'Качество анкеты','max_points':0.45,
             'description':'Содержательность, конкретность и согласованность ответов. Страницу VK не просматриваем; закрытый профиль, внешность и цифровой след не оцениваем.'},
            {'code':'logistics','name':'Логистика и взаимодействие','max_points':0.3,
             'description':'Готовность взаимодействовать с музеем, посещать мероприятия и совмещать обязанности, если об этом прямо сказано. Не предполагать город или график по вузу. Если данных для отдельного вывода нет, needs_review=true с цитатой доступного контекста.'},
        ],
        'direction_assessment_required':True,
        'history_examples':reference_examples(train),
        'calibration':{'total':len(records),'train':len(train),'holdout':len(holdout),
                       'method':'8 balanced expert examples; deterministic SHA256(id) % 5 holdout',
                       'limitations':'Малая выборка, разные распределения 2024/2025; веса предварительные; это не обученная или валидированная экспертами модель.'},
    }
