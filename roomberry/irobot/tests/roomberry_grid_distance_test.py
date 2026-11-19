# @(#)roomberry_grid_distance_test.py 3.2.return.3 2026/11/19 12:38:26
"""Distance survey stopping, operator gates and independent range evidence."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import roomberry_calibration_test as fixture
from roomberry_gridrunner_test import packet
from roomberry_gridrunner import GRID_FIELDS, decode_grid_packet
from roomberry_grid_distance import GridDistanceDrive


class DistanceTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CalibrationTest('test_cruise_speed_is_50_mm_s')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        for name in ('roomberry_grid_distance', 'roomberry_gridrunner'):
            for clock, offset in (('monotonic', 0), ('time', 1700000000)):
                p = patch(name+'.'+clock, side_effect=lambda offset=offset:self.f.now+offset)
                p.start(); self.addCleanup(p.stop)
        self.m = self.f.m
        self.m.set_mode('idle')
        self.row = dict(zip(GRID_FIELDS, decode_grid_packet(packet())))
        self.m.navlink = SimpleNamespace(latest_grid_observation=lambda:self.row,
                                        latest_health_observation=lambda:self.f.health)
        self.m.grid_distance_operation('grid_distance_start', dict(start_mm=304.8, tile_mm=304.8, autonomous=False))
        self.g = self.m.gridrunner

    def tick(self, seconds=.1, delta=0):
        self.f.now += seconds
        self.f.state['distance'] += delta
        self.row.update(received_monotonic=self.f.now, frame_monotonic=self.f.now-.01)
        self.f.health['received_monotonic'] = self.f.now
        self.g.tick(self.f.state)

    def scan(self, clear=True):
        self.tick()
        self.tick(1.1)
        self.assertEqual(self.g.stage, 'scanning')
        self.f.camera.last_detection_time = 1700000000+self.f.now+.01
        self.f.camera.latest_detections = [dict(id=15, family='tag16h5', hamming=0,
            decision_margin=40, distance_mm=335.28, depth_mm=330,
            raw_distance_mm=304.8, pose_translation_scale=1.10,
            tag_pose_camera=dict(error=1))] if clear else []
        self.tick()
        self.assertEqual(self.g.stage, 'awaiting_measure')

    def test_scan_measure_move_and_crossing_stop(self):
        self.scan()
        with self.assertRaises(ValueError): self.g.advance()
        self.g.measure(304.8)
        self.assertAlmostEqual(self.g.records[-1]['error_pct'], 10)
        self.assertEqual(self.g.records[-1]['raw_camera_distance_mm'], 304.8)
        self.assertEqual(self.g.records[-1]['pose_translation_scale'], 1.10)
        self.g.advance()
        self.assertEqual(self.g.stage, 'stepping')
        self.tick(delta=-50)
        self.row['crossing_count'] = 1
        self.tick(delta=-50)
        self.assertEqual(self.g.stage, 'settling')
        self.f.robot.end_motion_lease.assert_called()

    def test_unclear_scan_waits_for_last_tape_then_ends(self):
        self.scan(False)
        with self.assertRaises(ValueError): self.g.advance()
        self.g.measure(305)
        self.assertEqual(self.g.result['status'], 'complete')
        self.assertEqual(self.m._mode, 'idle')

    def test_one_tile_fallback_stops_without_crossing(self):
        self.scan(); self.g.measure(304.8); self.g.advance()
        for _ in range(4): self.tick(delta=-80)
        self.assertEqual(self.g.stage, 'settling')

    def test_stale_phone_stops_moving(self):
        self.scan(); self.g.measure(304.8); self.g.advance()
        self.f.now += 1
        self.g.tick(self.f.state)
        self.assertEqual(self.g.result['status'], 'stopped')

    def test_cap_prevents_another_tile_and_rejects_bad_numbers(self):
        for value in ('nan', 'inf', '-1'):
            with self.assertRaises(ValueError):
                self.m.grid_distance_operation('grid_distance_start', dict(start_mm=value))
        self.scan(); self.g.measure(4900); self.g.advance()
        self.assertEqual(self.g.result['status'], 'complete')
        self.assertIn('5 m', self.g.result['reason'])

    def test_tape_limit_ends_without_another_move(self):
        self.scan(); self.g.measure(5001)
        self.assertEqual(self.g.result['status'], 'complete')

    def test_operator_commands_reject_unknown_parameters(self):
        self.scan()
        with self.assertRaises(ValueError):
            self.m.grid_distance_operation('grid_distance_measure', dict(tape_mm=300, bad=1))
        with self.assertRaises(ValueError):
            self.m.grid_distance_operation('grid_distance_next', dict(bad=1))
        self.assertEqual(self.g.stage, 'awaiting_measure')

    def test_wheel_cap_survives_clear_final_scan(self):
        self.scan(); self.g.measure(304.8); self.g.advance()
        self.g.origin = 4740
        self.tick(delta=-60)
        self.assertEqual(self.g.stage, 'settling')
        self.tick(1.1)
        self.f.camera.last_detection_time = 1700000000+self.f.now+.01
        self.tick()
        self.assertIn('5 m', self.g.stop_reason)
        with self.assertRaises(ValueError): self.g.advance()
        self.g.measure(4990)
        self.assertEqual(self.g.stage, 'complete')

    def test_contact_and_configuration_changes_abort(self):
        self.scan(); self.g.measure(304.8); self.g.advance()
        self.row['calibration'] += 1
        self.f.health['calibration'] += 1
        self.tick()
        self.assertEqual(self.g.result['status'], 'stopped')

    def test_arrival_between_tick_start_and_snapshot_is_not_false_staleness(self):
        self.scan()
        def arriving_row():
            self.f.now += .01
            self.row.update(received_monotonic=self.f.now, frame_monotonic=self.f.now-.01)
            return self.row
        self.m.navlink.latest_grid_observation = arriving_row
        self.g.tick(self.f.state)
        self.assertEqual(self.g.stage, 'awaiting_measure')
        self.assertIsNone(self.g.result)

    def test_final_tape_after_safety_stop_records_without_rearming(self):
        self.scan(); self.g.abort('phone telemetry expired')
        self.f.robot.begin_motion_lease.reset_mock()
        self.m.grid_distance_operation('grid_distance_measure', {'tape_mm':'4255'})
        self.assertEqual(self.g.records[-1]['tape_mm'], 4255)
        self.assertTrue(self.g.records[-1]['recorded_after_stop'])
        self.assertEqual(self.g.stage, 'stopped')
        self.assertEqual(self.m._mode, 'idle')
        self.f.robot.begin_motion_lease.assert_not_called()
        with self.assertRaises(ValueError): self.m.grid_distance_operation('grid_distance_next', {})

    def test_tape_after_stop_rejects_robot_move_and_epoch_reset(self):
        self.scan(); self.g.abort('test stop')
        self.f.state['distance'] += 50
        with self.assertRaises(ValueError): self.m.grid_distance_operation('grid_distance_measure', {'tape_mm':'4255'})
        self.f.state['distance'] -= 50
        self.f.state['angle'] += 5
        with self.assertRaises(ValueError): self.m.grid_distance_operation('grid_distance_measure', {'tape_mm':'4255'})
        self.f.state['angle'] -= 5
        self.f.state['odometry_epoch'] += 1
        with self.assertRaises(ValueError): self.m.grid_distance_operation('grid_distance_measure', {'tape_mm':'4255'})
        self.assertIsNone(self.g.records[-1]['tape_mm'])

    def test_parked_sensor_glitch_waits_without_motor_rearm(self):
        self.scan();self.g.measure(304.8)
        self.f.robot.begin_motion_lease.reset_mock()
        self.f.state.update(ready=False,age=.6)
        self.tick()
        self.assertEqual(self.g.stage,'awaiting_measure')
        self.assertTrue(self.g.last['sensor_wait'])
        with self.assertRaises(ValueError):self.g.advance()
        self.tick(.3)
        self.f.state.update(ready=True,age=0)
        self.tick()
        self.assertIsNone(self.g.result)
        self.assertIsNone(self.g.sensor_wait_started)
        self.f.robot.begin_motion_lease.assert_not_called()

    def test_parked_sensor_grace_expires(self):
        self.scan();self.f.state['ready']=False;self.tick();self.tick(1.1)
        self.assertEqual(self.g.stage,'stopped')

    def test_moving_sensor_fault_stops_immediately(self):
        self.scan();self.g.measure(304.8);self.g.advance()
        self.f.state['ready']=False;self.tick()
        self.assertEqual(self.g.stage,'stopped')
        self.assertIsNone(self.g.sensor_wait_started)

    def test_parked_recovery_rejects_changed_position(self):
        self.scan();self.f.state['ready']=False;self.tick()
        self.f.state.update(ready=True,distance=50)
        self.tick();self.assertEqual(self.g.stage,'stopped')

    def test_stationary_wait_does_not_mask_contact(self):
        self.scan();self.f.state['ready']=False
        self.f.state['sensors'].bumps_and_wheel_drops.bump_right=True
        self.tick();self.assertEqual(self.g.stage,'stopped')

    def test_first_tape_entry_anchors_restarted_station_labels(self):
        self.scan();self.g.measure(1214)
        self.assertEqual(self.g.start_mm,1214)
        self.assertEqual(self.g.records[-1]['expected_mm'],1214)
        self.assertEqual(self.g.configured_start_mm,304.8)
        self.g.advance();self.tick(delta=-100);self.tick(delta=-100);self.tick(delta=-110)
        self.tick(1.1)
        self.f.camera.last_detection_time=1700000000+self.f.now+.01
        self.tick()
        self.assertAlmostEqual(self.g.records[-1]['expected_mm'],1518.8)

    def autonomous_step(self):
        self.scan()
        self.g.autonomous = True
        self.g.advance()

    def test_autonomous_crossing_scans_then_continues_without_tape(self):
        self.autonomous_step()
        self.tick(delta=-150)
        self.row['crossing_count'] = 1
        self.tick(delta=-150)
        self.assertEqual(self.g.stage, 'settling')
        self.tick(1.1)
        self.f.camera.last_detection_time = 1700000000+self.f.now+.01
        self.tick()
        self.assertEqual(self.g.stage, 'stepping')
        self.assertIsNone(self.g.records[-1]['tape_mm'])
        self.assertIsNone(self.g.records[-1]['expected_mm'])

    def test_missing_crossing_forward_50_retry_then_skip(self):
        self.autonomous_step()
        for _ in range(4): self.tick(delta=-85)
        self.assertIsNotNone(self.g.recovery_origin)
        self.tick(delta=25)
        self.assertIsNotNone(self.g.recovery_origin)
        self.tick(delta=25)
        self.assertIsNone(self.g.recovery_origin)
        self.tick(delta=-50)
        self.assertEqual(self.g.crossing_retries, 2)
        self.tick(delta=50)
        self.tick(delta=-50)
        self.assertEqual(self.g.skipped_crossings, 1)
        self.assertIsNone(self.g.result)
        self.assertEqual(self.g.stage, 'stepping')
        self.tick(delta=-100)
        self.row['crossing_count'] = 1
        self.tick(delta=-100)
        self.assertEqual(self.g.stage, 'settling')

    def test_forward_recovery_crossing_is_not_a_station(self):
        self.autonomous_step()
        for _ in range(4): self.tick(delta=-85)
        self.row['crossing_count'] = 1
        self.tick(delta=25)
        self.assertEqual(self.g.stage, 'stepping')
        self.tick(delta=25)
        self.assertEqual(self.g.step_count, 1)
        self.tick(delta=-25)
        self.assertEqual(self.g.stage, 'stepping')
        self.row['crossing_count'] = 2
        self.tick(delta=-25)
        self.assertEqual(self.g.stage, 'settling')

    def test_low_confidence_retraces_fifty_then_rechecks_without_weak_steering(self):
        self.autonomous_step()
        self.row['confidence'] = .640475869
        self.tick(delta=-100)
        self.assertIsNone(self.g.result)
        self.assertEqual(self.g.confidence_retries, 1)
        self.assertIsNotNone(self.g.recovery_origin)
        with patch.object(self.m, '_dispatch') as dispatch:
            self.tick(delta=25)
            self.assertEqual(dispatch.call_args.args[0]['steering'], 0)
            self.assertEqual(dispatch.call_args.args[0]['velocity'], 50)
        self.tick(delta=25)
        self.assertIsNone(self.g.recovery_origin)
        self.tick(delta=-25)
        self.assertEqual(self.g.confidence_retries, 1)
        self.tick(delta=-25)
        self.assertEqual(self.g.confidence_retries, 2)
        self.assertIsNone(self.g.result)

    def test_persistent_low_confidence_holds_active_run_then_resumes(self):
        self.autonomous_step()
        self.row['confidence'] = .64
        self.tick(delta=-100)
        for _ in range(2):
            self.tick(delta=50)
            self.tick(delta=-50)
        self.assertTrue(self.g.confidence_hold)
        self.assertEqual(self.g.stage, 'stepping')
        self.assertIsNone(self.g.result)
        self.f.robot.renew_motion_lease.reset_mock()
        self.tick(5)
        self.f.robot.renew_motion_lease.assert_not_called()
        self.row['confidence'] = .75
        self.tick()
        self.assertFalse(self.g.confidence_hold)
        self.assertIsNone(self.g.result)
        self.f.robot.renew_motion_lease.assert_called()

    def test_confidence_recovery_keeps_contact_safety(self):
        self.autonomous_step()
        self.row['confidence'] = .64
        self.tick(delta=-100)
        self.f.state['sensors'].bumps_and_wheel_drops.bump_right = True
        self.tick(delta=10)
        self.assertIn('right bumper pressed', self.g.result['reason'])

    def test_contact_names_bumper_side(self):
        self.autonomous_step()
        self.f.state['sensors'].bumps_and_wheel_drops.bump_left = True
        self.tick()
        self.assertIn('left bumper pressed', self.g.result['reason'])
        self.assertNotIn('battery', self.g.result['reason'])

    def test_moving_sensor_age_is_reported(self):
        self.autonomous_step()
        self.f.state['age'] = .8
        self.tick()
        self.assertIn('sensor age 0.80 seconds', self.g.result['reason'])

    def test_line_loss_is_distinct_from_low_confidence(self):
        self.autonomous_step()
        self.row.update(flags=2, reason=1)
        self.tick()
        self.assertEqual(self.g.last['tracking'], 'waiting for grout line')
        self.assertEqual(self.g.last['velocity_mm_s'], 0)
        self.tick(3.1)
        self.assertIn('lost the grout line', self.g.result['reason'])
        self.assertIn('did not reacquire', self.g.result['reason'])

    def test_autonomous_survey_retraces_two_fifty_mm_steps(self):
        self.autonomous_step()
        self.tick(delta=-125)
        self.row.update(flags=2, reason=1)
        self.tick()
        for number in (1, 2):
            self.tick(3.1)
            self.assertEqual(self.g.line_retrace_steps, number)
            self.assertEqual(self.g.line_retrace_target, self.f.state['distance'] + 50)
            self.tick()
            self.assertEqual(self.g.last['velocity_mm_s'], 50)
            self.tick(delta=50)
            self.assertEqual(self.g.last['velocity_mm_s'], 0)
            self.assertIsNone(self.g.line_retrace_target)
        self.tick(3.1)
        self.assertIn('retrace limit', self.g.result['reason'])

    def test_autonomous_survey_resumes_after_two_clear_frames(self):
        self.autonomous_step()
        self.row.update(flags=2, reason=1)
        self.tick()
        self.f.robot.end_motion_lease.assert_called()
        self.f.robot.begin_motion_lease.reset_mock()
        self.row.update(flags=3, reason=0, confidence=.9)
        self.tick()
        self.f.robot.begin_motion_lease.assert_not_called()
        self.g.tick(self.f.state)
        self.f.robot.begin_motion_lease.assert_not_called()
        self.tick()
        self.f.robot.begin_motion_lease.assert_called_once_with(.6)
        self.assertIsNone(self.g.line_loss_started)

    def test_survey_uses_phone_bump_policy(self):
        self.autonomous_step()
        self.f.robot.phone_bump_speed_change.return_value = None
        self.f.health.update(bump_count=self.f.health['bump_count']+1, last_bump_peak_mm_s2=4200)
        self.tick()
        self.assertEqual(self.g.stage, 'stepping')
        self.f.health['last_bump_peak_mm_s2'] = 7100
        self.tick()
        self.assertIn('phone impact during distance survey', self.g.result['reason'])

    def test_autonomous_default_and_pitch(self):
        self.m.set_mode('idle')
        self.m.grid_distance_operation('grid_distance_start', dict(start_mm=304.8))
        self.assertTrue(self.m.gridrunner.autonomous)
        self.assertEqual(self.m.gridrunner.tile_mm, 305.45)

    def test_rescan_does_not_move_or_discard_evidence(self):
        self.scan(); self.g.measure(304.8); self.g.rescan()
        self.assertEqual(self.g.stage, 'settling')
        self.assertEqual(len(self.g.records), 1)
        self.assertFalse(self.g.measured)


if __name__ == '__main__': unittest.main()
