"""XLSX строго из сохранённого снимка; продолжения не теряют исходный текст."""
import io
import json
import re
import zipfile
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import DataBarRule
from gim.shared_analysis import DIRECTION_NAMES

SHEETS=('Анкеты','Ответы','Собеседование','Сводка')
HEADERS={
    'application_id':'ID анкеты','vk_id':'VK ID','full_name':'ФИО','email':'Email',
    'birth_date':'Дата рождения','birth_date_raw':'Дата рождения (ответ)',
    'status':'Статус','decision':'Решение сотрудника','selected_directions':'Выбранные направления',
    'undecided':'Направление не выбрано','answers_revision':'Версия ответов','submitted_at':'Подана',
    'evaluation_id':'ID оценки','ranking_score':'Рейтинг S 0–3','candidate_profile':'Профиль кандидата','score':'Балл 0–3','evaluation_source':'Источник оценки',
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
HEADERS.update({'ai_score':'Исходный балл AI','ai_summary':'Исходное резюме AI','criterion':'Критерий','criterion_status':'Статус критерия','reason':'Обоснование','quote':'Подтверждающая цитата','points':'Вклад в оценку','source_id':'ID исходного ответа','fact':'Проверяемый факт','group_share':'Основания / максимум группы','group_points':'Баллы группы','full_ai_report':'Полный AI-отчёт'})
ORDER={
 'Анкеты':['full_name','ranking_score','score','ai_score','status','decision','selected_directions','recommended_directions','summary','candidate_profile','ai_summary','email','submitted_at','evaluated_at','criteria_results'],
 'Ответы':['application_id','position','question_text','answer_text','question_source','purpose','target_slot','is_latest'],
 'Собеседование':['application_id','summary','expectations','interview_questions'],
 'Оценка':['full_name','criterion','fact','criterion_status','group_points','group_share','points','reason','quote','application_id','source_id'],
 'Сводка':['metric','value'],
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
    from gim.ranking import ranked_bundle
    snapshot=ranked_bundle({**snapshot,'Анкеты':[dict(r) for r in snapshot.get('Анкеты',[])]})
    from gim.dashboard import dashboard
    for row in snapshot.get('Анкеты',[]):row['candidate_profile']=dashboard(row)
    wb=Workbook()
    wb.remove(wb.active)
    wb.properties.created=wb.properties.modified=datetime(2000,1,1)
    proof=[]
    from gim.dashboard import dimensions
    for app in snapshot.get('Анкеты',[]):
        shares={d['code']:d['fraction'] for d in dimensions(app)}
        for criterion in app.get('criteria_results') or []:
            items=criterion.get('facts') or [criterion]
            for index,item in enumerate(items):
                ev=item.get('evidence',criterion.get('evidence',[]))
                proof.append({'full_name':app.get('full_name'),'application_id':app['application_id'],
                    'criterion':criterion.get('name',criterion.get('code')),'fact':item.get('label',''),
                    'criterion_status':{'yes':'Да','no':'Нет','unknown':'Недостаточно данных'}.get(item.get('status'),'Нужно уточнить' if criterion.get('needs_review') else 'Оценён'),
                    'group_points':criterion.get('points') if index==0 else None,'group_share':shares.get(criterion['code']) if index==0 else None,'points':item.get('contribution'),'reason':criterion.get('reason','') if index==0 else '',
                    'quote':item.get('quote') or '\n'.join(e.get('quote','') for e in ev),
                    'source_id':item.get('source_id') or ', '.join(str(e.get('source_id','')) for e in ev)})
    snapshot={**snapshot,'Оценка':proof}
    for name in (*SHEETS,'Оценка'):
        sheet=wb.create_sheet(name)
        data=snapshot.get(name,[] if name!='Сводка' else {})
        if isinstance(data,dict):
            data=[dict(metric=k,value=v) for k,v in data.items()]
        prepared=[]
        for record in data:
            record=dict(record)
            if name=='Анкеты' and isinstance(record.get('summary'),str):
                record['full_ai_report']=record['summary']
                record['summary']=record['summary'].split('\n\n')[0]
            for key,labels in LABELS.items():
                if isinstance(record.get(key),str):
                    record[key]=labels.get(record[key],record[key])
            for field in ('selected_directions','recommended_directions'):
                if isinstance(record.get(field),list):record[field]=', '.join(DIRECTION_NAMES.get(d,d) for d in record[field])
            if name=='Сводка' and isinstance(record.get('value'),dict):
                record['value']='\n'.join(f'{DIRECTION_NAMES.get(k,k)}: {v}' for k,v in record['value'].items())
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
        available=list(dict.fromkeys(k for row in data for k in row))
        columns=[k for k in ORDER.get(name,[]) if k in available]+[k for k in available if k not in ORDER.get(name,[])] or ['Нет данных']
        columns += ['continuation_part','continuation_total']
        sheet.append([HEADERS.get(k,k) for k in columns])
        for cell in sheet[1]:
            cell.font=Font(bold=True,color='FFFFFF')
            cell.fill=PatternFill('solid',fgColor='A71930')
            cell.alignment=Alignment(wrap_text=True,vertical='center')
        sheet.row_dimensions[1].height=34
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
                for cell,k in zip(sheet[sheet.max_row],columns):
                    raw=row.get(k)
                    if n==0 and k in {'ranking_score','score','ai_score','position','points','group_points','group_share','answers_revision'} and type(raw) in (int,float):
                        cell.value=raw
                        if k=='group_share':cell.number_format='0%'
                    else:cell.data_type='s'
                    cell.alignment=Alignment(wrap_text=True,vertical='top')
                    if sheet.max_row%2==0:cell.fill=PatternFill('solid',fgColor='FFF3F4')
                sheet.row_dimensions[sheet.max_row].height=120 if name=='Анкеты' else 75 if name!='Сводка' else 40
        for i,k in enumerate(columns,1):
            sheet.column_dimensions[get_column_letter(i)].width=(65 if k in {'candidate_profile','summary','ai_summary','answer_text','question_text','reason','quote','criteria_results','interview_questions'} else 30 if k not in {'score','ai_score','points','position','continuation_part','continuation_total'} else 14)
        for i,k in enumerate(columns,1):
            if k in {'criteria_results','full_ai_report','field_encodings'} or (k in {'continuation_part','continuation_total'} and all(len(_text(r.get('answer_text','')))<15000 for r in data)):
                sheet.column_dimensions[get_column_letter(i)].hidden=True
        if name=='Оценка' and 'group_share' in columns and sheet.max_row>1:
            letter=get_column_letter(columns.index('group_share')+1)
            sheet.conditional_formatting.add(f'{letter}2:{letter}{sheet.max_row}',DataBarRule(start_type='num',start_value=0,end_type='num',end_value=1,color='A71930',showValue=True))
        sheet.sheet_view.zoomScale=85
        sheet.freeze_panes='B2' if name=='Анкеты' else 'A2'
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
