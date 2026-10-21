import unittest
from gim import evidence

class EvidenceTests(unittest.TestCase):
    def test_fact_requires_exact_candidate_quote(self):
        answers=[{'id':'a','text':'Работала в архиве.'}]
        with self.assertRaises(ValueError):
            evidence.validate_facts([{'code':'profile_experience','status':'yes','source_id':'a','quote':'Работала в музее.'}],answers)

    def test_unknown_is_neutral_and_cannot_fake_zero_on_provider_failure(self):
        self.assertEqual(evidence.fact_vector([{'code':c,'status':'unknown'} for c in evidence.FACTS]),[0.0]*len(evidence.FACTS))
        with self.assertRaises(ValueError):
            evidence.calculate([],{'coefficients':[0]*len(evidence.FACTS),'intercept':2})

    def test_transparent_calculation_and_unknown_evidence(self):
        facts=[{'code':c,'status':'unknown','quote':'','source_id':None} for c in evidence.FACTS]
        facts[0]={'code':next(iter(evidence.FACTS)),'status':'yes','quote':'Хочу изучать историю','source_id':'a'}
        model={'coefficients':[0.8]+[0]*(len(evidence.FACTS)-1),'intercept':1.2}
        result=evidence.calculate(facts,model)
        self.assertEqual(result['score'],2)
        self.assertAlmostEqual(result['raw'],2)
        self.assertEqual(result['contributions'][0]['value'],0.8)

    def test_report_cannot_invent_strength_evidence(self):
        report={'summary':'Опыт','strengths':[{'text':'Опыт','source_id':'a','quote':'Иное'}],
                'gaps':['Уточнить график'],'directions':['media'],'direction_assessments':{d:'Недостаточно данных' for d in ('organizational','project','collections','inclusive','media')},'interview_questions':['Что делали?']}
        with self.assertRaises(ValueError):evidence.validate_report(report,[{'id':'a','text':'Работал'}])

    def test_fixed_fact_classifier_calculates_class_from_pinned_coefficients(self):
        facts=[{'code':c,'status':'unknown'} for c in evidence.FACTS];facts[0]['status']='yes'
        model={'kind':'logistic','classes':[0,1,2,3],'intercept':[0,0,0,0],
               'coefficients':[[0]*15,[0]*15,[2]+[0]*14,[1]+[0]*14]}
        result=evidence.calculate(facts,model)
        self.assertEqual(result['score'],2)
        self.assertEqual(result['class_values']['2'],2)
