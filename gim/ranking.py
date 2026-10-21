"""User-approved 50/35/15 ranking. LLM supplies evidence, never arithmetic."""
from decimal import Decimal, ROUND_HALF_UP
from gim.evidence import validate_report, REPORT_PROMPT
FEATURES={
 'm1':('motivation','Конкретные ожидания и цели'),
 'm2':('motivation','Обоснован выбор именно ГИМ'),
 'm3':('motivation','Интересы соответствуют тематике музея'),
 'm4':('motivation','Осведомлённость о волонтёрской программе'),
 'e1':('experience','Профильный опыт'),
 'e2':('experience','Волонтёрство или практика в музеях'),
 'e3':('experience','Полезные смежные навыки или рабочий опыт'),
 'e4':('experience','Академические достижения'),
 'e5':('experience','Конкретно объяснена помощь музею'),
 'a1':('availability','Второй курс и выше либо оконченное образование'),
 'a2':('availability','Нагрузка позволяет регулярно волонтёрить'),
 'p_exclusive':('motivation','Прямо указан интерес исключительно к фондам'),
 'p_refuses':('motivation','Прямо отказался рассматривать альтернативы'),
}
GROUPS={'motivation':('Мотивация и осознанность',1.5),'experience':('Опыт и навыки',1.05),'availability':('Обучение и нагрузка',.45)}
RULE='S = 3 × (0.50 × max(0, Σm − p)/4 + 0.35 × Σe/5 + 0.15 × Σa/2), p=1 только при исключительном интересе к фондам И отказе от альтернатив. Целый балл округляется 0.5 вверх; рейтинг сортируется по S.'
RUBRIC={'version':'gim-ranking-50-35-15-v1','rubric':{'approved_by':'mchibisov: formula supplied 2026-10-22','scoring_method':'binary_50_35_15','scoring_rule':RULE,'criteria':[{'code':c,'name':n,'max_points':w} for c,(n,w) in GROUPS.items()]}}
PROMPT=REPORT_PROMPT+'''
Дополнительно верни facts: все переданные коды ровно по одному, каждый {code,status:"yes|no|unknown",source_id,quote}.
Да — только прямое подтверждение, нет — прямое отрицание, unknown — недостаточно данных. Для yes/no нужна точная непрерывная цитата из answers; для unknown quote="", source_id=null.
Не делай вывод о нагрузке по курсу или работе. a1: только явно названный курс>=2 или оконченное образование, не предполагай академических достижений по престижу вуза.
p_exclusive: выбор фондов сам по себе НЕ исключительность; p_refuses: только явный отказ от альтернатив, молчание значит unknown. Один отказ от альтернатив без исключительного интереса к фондам не штрафуется.
Не оценивай по полу, возрасту, контактам, будущим результатам участия. Не считай неизвестность отсутствием навыка. Не выдавай итоговую оценку: её вычисляет сервер.'''

def validate(facts,answers):
 if not isinstance(facts,list) or len(facts)!=len(FEATURES):raise ValueError('All ranking facts required')
 sources={a['id']:a['text'] for a in answers};by={}
 for f in facts:
  if not isinstance(f,dict) or f.get('code') not in FEATURES or f['code'] in by or f.get('status') not in {'yes','no','unknown'}:raise ValueError('Invalid ranking fact')
  if f['status']!='unknown' and (not isinstance(f.get('quote'),str) or not f['quote'].strip() or f.get('source_id') not in sources or f['quote'] not in sources[f['source_id']]):raise ValueError('Unverifiable ranking evidence')
  if f['status']=='unknown':f={**f,'quote':'','source_id':None}
  by[f['code']]=f
 return [by[c] for c in FEATURES]

