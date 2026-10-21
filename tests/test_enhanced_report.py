import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from gim.evidence import FACTS
from gim.shared_service import SharedService
class EnhancedReport(unittest.IsolatedAsyncioTestCase):
 async def test_enhancement_preserves_pinned_score_and_adds_evidence(self):
  repo=SimpleNamespace(pool=None);settings=SimpleNamespace(enhanced_reports=True,llm_api_key='test',llm_model='test',llm_base_url='https://example.invalid')
  service=SharedService(repo,repo,repo,None,settings,None)
  snapshot={'rubric_version':'v','rubric':{'approved_by':'team','scoring_rule':'sum','scoring_method':'sum_round_half_up','criteria':[{'code':'experience','max_points':3}]},'answers':[{'id':'a','target_slot':'experience','answer_text':'Работал в музее'}]}
  grade={'score':2,'criteria':[{'code':'experience','points':2,'reason':'Опыт','evidence':[{'source_type':'answer','source_id':'a','quote':'Работал в музее'}]}],'summary':'Опыт','directions':['media'],'interview_questions':['Какой опыт?']}
  facts=[{'code':c,'status':'unknown'} for c in FACTS];facts[3].update(status='yes',source_id='a',quote='Работал в музее')
  report={'summary':'Есть музейный опыт','strengths':[{'text':'Опыт','source_id':'a','quote':'Работал в музее'}],'directions':['media'],'direction_assessments':{c:'Уточнить задачи' for c in ('organizational','project','collections','inclusive','media')},'interview_questions':['Какие задачи выполняли лично?']}
  service.llm.complete=AsyncMock(side_effect=[grade,{'facts':facts},report])
  result=await service.analyze({'snapshot':snapshot})
  self.assertEqual(result['score'],2)
  self.assertEqual(result['criteria'][0]['points'],2)
  self.assertEqual(len(result['criteria'][0]['facts']),3)
  self.assertIn('Недостающие сведения',result['summary'])
