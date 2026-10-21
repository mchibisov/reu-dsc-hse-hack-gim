import unittest

from gim.followups import validate_decision


class FollowupTests(unittest.TestCase):
    def test_model_can_finish_without_unnecessary_question(self):
        result = validate_decision({'action': 'finish'}, ['funds'], [])
        self.assertEqual(result['action'], 'finish')

    def test_model_question_is_preserved_without_keyword_routing(self):
        question = 'Как вы сверяли инвентарные номера предметов?'
        result = validate_decision({'action': 'ask', 'direction': 'funds', 'question': question}, ['funds'], [])
        self.assertEqual(result['question'], question)

    def test_provider_cannot_repeat_or_change_direction(self):
        for decision in ({'action': 'ask', 'direction': 'media', 'question': 'Где работали?'},
                         {'action': 'ask', 'direction': 'funds', 'question': '  Один вопрос?  '}):
            with self.assertRaises(ValueError):
                validate_decision(decision, ['funds'], ['Один вопрос?'])

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_decision({'action': 'accept_candidate'}, ['funds'], [])
