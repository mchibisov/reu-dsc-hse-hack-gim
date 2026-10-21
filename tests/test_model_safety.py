import unittest
from gim.ranking import FEATURES,validate
from gim.evidence import validate_report
from gim.shared_domain import DIRECTIONS
class ModelSafetyTests(unittest.TestCase):
 def facts(self):return [{'code':c,'status':'unknown'} for c in FEATURES]
 def test_non_string_codes_are_rejected_as_validation_errors(self):
  f=self.facts();f[0]['code']=[]
  with self.assertRaises(ValueError):validate(f,[])
 def test_non_string_source_ids_are_rejected(self):
  f=self.facts();f[0].update(status='yes',quote='Опыт',source_id={})
  with self.assertRaises(ValueError):validate(f,[{'id':'a','text':'Опыт'}])
 def test_nested_directions_cannot_crash_report_validation(self):
  r={'summary':'Резюме','strengths':[],'directions':[{}],'direction_assessments':{d:'Уточнить' for d in DIRECTIONS},'interview_questions':['Какой опыт?']}
  with self.assertRaises(ValueError):validate_report(r,[])
