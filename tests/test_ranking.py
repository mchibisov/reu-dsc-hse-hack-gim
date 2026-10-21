import unittest
from gim.ranking import FEATURES, calculate, validate
class RankingTests(unittest.TestCase):
 def facts(self,status='yes'):
  return [{'code':c,'status':status,'source_id':'a','quote':'Подтверждаю'} for c in FEATURES]
 def test_full_score_and_explicit_penalty(self):
  f=self.facts();r=calculate(f)
  self.assertEqual(r['raw'],2.625)
  self.assertEqual(r['penalty'],1)
  f[-1]['status']='unknown'
  self.assertEqual(calculate(f)['raw'],3)
 def test_no_double_negative_or_invented_zero(self):
  f=self.facts('unknown')
  with self.assertRaises(ValueError):calculate(f)
  f[0]['status']='no'
  self.assertEqual(calculate(f)['raw'],0)
 def test_exact_example_and_rounding(self):
  f=self.facts('unknown')
  for v in f:
   if v['code'] in {'m1','m2','e1','a2'}:v['status']='yes'
  r=calculate(f)
  self.assertEqual(r['raw'],1.185)
  self.assertEqual(r['score'],1)
 def test_reject_fabricated_evidence(self):
  with self.assertRaises(ValueError):validate(self.facts(),[{'id':'a','text':'Другой текст'}])
 def test_fractional_ranking_precedes_integer_and_curator_wins(self):
  from gim.ranking import ranked_bundle
  def row(name,raw,source='algorithm',score=2):return {'application_id':name,'score':score,'evaluation_source':source,'criteria_results':[{'calculation':{'kind':'binary_50_35_15','raw':raw}}]}
  b=ranked_bundle({'Анкеты':[row('low',1.6),row('high',2.4),row('manual',.2,'curator',3),{'application_id':'pending','score':None}]})
  self.assertEqual([r['application_id'] for r in b['Анкеты']],['manual','high','low','pending'])

class RankingEvidenceTests(unittest.IsolatedAsyncioTestCase):
 async def test_redaction_placeholder_is_not_a_quote_of_the_original(self):
  from unittest.mock import AsyncMock
  from types import SimpleNamespace
  from gim.ranking import analyze,RUBRIC
  from gim.shared_domain import DIRECTIONS
  facts=[{'code':c,'status':'unknown'} for c in FEATURES]
  facts[0]={'code':'m1','status':'yes','source_id':'a','quote':'[email]'}
  r={'facts':facts,'summary':'Требует уточнения','strengths':[],'directions':[], 'direction_assessments':{d:'Уточнить задачи' for d in DIRECTIONS},'interview_questions':['Какие задачи вам интересны?']}
  llm=SimpleNamespace(complete=AsyncMock(return_value=r))
  with self.assertRaisesRegex(ValueError,'original answer'):
   await analyze(llm,{'rubric':RUBRIC['rubric'],'answers':[{'id':'a','target_slot':'motivation','answer_text':'Напишу mail@example.test'}]})
