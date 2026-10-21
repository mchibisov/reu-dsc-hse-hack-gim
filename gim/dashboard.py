"""Private, deterministic candidate profile from stored evaluation JSON, no LLM."""
import math
DIMENSIONS={'motivation':('Мотивация',1.5),'experience':('Опыт',1.05),'availability':('Занятость',.45)}

def dimensions(row):
 criteria=row.get('criteria_results') or []
 fixed=any(c.get('calculation',{}).get('kind')=='binary_50_35_15' for c in criteria)
 by={c.get('code'):c for c in criteria};result=[]
 for code,(name,maximum) in DIMENSIONS.items():
  c=by.get(code,{})
  points=c.get('points');known=bool(c) and not c.get('needs_review') and type(points) in (int,float) and math.isfinite(points)
  result.append({'code':code,'name':name,'points':points if known else None,'maximum':maximum if fixed else None,
                 'fraction':max(0,min(1,points/maximum)) if known and fixed else None})
 return result

def dashboard(row):
 if row.get('score') is None:return 'Профиль кандидата: AI-анализ ещё не готов; график не рассчитан.'
 lines=['ПРОФИЛЬ КАНДИДАТА'+(' · исходный AI' if row.get('evaluation_source')=='curator' else '')]
 for d in dimensions(row):
  if d['points'] is None:lines.append(d['name']+': недостаточно данных');continue
  value=f'{d["points"]:g}'
  if d['fraction'] is None:lines.append(d['name']+': '+value+' балла (прежняя рубрика)');continue
  n=int(d['fraction']*8+.5)
  lines.append(d['name']+' '+('🟥'*n+'⬜'*(8-n))+f' {value} / {d["maximum"]:g}')
 lines.append('Основания оценки, не вероятность приёма. Пробелы уточняет сотрудник.')
 return '\n'.join(lines)
