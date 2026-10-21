from pathlib import Path
from gim_db.materials import FEATURE_COLUMNS,prepare_history,questionnaire_from_docx


def test_future_outcomes_are_never_features(tmp_path):
    from openpyxl import Workbook
    p=tmp_path/'synthetic.xlsx';w=Workbook();s=w.active
    s.append(['Сколько баллов дали','Дата рождения','Опыт работы','Активность в часах в год','Длительность пребывания в программе','Взяли ли в команду'])
    s.append([0,'01.2000','Снимал',999,42,'Да']);w.save(p)
    records,counts=prepare_history([p])
    assert records[0]['features']=={'birth_date_raw':'01.2000','experience':'Снимал'}
    assert records[0]['expert_score']==0 and sum(counts.values())==1
