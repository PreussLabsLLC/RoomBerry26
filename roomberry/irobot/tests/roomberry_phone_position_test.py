import logging
import unittest
from math import hypot, pi
from unittest.mock import Mock

from roomberry_localization import AprilTagLocalizer
from roomberry_phone_position import PhonePositionCorrection
from roomberry_navlink import NavLinkReceiver, FIELDS


class PhonePositionTest(unittest.TestCase):
    def setUp(self):
        self.receiver = Mock()
        self.row = dict(session=1, alignment=0, flags=3, tracking=2,
                        frame_monotonic=100., frame_age_us=0, heading_rad=0.,
                        x_mm=0., y_mm=0., forward_mm_s=0., left_mm_s=0., yaw_rad_s=0.)
        self.receiver.latest_observation.side_effect = lambda: dict(self.row)
        self.aid = PhonePositionCorrection(self.receiver, logging.getLogger('test'),
                                          mount_yaw_deg=0, lens_x_mm=0, lens_y_mm=0)
        self.localizer = AprilTagLocalizer({}, [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
        self.localizer._pose = dict(x_mm=1000., y_mm=1000., heading_rad=0.)
        self.pose = dict(self.localizer._pose, localized=True, accepted_tag_ids=(('tag16h5',1),))
        self.aid.apply(self.localizer, self.pose, 100., 0)
        self.pose['accepted_tag_ids'] = ()

    def step(self, now):
        self.row['frame_monotonic'] = now
        self.pose = self.aid.apply(self.localizer, self.pose, now, 0)
        return self.pose

    def test_converges_continuously_and_preserves_heading_and_tag_age(self):
        self.localizer._last_tag_time = 90.
        for i in range(1, 501):
            self.row['x_mm'] = min(i*10., 300.)
            old = dict(self.pose)
            self.step(100+i*.2)
            self.assertLessEqual(hypot(self.pose['x_mm']-old['x_mm'],
                                      self.pose['y_mm']-old['y_mm']), 1.000001)
        self.assertLess(abs(self.pose['x_mm']-1300), 10)
        self.assertEqual(self.pose['heading_rad'], 0)
        self.assertEqual(self.localizer._last_tag_time, 90.)
        self.assertEqual(self.pose['x_mm'], self.localizer._pose['x_mm'])

    def test_stale_tracking_and_identity_changes_require_new_tag(self):
        for change in ({'tracking':1}, {'session':2}, {'alignment':1}, {'frame_age_us':900000}):
            with self.subTest(change=change):
                self.setUp()
                self.row.update(change, x_mm=100.)
                old = dict(self.pose)
                self.step(100.2)
                self.assertEqual(self.pose, old)
                self.assertIsNone(self.aid.anchor)
                self.row.update(tracking=2, frame_age_us=0)
                self.step(100.4)
                self.assertEqual(self.pose, old)

    def test_packet_jump_and_long_loop_do_not_jump_robot(self):
        self.row['x_mm'] = 2000.
        old = dict(self.pose)
        self.step(100.2)
        self.assertEqual(self.pose, old)
        self.assertIsNone(self.aid.anchor)
        self.setUp()
        self.row['x_mm'] = 100.
        old = dict(self.pose)
        self.step(110.)
        self.assertLessEqual(self.pose['x_mm']-old['x_mm'], 1.25)

    def test_reanchor_does_not_apply_phone_translation(self):
        self.row['x_mm'] = 100.
        self.pose['accepted_tag_ids'] = (('tag16h5',2),)
        old = dict(self.pose)
        self.step(100.2)
        self.assertEqual(self.pose, old)
        self.pose['accepted_tag_ids'] = ()
        old['accepted_tag_ids'] = ()
        self.step(100.4)
        self.assertEqual(self.pose, old)

    def test_receiver_ignores_duplicates_and_detects_delayed_frames(self):
        receiver = NavLinkReceiver()
        row = dict(self.row, seq=10, send_us=1000000, frame_us=1000000)
        def observe(received):
            receiver._observe(tuple(row.get(k, 0) for k in FIELDS), received)
        observe(100.)
        row['x_mm'] = 999.
        observe(100.1)
        self.assertEqual(receiver.latest_observation()['x_mm'], 0.)
        row.update(seq=11, send_us=1100000, frame_us=1100000)
        observe(102.)
        self.assertAlmostEqual(receiver.latest_observation()['frame_monotonic'], 100.1)

    def test_epoch_change_or_disabled_mode_cannot_move_pose(self):
        self.row.update(x_mm=100., frame_monotonic=100.2)
        old = dict(self.pose)
        self.aid.apply(self.localizer, self.pose, 100.2, 0, enabled=False)
        self.assertEqual(self.localizer._pose['x_mm'], old['x_mm'])
        self.aid.apply(self.localizer, self.pose, 100.2, 1)
        self.assertIsNone(self.aid.anchor)

    def test_camera_lever_arm_does_not_create_false_translation_on_turns(self):
        self.aid = PhonePositionCorrection(self.receiver, logging.getLogger('test'),
                                          mount_yaw_deg=0, lens_x_mm=-145, lens_y_mm=-22)
        self.row.update(x_mm=-145., y_mm=-22.)
        self.pose['accepted_tag_ids'] = (('tag16h5',1),)
        self.aid.apply(self.localizer, self.pose, 100., 0)
        self.pose.update(accepted_tag_ids=(), heading_rad=pi/2)
        self.localizer._pose['heading_rad'] = pi/2
        self.row.update(heading_rad=pi/2, x_mm=22., y_mm=-145.)
        self.step(100.2)
        self.assertAlmostEqual(self.pose['x_mm'], 1000.)
        self.assertAlmostEqual(self.pose['y_mm'], 1000.)

    def test_nudge_persists_through_odometry_and_respects_bounds(self):
        localizer = self.localizer
        localizer.room_bounds_mm = (0, 0, 1100, 1100)
        localizer.update((), 0, 0, new_detections=False)
        self.assertTrue(localizer.nudge_position(1, 2))
        result = localizer.update((), 10, 0, new_detections=False)
        self.assertEqual((result['x_mm'], result['y_mm']), (1011, 1002))
        self.assertFalse(localizer.nudge_position(500, 0))
        self.assertFalse(localizer.nudge_position(float('nan'), 0))


if __name__ == '__main__':
    unittest.main()
