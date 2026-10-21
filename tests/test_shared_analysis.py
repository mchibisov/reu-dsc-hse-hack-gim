import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from gim.shared_service import SharedService


class AnalysisIntegration(unittest.IsolatedAsyncioTestCase):
    def service(self):
        settings = SimpleNamespace(llm_api_key='synthetic', llm_model='test-model',
                                   llm_base_url='https://example.invalid')
        repo = SimpleNamespace(pool=None)
        service = SharedService(repo, repo, repo, None, settings, None)
        self.aid = str(uuid4())
        self.snapshot = {'rubric_version':'approved-v1',
            'rubric':{'approved_by':'team', 'scoring_rule':'Сумма баллов, целое 0–3',
                      'scoring_method':'sum_round_half_up',
                      'criteria':[{'code':'experience', 'description':'Опыт', 'max_points':3}]},
            'answers':[{'id':self.aid, 'question_id':str(uuid4()), 'target_slot':'experience',
                        'answer_text':'Снимал концерты', 'revision':1}], 'files':[]}
        self.result = {'score':2, 'criteria':[{'code':'experience','points':2,
            'reason':'Подтверждено ответом','evidence':[{'source_type':'answer',
            'source_id':self.aid,'quote':'Снимал концерты'}]}],
            'summary':'Есть опыт съёмки', 'directions':['media'],
            'interview_questions':['Какой была ваша роль?']}
        service.llm = SimpleNamespace(complete=AsyncMock(return_value=self.result))
        return service

    async def test_shared_worker_actually_returns_persistable_analysis(self):
        service = self.service()
        result = await service.analyze({'snapshot':self.snapshot})
        self.assertIsNotNone(result)
        self.assertEqual(result['score'], 2)
        self.assertEqual(result['criteria'][0]['evidence'][0]['source_id'], self.aid)
        self.assertEqual(result['model'], 'test-model')

    async def test_bad_evidence_fractional_score_and_invented_criterion_rejected(self):
        service = self.service()
        for mode in ('quote','score','criterion','sum'):
            bad = deepcopy(self.result)
            if mode=='quote': bad['criteria'][0]['evidence'][0]['quote']='Не писал такого'
            if mode=='score': bad['score']=2.5
            if mode=='criterion': bad['criteria'][0]['code']='invented'
            if mode=='sum': bad['score']=3
            service.llm.complete.return_value=bad
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                await service.analyze({'snapshot':self.snapshot})

    async def test_provider_failure_is_retryable_never_a_fake_zero(self):
        service=self.service()
        service.llm.complete.side_effect=TimeoutError
        with self.assertRaises(TimeoutError):
            await service.analyze({'snapshot':self.snapshot})

    async def test_unapproved_formula_is_not_silently_replaced(self):
        service=self.service()
        self.snapshot['rubric'].pop('scoring_method')
        with self.assertRaises(ValueError):
            await service.analyze({'snapshot':self.snapshot})
        service.llm.complete.assert_not_awaited()

    async def test_external_payload_excludes_identity_and_historical_outcomes(self):
        service=self.service()
        for slot, text in [('full_name','Петров Пётр'), ('email','private@example.ru'),
                           ('hours','900'), ('historical_outcomes','accepted')]:
            self.snapshot['answers'].append({'id':str(uuid4()),'target_slot':slot,
                                            'answer_text':text,'question_id':str(uuid4()),'revision':1})
        await service.analyze({'snapshot':self.snapshot})
        payload=service.llm.complete.call_args.args[1]
        self.assertEqual(len(payload['answers']),1)
        self.assertNotIn('private@example.ru',str(payload))

    async def test_unknown_information_is_not_automatically_zero(self):
        service=self.service()
        self.result['criteria'][0].update(points=0,evidence=[],needs_review=True)
        self.result['score']=0
        with self.assertRaises(ValueError):
            await service.analyze({'snapshot':self.snapshot})

    async def test_personal_question_requires_exact_anchor_and_does_not_repeat(self):
        service=self.service()
        qid=self.snapshot['answers'][0]['question_id']
        ctx={'questions':[{'id':qid,'target_slot':'experience','text':'Опишите опыт'}],
             'answers':self.snapshot['answers'],'templates':[], 'direction_info':{}}
        generated={'action':'ask','question':'Какую роль вы выполняли на съёмке концертов?',
                   'source_id':self.aid,'quote':'Снимал концерты'}
        service.llm.complete.return_value=generated
        result=await service.personal_question(ctx,['media'],2)
        self.assertEqual(result['question'],generated['question'])
        service.llm.complete.return_value={**generated,'quote':'Делал сайты'}
        with self.assertRaises(ValueError):
            await service.personal_question(ctx,['media'],2)
        ctx['questions'].append({'id':str(uuid4()),'target_slot':'clarification_1',
                                 'text':generated['question']})
        service.llm.complete.return_value=generated
        with self.assertRaises(ValueError):
            await service.personal_question(ctx,['media'],1)
