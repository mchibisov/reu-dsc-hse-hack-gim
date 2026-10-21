import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from gim.llm import LLMClient, ModelUnavailable


class LLMTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_history_is_sent_as_data_and_one_question_returned(self):
        captured = []
        async def endpoint(request):
            captured.append(json.loads(request.content))
            result = {'action': 'ask', 'direction': 'funds', 'question': 'Как вы сверяли инвентарные номера?'}
            return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(result)}}]})
        settings = SimpleNamespace(llm_api_key='test-secret', llm_model='test-model', llm_base_url='https://model.test/v1',llm_reasoning_effort='low')
        factory = httpx.AsyncClient
        history = [{'id': 'a1', 'question_text': 'Ваш опыт?', 'answer_text': 'Каталогизация'},
                   {'id': 'a2', 'question_text': 'Какие предметы?', 'answer_text': 'Монеты'}]
        with patch('gim.llm.httpx.AsyncClient', lambda **kwargs: factory(transport=httpx.MockTransport(endpoint), **kwargs)):
            result = await LLMClient(settings).next_question(history, ['funds'], 2)
        self.assertEqual(result['action'], 'ask')
        self.assertEqual(captured[0]['response_format'], {'type': 'json_object'})
        self.assertEqual(captured[0]['reasoning'],{'effort':'low'})
        self.assertEqual(captured[0]['max_tokens'],6000)
        payload = json.loads(captured[0]['messages'][1]['content'])
        self.assertEqual(payload['answers'], history)
        self.assertEqual(payload['remaining_questions'], 2)
        self.assertNotIn('Монеты', captured[0]['messages'][0]['content'])

    async def test_no_key_never_substitutes_pattern_question(self):
        with self.assertRaises(ModelUnavailable):
            await LLMClient(SimpleNamespace()).next_question([], ['funds'], 3)