def calculate(facts):
 by={f['code']:f['status'] for f in facts}
 if set(by)!=set(FEATURES) or len(facts)!=len(FEATURES) or any(v not in {'yes','no','unknown'} for v in by.values()):raise ValueError('Invalid ranking facts')
 if all(v=='unknown' for v in by.values()):raise ValueError('No observed facts; manual review required')
 n=lambda prefix:sum(by[c]=='yes' for c in FEATURES if c.startswith(prefix) and c[1:].isdigit())
 m,e,a=n('m'),n('e'),n('a');p=int(by['p_exclusive']==by['p_refuses']=='yes')
 points={'motivation':Decimal('1.5')*max(0,m-p)/4,'experience':Decimal('1.05')*e/5,'availability':Decimal('.45')*a/2}
 raw=sum(points.values())
 return {'kind':'binary_50_35_15','raw':float(raw),'score':int(raw.quantize(Decimal(1),rounding=ROUND_HALF_UP)), 'm':m,'e':e,'a':a,'penalty':p,'group_points':{c:float(v) for c,v in points.items()},'rule':RULE,'unknown':sum(v=='unknown' for v in by.values())}

async def analyze(llm,snapshot):
 from gim.shared_analysis import safe_answers,DIRECTION_NAMES
 answers=safe_answers(snapshot['answers']);payload={'answers':answers,'features':{c:v[1] for c,v in FEATURES.items()},'direction_info':snapshot.get('direction_info',{})}
 for attempt in range(2):
  result=await llm.complete(PROMPT,payload)
  try:
   facts=validate(result.get('facts'),answers);report=validate_report(result,answers)
   originals={str(a['id']):a['answer_text'] for a in snapshot['answers']}
   for item in [f for f in facts if f['status']!='unknown']+report['strengths']:
    if item['quote'] not in originals.get(item['source_id'],''):raise ValueError('Quote must also exist in original answer, not a redaction placeholder')
   calc=calculate(facts);break
  except ValueError as exc:
   if attempt:raise
   payload={**payload,'validation_error':str(exc),'repair':'Use exact current quotes; unknown when evidence is absent; all features required.'}
 criteria=[]
 for group,(name,maximum) in GROUPS.items():
  items=[{**f,'label':FEATURES[f['code']][1]} for f in facts if FEATURES[f['code']][0]==group]
  ev=[{'source_type':'answer','source_id':f['source_id'],'quote':f['quote']} for f in items if f['status']!='unknown']
  criteria.append({'code':group,'name':name,'points':calc['group_points'][group],'reason':'По фиксированной формуле 50/35/15; неподтверждённое не даёт баллов и требует уточнения.','needs_review':not ev,'evidence':ev,'facts':items})
 criteria[0]['calculation']=calc
 summary=report['summary']+'\n\nСильные стороны:\n'+('\n'.join('• '+s['text']+' — «'+s['quote']+'»' for s in report['strengths']) or 'Уточнить на собеседовании.')
 summary+='\n\nНедостающие сведения:\n'+('\n'.join('• '+FEATURES[f['code']][1] for f in facts if f['status']=='unknown') or 'Все признаки рассмотрены.')
 negative=[f for f in facts if f['status']=='no']
 if negative:summary+='\n\nПрямо указанные ограничения:\n'+'\n'.join(FEATURES[f['code']][1]+': «'+f['quote']+'»' for f in negative)
 summary+='\n\nПо направлениям:\n'+'\n'.join(DIRECTION_NAMES[d]+': '+v for d,v in report['direction_assessments'].items())
 return {'score':calc['score'],'criteria':criteria,'summary':summary,'directions':report['directions'],'interview_questions':report['interview_questions']}

def ranking_value(row):
 """Curator score supersedes AI rank; old rubrics retain their integer ordering."""
 if row.get('score') is None:return None
 if row.get('evaluation_source')=='curator':return float(row['score'])
 for c in row.get('criteria_results') or []:
  calc=c.get('calculation',{})
  if calc.get('kind')=='binary_50_35_15':return calc['raw']
 return float(row['score'])

def ranked_bundle(bundle):
 rows=bundle.get('Анкеты',[])
 for row in rows:row['ranking_score']=ranking_value(row)
 # Stable ties preserve database submission ordering.
 bundle['Анкеты']=sorted(rows,key=lambda r:(r['ranking_score'] is None,-(r['ranking_score'] or 0)))
 return bundle
