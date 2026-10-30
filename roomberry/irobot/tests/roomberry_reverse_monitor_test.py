# @(#)roomberry_reverse_monitor_test.py 2.3.10 2026/10/28 17:00:00
import logging
from types import SimpleNamespace
import unittest
from roomberry_reverse_monitor import ReverseCurrentMonitor


class ReverseMonitorTest(unittest.TestCase):
    def setUp(self):
        self.monitor = ReverseCurrentMonitor(logging.getLogger('ReverseReportTest'))
        self.sensors = SimpleNamespace(left_motor_current=140, right_motor_current=150,
            wheel_overcurrents=SimpleNamespace(left_wheel_overcurrent=False,
                                               right_wheel_overcurrent=False))

    def sample(self, now, current=140, progress=4, wheels=(-40,-40)):
        self.sensors.left_motor_current=current
        return self.monitor.update(self.sensors,wheels,progress,now)

    def test_normal_reverse_is_not_candidate(self):
        for i in range(20):state=self.sample(i*.125)
        self.assertEqual(state['mode'],'report_only')
        self.assertFalse(state['candidate'])
        self.assertEqual(state['event_count'],0)

    def test_sustained_current_needs_three_samples_and_duration(self):
        self.sample(0)
        self.assertFalse(self.sample(.2,500)['candidate'])
        self.assertFalse(self.sample(.325,500)['candidate'])
        self.assertTrue(self.sample(.45,500)['candidate'])
        self.assertIn('left_sustained_current',self.monitor.status()['reasons'])
        for i in range(4,10):self.sample(i*.125,500)
        self.assertEqual(self.monitor.event_count,1)

    def test_fast_limit_still_reports_during_acceleration(self):
        state=self.sample(0,700,wheels=(-5,-5))
        self.assertIn('left_high_current',state['reasons'])
        self.assertEqual(state['last_event']['applied_wheels_mm_s'],[-5,-5])

    def test_gap_cannot_satisfy_persistence(self):
        self.sample(0)
        self.sample(.2,500)
        self.assertFalse(self.sample(1.0,500)['candidate'])

    def test_forward_and_turning_are_not_reverse_translation(self):
        self.assertFalse(self.sample(0,1000,wheels=(40,40))['candidate'])
        self.assertFalse(self.sample(.2,1000,wheels=(-40,40))['candidate'])

    def test_no_progress_is_independent_of_current(self):
        for i in range(10):state=self.sample(i*.125,progress=0)
        self.assertIn('no_encoder_progress',state['reasons'])

    def test_stop_resets_episode_but_preserves_report_history(self):
        self.sample(0,700)
        state=self.sample(.1,wheels=(0,0))
        self.assertFalse(state['candidate'])
        self.assertFalse(state['reversing'])
        self.assertEqual(state['event_count'],1)
        self.assertIsNotNone(state['last_event'])

    def test_active_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            ReverseCurrentMonitor(logging.getLogger('BadMode'),{'mode':'stop'})

    def test_baseline_cannot_learn_high_load(self):
        for i in range(100):self.sample(i*.125,500)
        self.assertLessEqual(self.monitor.baseline[0],.15)
