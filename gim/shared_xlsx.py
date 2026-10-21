"""XLSX строго из сохранённого снимка; продолжения не теряют исходный текст."""
import io
import json
import re
import zipfile
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font

SHEETS=('Анкеты','Ответы','Собеседование','Сводка')
HEADERS={
    'application_id':'ID анкеты','vk_id':'VK ID','full_name':'ФИО','email':'Email',
    'birth_date':'Дата рождения','birth_date_raw':'Дата рождения (ответ)',
    'status':'Статус','decision':'Решение сотрудника','selected_directions':'Выбранные направления',
    'undecided':'Направление не выбрано','answers_revision':'Версия ответов','submitted_at':'Подана',
    'evaluation_id':'ID оценки','score':'Балл 0–3','evaluation_source':'Источник оценки',
    'reviewer_staff_id':'ID сотрудника','reviewer_name':'Сотрудник','summary':'AI-сводка',
    'recommended_directions':'Рекомендованные направления','criteria_results':'Критерии и цитаты',
    'evaluation_revision':'Версия оценки','evaluated_at':'Дата оценки','evaluation_stale':'Оценка устарела',
    'question_id':'ID вопроса','position':'Порядок вопроса','question_text':'Вопрос',
    'question_source':'Источник вопроса','purpose':'Назначение вопроса','target_slot':'Поле анкеты',
    'answer_id':'ID ответа','revision':'Версия','answer_text':'Ответ кандидата',
    'created_at':'Дата ответа','is_latest':'Последняя версия ответа','interview_questions':'Вопросы для собеседования',
    'expectations':'Ответы об ожиданиях','metric':'Показатель','value':'Значение',
    'continuation_part':'Часть текста','continuation_total':'Всего частей','field_encodings':'Кодировка полей',
}
LABELS={
    'status':{'draft':'Черновик','submitted':'Подана','withdrawn':'Отозвана'},
    'decision':{'pending':'Не принято','invited':'Приглашён','accepted':'Принят','rejected':'Отказ'},
    'evaluation_source':{'algorithm':'AI','curator':'Сотрудник'},
    'metric':{'total':'Всего анкет','scored':'С оценкой','unscored':'Без оценки','average_score':'Средний балл',
              'score_distribution':'Распределение баллов','directions':'Направления','decisions':'Решения сотрудников'},
}



def _text(value):
    if value is None:
        return ''
    if isinstance(value,(dict,list)):
        return json.dumps(value,ensure_ascii=False,default=str,sort_keys=True)
    return str(value)


def snapshot_xlsx(snapshot):
    wb=Workbook()
    wb.remove(wb.active)
    wb.properties.created=wb.properties.modified=datetime(2000,1,1)
    for name in SHEETS:
        sheet=wb.create_sheet(name)
        data=snapshot.get(name,[] if name!='Сводка' else {})
        if isinstance(data,dict):
            data=[dict(metric=k,value=v) for k,v in data.items()]
        prepared=[]
        for record in data:
            record=dict(record)
            for key,labels in LABELS.items():
                if isinstance(record.get(key),str):
                    record[key]=labels.get(record[key],record[key])
            encoded={}
            for key,value in list(record.items()):
                text=_text(value)
                if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',text):
                    record[key]=json.dumps(text,ensure_ascii=False)
                    encoded[key]='json_string'
            if encoded:
                record['field_encodings']=encoded
            prepared.append(record)
        data=prepared
        columns=list(dict.fromkeys(k for row in data for k in row)) or ['Нет данных']
        columns += ['continuation_part','continuation_total']
        sheet.append([HEADERS.get(k,k) for k in columns])
        for cell in sheet[1]:
            cell.font=Font(bold=True)
        for row in data:
            # 15000 code points also fit Excel's UTF-16 limit for astral emoji.
            chunks={k:[_text(row.get(k))[i:i+15000] for i in range(0,len(_text(row.get(k))),15000)] or [''] for k in columns[:-2]}
            total=max(map(len,chunks.values()))
            for n in range(total):
                values=[]
                for k in columns[:-2]:
                    # Carry identifiers on continuation rows; split each other field losslessly.
                    v=chunks[k]
                    values.append(v[n] if n<len(v) else (v[0] if k.endswith('_id') else ''))
                sheet.append(values+[str(n+1),str(total)])
                for cell in sheet[sheet.max_row]:
                    cell.data_type='s'
        sheet.freeze_panes='A2'
        sheet.auto_filter.ref=sheet.dimensions
    data=io.BytesIO()
    wb.save(data)
    # Fixed ZIP timestamps make crash retry byte-identical for immutable storage.
    output=io.BytesIO()
    with zipfile.ZipFile(data) as source,zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            item.date_time=(2000,1,1,0,0,0)
            content=source.read(item.filename)
            if item.filename=='docProps/core.xml':
                # openpyxl updates modified during save regardless of properties.
                content=re.sub(rb'(<dcterms:modified[^>]*>).*?(</dcterms:modified>)',
                               rb'\g<1>2000-01-01T00:00:00Z\g<2>',content)
            target.writestr(item,content)
    return output.getvalue()
