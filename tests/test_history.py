import unittest
from gim.history import normalize_record


class HistoryTests(unittest.TestCase):
    def test_future_outcomes_are_never_candidate_answers(self):
        headers = ['Сколько баллов дали после обработки анкеты: 0–3', 'Взяли ли в итоге кандидата в команду?',
                   'Активность в часах в год:', 'Дата рождения', 'Опыт работы, стажировки, участие в проектах и т.д. (если имеется)',
                   'Интересующие виды волонтёрства']
        record = normalize_record(headers, [2, 'ДА', 60, 2007, 'Работал в архиве', 'Фондовая работа'])
        self.assertEqual(record['score'], 2)
        self.assertEqual(record['directions'], ['funds'])
        self.assertEqual(record['outcomes']['hours'], 60)
        self.assertEqual({a['code'] for a in record['answers']}, {'birth_date', 'experience', 'directions'})
        self.assertNotIn('hours', {a['code'] for a in record['answers']})

    def test_blank_formatted_rows_are_not_imported(self):
        self.assertIsNone(normalize_record(['Сколько баллов дали после обработки анкеты:', 'ВУЗ'], [None, None]))

    def test_zero_score_is_not_missing(self):
        record = normalize_record(['Сколько баллов дали после обработки анкеты:', 'ВУЗ'], [0, 'ВШЭ'])
        self.assertEqual(record['score'], 0)
