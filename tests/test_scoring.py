import unittest
from gim.scoring import validate_evaluation


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.answers = [{'id': 'a1', 'answer_text': 'Работал в архиве два года'}]
        self.result = {'score': 2, 'rubric_version': 'v1', 'rubric_snapshot': {'criteria': ['опыт']},
                       'criteria_results': [{'criterion': 'опыт', 'answer_id': 'a1', 'quote': 'в архиве', 'reason': 'Есть релевантный опыт'}],
                       'summary': 'Опыт архивной работы', 'interview_questions': ['Какие задачи выполняли?'],
                       'recommended_directions': ['funds']}

    def test_valid_citation(self):
        self.assertEqual(validate_evaluation(self.result, self.answers)['score'], 2)

    def test_fabricated_quote_is_rejected(self):
        self.result['criteria_results'][0]['quote'] = 'Стажировался в ГИМ'
        with self.assertRaises(ValueError):
            validate_evaluation(self.result, self.answers)

    def test_invalid_score_and_direction_are_rejected(self):
        for key, value in [('score', 4), ('score', float('nan')), ('recommended_directions', ['unknown'])]:
            result = {**self.result, key: value}
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_evaluation(result, self.answers)


if __name__ == '__main__':
    unittest.main()
