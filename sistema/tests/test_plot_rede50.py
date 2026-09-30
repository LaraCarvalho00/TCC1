import unittest
import numpy as np
from sistema.scripts.plot_rede50 import calendar, event_series


class EventSeriesTests(unittest.TestCase):
    def setUp(self):
        self.run = dict(scores=np.array([[.5,.5],[.4,.6],[.3,.7]]),
                        mal=np.array([False,True]), before={(1,0):.2,(1,1):.8})

    def test_event_keeps_pre_and_post_at_same_round(self):
        x, values = event_series(self.run, 'score', 'honest')
        np.testing.assert_array_equal(x,[0,1,1,2])
        np.testing.assert_allclose(values,[.5,.2,.4,.3])

    def test_weight_share_uses_pre_event_denominator(self):
        self.run['before'][(1,1)] = .6
        _, values = event_series(self.run, 'share')
        np.testing.assert_allclose(values,[.5,.75,.6,.7])

    def test_control_has_no_event_and_no_duplicated_round(self):
        self.run['before'] = {}
        x,_ = event_series(self.run, 'share')
        np.testing.assert_array_equal(x,[0,1,2])
        self.assertEqual(calendar([self.run]),[])

    def test_mismatched_calendars_are_rejected(self):
        with self.assertRaises(ValueError):
            calendar([self.run,{**self.run,'before':{}}])
