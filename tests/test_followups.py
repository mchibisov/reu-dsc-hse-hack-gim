import unittest

from gim.followups import plan_followups, validate_plan


class FollowupTests(unittest.TestCase):
    def test_skill_already_described_gets_deeper_question(self):
        plan = plan_followups(['media'], {'experience': 'Я фотограф, снимаю мероприятия и делаю репортажи'})
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]['direction'], 'media')
        self.assertNotIn('Что вы умеете', plan[0]['text'])
        self.assertIn('фото', plan[0]['text'].lower())

    def test_unselected_directions_never_get_questions(self):
        plan = plan_followups(['funds'], {'experience': 'Архив и каталоги'})
        self.assertEqual([q['direction'] for q in plan], ['funds'])
        self.assertNotIn('дет', plan[0]['text'])

    def test_provider_cannot_repeat_or_change_direction(self):
        for plan in ([{'direction': 'media', 'text': 'Где работали?'}],
                     [{'direction': 'funds', 'text': 'Один вопрос?'}, {'direction': 'funds', 'text': 'Один вопрос?'}]):
            with self.assertRaises(ValueError):
                validate_plan(plan, ['funds'])
