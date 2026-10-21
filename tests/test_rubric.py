import unittest
from gim.rubric import validate_rubric, validate_rubric_evaluation


class RubricTests(unittest.TestCase):
    def setUp(self):
        self.rubric = {'version': 'team-v1', 'criteria': [{'code': 'experience', 'description': 'Критерий команды', 'max_score': 3}]}
        self.answers = [{'id': 'a1', 'answer_text': 'Работал в архиве'}]
        self.result = {'score': 2, 'criteria_results': [{'criterion': 'experience', 'points': 2,
            'reason': 'Релевантный опыт', 'answer_id': 'a1', 'quote': 'в архиве'}],
            'summary': 'Опыт архива', 'interview_questions': [], 'recommended_directions': ['funds']}

    def test_provider_cannot_replace_rubric(self):
        result = validate_rubric_evaluation({**self.result, 'rubric_version': 'invented'}, self.rubric, self.answers)
        self.assertEqual(result['rubric_version'], 'team-v1')
        self.assertEqual(result['rubric_snapshot'], self.rubric)

    def test_extra_criterion_and_wrong_total_are_rejected(self):
        for result in ({**self.result, 'score': 3},
                       {**self.result, 'criteria_results': [{**self.result['criteria_results'][0], 'criterion': 'invented'}]}):
            with self.assertRaises(ValueError):
                validate_rubric_evaluation(result, self.rubric, self.answers)

    def test_positive_points_require_source_quote(self):
        self.result['criteria_results'][0]['quote'] = ''
        with self.assertRaises(ValueError):
            validate_rubric_evaluation(self.result, self.rubric, self.answers)

    def test_unapproved_or_invalid_rubric_is_rejected(self):
        for rubric in ({}, {'version': 'v1', 'criteria': []},
                       {'version': 'v1', 'criteria': [{'code': 'x', 'description': 'x', 'max_score': 4}]}):
            with self.assertRaises(ValueError):
                validate_rubric(rubric)
