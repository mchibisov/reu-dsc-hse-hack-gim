import unittest
from scripts.evaluate_history import evaluation_metrics

class HistoryMetrics(unittest.TestCase):
    def test_abstentions_do_not_inflate_full_sample_accuracy_and_zero_is_valid(self):
        rows=[{'expert_score':0,'score':0},{'expert_score':2,'score':None,'error':'ModelUnavailable'},
              {'expert_score':3,'score':2}]
        m=evaluation_metrics(rows)
        self.assertEqual(m['predicted'],2)
        self.assertEqual(m['exact_match'],0.5)
        self.assertAlmostEqual(m['exact_match_all'],1/3)
        self.assertAlmostEqual(m['baseline_score_2']['exact_match'],1/3)
        self.assertEqual(m['abstentions'],{'ModelUnavailable':1})

    def test_empty_sample_has_no_invented_accuracy(self):
        m=evaluation_metrics([])
        self.assertIsNone(m['exact_match_all'])
        self.assertIsNone(m['baseline_score_2']['mae'])
