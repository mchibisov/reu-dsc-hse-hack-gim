import unittest
from collections import Counter

from gim.calibration import split_history, reference_examples, museum_rubric
from gim.shared_analysis import approved_rubric


class CalibrationTests(unittest.TestCase):
    def records(self):
        return [dict(id=f'synthetic-{i}',cohort=str(2024+i%2),expert_score=i%4,
                     features={'experience':'Вёл мастер-классы; test@example.ru',
                               'expectations':'Хочу помогать музею', 'birth_date_raw':'2000-01-01',
                               'hours':'9999','accepted':'yes','full_name':'Private Name'})
                for i in range(80)]

    def test_examples_are_balanced_private_and_outcome_free(self):
        examples=reference_examples(self.records())
        self.assertEqual(Counter(x['expert_score'] for x in examples),{0:2,1:2,2:2,3:2})
        for example in examples:
            self.assertLessEqual(sum(len(a['text']) for a in example['answers']),2400)
            self.assertNotIn('9999',str(example))
            self.assertNotIn('2000-01-01',str(example))
            self.assertNotIn('Private Name',str(example))
            self.assertNotIn('test@example.ru',str(example))

    def test_holdout_stable_disjoint_and_never_reference_example(self):
        train,test=split_history(self.records())
        train2,test2=split_history(list(reversed(self.records())))
        self.assertEqual({r['id'] for r in test},{r['id'] for r in test2})
        self.assertTrue(train and test)
        self.assertFalse({r['id'] for r in train}&{r['id'] for r in test})
        examples=reference_examples(train)
        self.assertFalse({e['id'] for e in examples}&{r['id'] for r in test})

    def test_five_fixed_groups_total_three_and_provenance_is_explicit(self):
        rubric=museum_rubric(self.records())
        _,maxima=approved_rubric({'rubric':rubric})
        self.assertEqual(len(maxima),5)
        self.assertEqual(sum(maxima.values()),3)
        self.assertIn('MVP',rubric['approved_by'])
        self.assertIn('history_examples',rubric)
