# @(#)roomberry_phone_bumps_test.py 3.1.grout.17 2026/11/05
import unittest
from roomberry_phone_bumps import PhoneBumpPolicy, REACTION_MIN_MM_S2


class PhoneBumpPolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy=PhoneBumpPolicy()
        self.health=dict(session=1,calibration=2,bump_count=0,last_bump_peak_mm_s2=0)
        self.policy.baseline(self.health)

    def event(self,count,peak,ignore=False):
        self.health.update(bump_count=count,last_bump_peak_mm_s2=peak)
        return self.policy.observe(self.health,lambda row:ignore)

    def test_previous_phantom_peaks_are_record_only(self):
        for count,peak in enumerate((3804,3844,4900,5245.4),1):
            self.assertEqual(self.event(count,peak)['action'],'record-only')
        self.assertEqual(len(self.policy.events),4)

    def test_exact_point_six_g_and_larger_react(self):
        for count,peak in enumerate((REACTION_MIN_MM_S2,6000),1):
            self.assertEqual(self.event(count,peak)['action'],'react')

    def test_refined_episode_peak_is_rechecked(self):
        self.assertEqual(self.event(1,3804)['action'],'record-only')
        self.assertEqual(self.event(1,6000)['action'],'react')
        self.assertEqual(len(self.policy.events),1)
        self.assertEqual(self.policy.events[0]['peak_mm_s2'],6000)
        self.assertIsNone(self.event(1,7000))

    def test_same_weak_packet_is_not_repeated(self):
        self.event(1,3804)
        self.assertIsNone(self.event(1,3804))

    def test_speed_change_ignore_remains_consumed_when_peak_refines(self):
        self.assertEqual(self.event(1,6000,True)['action'],'speed-change-ignore')
        self.assertIsNone(self.event(1,10000))

    def test_initial_old_events_and_new_session_are_baselined(self):
        policy=PhoneBumpPolicy()
        self.assertIsNone(policy.observe(dict(self.health,bump_count=5),lambda _:False))
        self.assertIsNone(self.policy.observe(dict(self.health,session=5,bump_count=10),lambda _:False))

    def test_lower_cutoff_rechecks_pending_peak_without_new_event(self):
        self.assertEqual(self.event(1, 5337.313)['action'], 'record-only')
        result = self.policy.observe(self.health, lambda _: False, minimum_mm_s2=.5*9806.65)
        self.assertEqual(result['action'], 'react')
        self.assertEqual(len(self.policy.events), 1)
        self.assertIsNone(self.policy.observe(self.health, lambda _: False, minimum_mm_s2=.5*9806.65))

    def test_missing_strength_does_not_silently_disable_impact_handling(self):
        self.assertEqual(self.event(1,None)['action'],'react')


if __name__=='__main__':unittest.main()
