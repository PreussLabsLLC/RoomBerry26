# @(#)roomberry_turn_guard_test.py 3.1.grout.13 2026/11/04
import math
import unittest
from unittest.mock import Mock
from roomberry_turn_guard import SettledTurn


class SettledTurnTest(unittest.TestCase):
    def setUp(self):
        self.now=100.
        self.mission=Mock()
        self.guard=SettledTurn(self.mission,lambda:self.now)

    def sample(self, t, angle=0., distance=0., stamp=None):
        self.now=t
        return dict(angle=angle,distance=distance,sensor_monotonic_s=t if stamp is None else stamp)

    def arm(self, sign):
        self.assertFalse(self.guard.prepare(self.sample(100.),sign))
        self.assertFalse(self.guard.prepare(self.sample(100.2),sign))
        self.assertTrue(self.guard.prepare(self.sample(100.4),sign))
        self.guard.dispatched(sign)

    def test_exact_reversal_failure_timing_waits_for_settling(self):
        self.arm(1)
        self.guard.prepare(self.sample(100.6,355.17),1)
        # Reversal chosen from 360.64 degrees, while old left turn continues.
        self.assertFalse(self.guard.prepare(self.sample(101.732,360.635,stamp=101.723),-1))
        self.assertFalse(self.guard.prepare(self.sample(101.933,363.81,stamp=101.864),-1))
        self.assertFalse(self.guard.prepare(self.sample(102.133,365.67,stamp=101.991),-1))
        self.assertIsNone(self.guard.error)
        self.assertTrue(self.guard.prepare(self.sample(102.333,365.67,stamp=102.24),-1))
        self.guard.dispatched(-1)
        self.assertTrue(self.guard.prepare(self.sample(102.5,365.6),-1))
        self.assertEqual(self.guard.anchor,365.6)
        self.assertTrue(self.guard.prepare(self.sample(102.7,361.6),-1))
        self.assertIsNone(self.guard.error)

    def test_pre_command_sample_cannot_arm_heading_reference(self):
        self.arm(-1)
        self.assertTrue(self.guard.prepare(self.sample(100.5,50,stamp=100.3),-1))
        self.assertIsNone(self.guard.anchor)
        self.guard.prepare(self.sample(100.6,10),-1)
        self.assertEqual(self.guard.anchor,10)

    def test_repeated_sensor_snapshot_cannot_establish_settling(self):
        self.guard.prepare(self.sample(100),1)
        for t in (100.2,100.4,100.6):
            self.assertFalse(self.guard.prepare(self.sample(t,stamp=99.99),1))
        self.assertEqual(self.guard.phase,'settling')

    def test_translating_wheels_must_settle_before_pivot(self):
        self.guard.prepare(self.sample(100),1)
        self.guard.prepare(self.sample(100.2,distance=10),1)
        self.assertFalse(self.guard.prepare(self.sample(100.4,distance=20),1))
        self.assertFalse(self.guard.prepare(self.sample(100.6,distance=22),1))
        self.assertTrue(self.guard.prepare(self.sample(100.8,distance=22),1))

    def test_settling_is_bounded(self):
        self.guard.prepare(self.sample(100),1)
        self.assertFalse(self.guard.prepare(self.sample(101.6,30),1))
        self.assertIn('did not settle',self.guard.error)

    def test_sustained_wrong_direction_still_stops(self):
        self.arm(-1)
        self.guard.prepare(self.sample(100.6),-1)
        self.assertTrue(self.guard.prepare(self.sample(100.8,4),-1))
        self.assertFalse(self.guard.prepare(self.sample(101.,5),-1))
        self.assertIn('opposite',self.guard.error)

    def test_large_wrong_direction_stops_without_second_vote(self):
        self.arm(-1)
        self.guard.prepare(self.sample(100.6),-1)
        self.assertFalse(self.guard.prepare(self.sample(100.8,9),-1))
        self.assertIn('opposite',self.guard.error)

    def test_early_braking_accounts_for_observed_turn_rate(self):
        self.arm(1)
        self.guard.prepare(self.sample(100.6,10),1,math.radians(7))
        self.assertFalse(self.guard.prepare(self.sample(100.8,14),1,math.radians(3)))
        self.assertEqual(self.guard.phase,'settling')
        self.assertIsNone(self.guard.error)

    def test_leaving_pivot_settles_before_translation(self):
        self.arm(1)
        self.assertFalse(self.guard.prepare(self.sample(100.6,5),None))
        self.assertFalse(self.guard.prepare(self.sample(100.8,8),None))
        self.assertTrue(self.guard.prepare(self.sample(101.,8),None))
        self.assertEqual(self.guard.phase,'idle')

    def test_no_sensor_wrap_at_360_degrees(self):
        self.arm(1)
        self.guard.prepare(self.sample(100.6,359),1)
        self.assertTrue(self.guard.prepare(self.sample(100.8,363),1))
        self.assertIsNone(self.guard.error)


if __name__=='__main__':unittest.main()
