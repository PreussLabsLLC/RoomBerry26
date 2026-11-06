# @(#)roomberry_gridrunner_test.py 3.1.tiles.6 2026/11/06
"""Grid wire contract, freshness, motion ownership, Clock and safety checks."""
import csv
import io
import json
import logging
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
import roomberry_calibration_test as fixture
from roomberry_gridrunner import GRID_PACKET,GRID_FIELDS,decode_grid_packet,grid_correction,build_crossing_report
from roomberry_navlink import NavLinkReceiver,decode_packet,export_csv
from roomberry_control import RobotCommandArbiter


def packet(**changes):
    row=dict(magic=b'NVLK',version=1,type=5,length=128,session=11,calibration=22,
             seq=1,flags=3,direction=-1,reason=0,frame_us=1000000,send_us=1010000,
             scan1_x=.55,scan1_y=.35,scan2_x=.55,scan2_y=.65,offset_mm=-13,
             line_angle_rad=0,confidence=1,correction=0,gain=2,correction_limit=.25,
             lens_left_mm=-13,height_mm=85,image_width=480,image_height=640,
             crossing_magic=0xc7,crossing_version=1,crossing_flags=0,crossing_count=0,
             crossing_us=0,crossing_y=0.,crossing_confidence=0.,crossing_interval_s=0.)
    row.update(changes)
    return GRID_PACKET.pack(*(row[k] for k in GRID_FIELDS))


def legacy_packet(**changes):
    """Pre-crossing app: type-5 trailer was 28 zero bytes."""
    data=bytearray(packet(**changes))
    data[-28:]=bytes(28)
    return bytes(data)


class GridWireTest(unittest.TestCase):
    def test_wire_validation_and_correction_contract(self):
        self.assertEqual(len(packet()),128)
        self.assertEqual(decode_packet(packet())[2],5)
        for kw in [dict(direction=0),dict(confidence=float('nan')),dict(flags=7),
                   dict(crossing_magic=0xc8),dict(crossing_version=2),dict(crossing_flags=2),
                   dict(crossing_count=1),dict(crossing_y=1.5),dict(crossing_confidence=2),
                   dict(crossing_interval_s=-1),dict(crossing_us=2000000),
                   dict(frame_us=1),dict(scan1_y=.9),dict(correction=.1),dict(gain=0),
                   dict(correction_limit=.4),dict(confidence=.1),dict(height_mm=0),dict(session=0)]:
            with self.subTest(kw=kw),self.assertRaises(ValueError):decode_grid_packet(packet(**kw))
        decode_grid_packet(packet(flags=2,reason=1,frame_us=0))
        decode_grid_packet(packet(flags=0,reason=3))
        for direction in (-1,1):
            self.assertGreater(grid_correction(20,0,direction,2,.25),0)
            self.assertGreater(grid_correction(0,.05,direction,2,.25)*direction,0)

    def test_crossing_trailer_and_legacy_padding(self):
        values=dict(zip(GRID_FIELDS,decode_grid_packet(packet(
            crossing_flags=1,crossing_count=4,crossing_us=990000,crossing_y=.5,
            crossing_confidence=.9,crossing_interval_s=3.06))))
        self.assertEqual(values['crossing_count'],4)
        self.assertAlmostEqual(values['crossing_y'],.5)
        self.assertAlmostEqual(values['crossing_interval_s'],3.06,places=4)
        legacy=dict(zip(GRID_FIELDS,decode_grid_packet(legacy_packet())))
        self.assertEqual(legacy['crossing_magic'],0)
        self.assertEqual(legacy['crossing_count'],0)

    def test_order_retired_sessions_and_frozen_frame(self):
        receiver=NavLinkReceiver()
        receiver._observe(decode_packet(packet()),100)
        receiver._observe(decode_packet(packet(seq=2,send_us=1020000)),100.01)
        receiver._observe(decode_packet(packet(seq=1,offset_mm=20,correction=2*20/600)),100.02)
        self.assertEqual(receiver.latest_grid_observation()['seq'],2)
        receiver._observe(decode_packet(packet(session=12)),100.1)
        receiver._observe(decode_packet(packet(seq=3)),100.2)
        self.assertEqual(receiver.latest_grid_observation()['session'],12)
        self.assertIsNone(receiver.latest_ground_observation())

    def test_type5_mixed_log_export(self):
        from roomberry_navlink import LOG_HEADER,LOG_MAGIC,RECEIPT
        from roomberry_groundhog_test import ground
        with TemporaryDirectory() as directory:
            path=Path(directory)/'log.bin'
            path.write_bytes(LOG_HEADER.pack(LOG_MAGIC,1,144,128)+RECEIPT.pack(1,2)+ground()+RECEIPT.pack(3,4)+packet())
            out=io.StringIO();export_csv(path,out);rows=list(csv.DictReader(io.StringIO(out.getvalue())))
            self.assertEqual([r['type'] for r in rows],['2','5'])
            self.assertEqual(rows[1]['lens_left_mm'],'-13.0')

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'),'requires Swift')
    def test_actual_swift_detector_and_wire(self):
        root=Path(__file__).resolve().parents[3]
        with TemporaryDirectory() as directory:
            binary=str(Path(directory)/'grid-check')
            sources=[root/'ios-app/GroundHog/GroundHog/GroundMotion.swift',
                     root/'ios-app/GridRunner/GridRunner/GridLine.swift',
                     root/'ios-app/GridRunner/GridRunner/GridCrossing.swift',
                     root/'ios-app/GridRunner/GridRunner/GridPacket.swift',
                     root/'ios-app/GridRunner/tests/GridLineCheck.swift']
            result=subprocess.run(['swiftc','-module-cache-path',str(Path(directory)/'cache'),
                                   *map(str,sources),'-o',binary],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([binary],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            values=dict(zip(GRID_FIELDS,decode_grid_packet(bytes.fromhex(result.stdout.splitlines()[0]))))
            self.assertEqual(values['session'],11)
            self.assertEqual(values['lens_left_mm'],26)
            self.assertLess(abs(values['offset_mm']-26),.15)
            self.assertEqual(values['crossing_magic'],0xc7)
            self.assertEqual(values['crossing_count'],3)
            self.assertEqual(values['crossing_us'],2900000)
            self.assertAlmostEqual(values['crossing_y'],.5012,places=4)
            self.assertAlmostEqual(values['crossing_interval_s'],3.06,places=4)
            self.assertIn('transverse stripes',result.stdout)

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'),'requires Swift')
    def test_actual_swift_crossing_detector(self):
        root=Path(__file__).resolve().parents[3]
        with TemporaryDirectory() as directory:
            binary=str(Path(directory)/'crossing-check')
            sources=[root/'ios-app/GridRunner/GridRunner/GridCrossing.swift',
                     root/'ios-app/GridRunner/tests/GridCrossingCheck.swift']
            result=subprocess.run(['swiftc','-O','-module-cache-path',str(Path(directory)/'cache'),
                                   *map(str,sources),'-o',binary],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([binary],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('crossings=15 expected=15',result.stdout)
            self.assertIn('tile crossings:',result.stdout)


class GridDriveTest(unittest.TestCase):
    def setUp(self):
        self.f=fixture.CalibrationTest('test_cruise_speed_is_50_mm_s');self.f.setUp();self.addCleanup(self.f.doCleanups)
        p=patch('roomberry_gridrunner.monotonic',side_effect=lambda:self.f.now);p.start();self.addCleanup(p.stop)
        p=patch('roomberry_gridrunner.time',side_effect=lambda:1700000000+self.f.now);p.start();self.addCleanup(p.stop)
        p=patch('roomberry_tag_return.monotonic',side_effect=lambda:self.f.now);p.start();self.addCleanup(p.stop)
        p=patch('roomberry_tag_return.time',side_effect=lambda:1700000000+self.f.now);p.start();self.addCleanup(p.stop)
        self.m=self.f.m
        self.m.mapper.robot_radius_mm = 174
        self.m.mapper.cell_size_mm = 87
        self.row=dict(zip(GRID_FIELDS,decode_grid_packet(packet())))
        self.m.navlink=SimpleNamespace(latest_grid_observation=lambda:self.row,latest_health_observation=lambda:self.f.health)
        self.m.set_mode('gridrunner');self.g=self.m.gridrunner
        self.refresh()

    def refresh(self):
        self.row.update(received_monotonic=self.f.now,frame_monotonic=self.f.now-.05)
        self.f.health['received_monotonic']=self.f.now

    def tick(self,delta=0):
        self.f.now+=.2;self.f.state['distance']+=delta;self.refresh();self.g.tick(self.f.state)

    def test_stream_waits_until_new_packet_then_drives_through_arbiter(self):
        self.row['received_monotonic']=self.g.started-1
        self.g.tick(self.f.state);self.assertEqual(self.g.stage,'waiting')
        self.tick();self.assertEqual(self.g.stage,'driving')
        drive=[c for c in self.f.robot.execute.call_args_list if c.args[0]=='drive_direct'][-1]
        self.assertEqual(drive.kwargs,dict(right_velocity=-100,left_velocity=-100,ramp=False,steps=True))

    def test_waiting_does_not_consume_movement_progress_timeout(self):
        self.f.now+=8
        self.tick()
        self.assertEqual(self.g.stage,'driving')

    def test_tile_crossings_are_recorded_once_with_odometry(self):
        self.tick()
        self.row.update(crossing_flags=1,crossing_count=1,crossing_us=990000,
                        crossing_y=.5,crossing_confidence=.9,crossing_interval_s=0.)
        self.tick(delta=-100)
        self.assertEqual(len(self.g.crossings),1)
        record=self.g.crossings[0]
        self.assertEqual(record['count'],1)
        self.assertEqual(record['wheel_distance_mm'],-100)
        self.assertEqual(record['stage'],'driving')
        self.assertEqual(record['session'],11)
        self.assertEqual(self.g.last['tiles'],1)
        # A repeated observation of the same count must not duplicate the event.
        self.tick()
        self.assertEqual(len(self.g.crossings),1)
        # A skipped packet is recorded as missed instead of inventing a time.
        self.row.update(crossing_count=4,crossing_us=1000000,crossing_interval_s=3.0)
        self.tick(delta=-100)
        self.assertEqual(len(self.g.crossings),2)
        self.assertEqual(self.g.crossings[1]['missed'],2)
        self.assertEqual(self.g.crossings[1]['interval_s'],3.0)
        self.assertEqual(self.g.last['tiles'],4)

    def test_crossing_report_per_tile_and_leg_reset(self):
        self.tick()
        for i in range(1, 4):
            self.row.update(crossing_flags=1, crossing_count=i, crossing_us=900000 + i * 1000,
                            crossing_y=.5, crossing_confidence=.9,
                            crossing_interval_s=3.0 if i > 1 else 0.)
            self.tick(delta=-100)
        self.assertEqual(len(self.g.crossings), 3)
        report = build_crossing_report(self.g.crossings)
        rows, summary = report['rows'], report['summary']
        self.assertEqual([r['tile_mm_span'] for r in rows], [None, 304.8, 304.8])
        self.assertAlmostEqual(rows[1]['wheel_delta_mm'], 100)
        self.assertAlmostEqual(rows[1]['error_mm'], 100 - 304.8)
        self.assertAlmostEqual(summary['median_ratio'], 100 / 304.8)
        self.assertAlmostEqual(summary['total_wheel_ratio'], 100 / 304.8)
        # A return-leg crossing starts a new leg: no delta across turnaround.
        self.g.stage = 'return'
        self.row.update(crossing_count=4, crossing_us=903000, crossing_interval_s=3.0)
        self.tick(delta=50)
        rows = build_crossing_report(self.g.crossings)['rows']
        self.assertIsNone(rows[-1]['wheel_delta_mm'])
        self.assertEqual(rows[-1]['tile_mm_total'], 0.0)

    def test_crossing_report_counts_missed_span(self):
        self.tick()
        self.row.update(crossing_flags=1, crossing_count=1, crossing_us=990000,
                        crossing_y=.5, crossing_confidence=.9, crossing_interval_s=0.)
        self.tick(delta=-100)
        self.row.update(crossing_count=4, crossing_us=1000000, crossing_interval_s=3.0)
        self.tick(delta=-100)
        rows = build_crossing_report(self.g.crossings)['rows']
        self.assertAlmostEqual(rows[1]['tile_mm_span'], 3 * 304.8)
        self.assertAlmostEqual(rows[1]['wheel_delta_mm'], 100)
        self.assertAlmostEqual(rows[1]['error_mm'], 100 - 3 * 304.8)

    def test_abort_persists_crossings_and_report_in_result(self):
        self.tick()
        self.row.update(crossing_flags=1, crossing_count=1, crossing_us=990000,
                        crossing_y=.5, crossing_confidence=.9, crossing_interval_s=0.)
        self.tick(delta=-100)
        self.g.abort('test stop')
        self.assertEqual(len(self.g.result['crossings']), 1)
        self.assertEqual(self.g.result['crossings'][0]['count'], 1)
        self.assertEqual(self.g.result['crossing_report']['summary']['crossings'], 1)
        self.assertEqual(self.g.result['crossing_report']['rows'][0]['count'], 1)

    def test_mid_session_first_count_is_rebaselined_not_missed(self):
        # A fresh GridDrive first sees the ongoing session count mid-run;
        # pre-existing crossings are not new events.
        self.row.update(crossing_flags=1, crossing_count=14, crossing_us=990000,
                        crossing_y=.5, crossing_confidence=.9, crossing_interval_s=3.0)
        self.tick()
        self.assertEqual(self.g.crossings, [])
        self.row.update(crossing_count=15, crossing_us=1000000, crossing_interval_s=3.0)
        self.tick(delta=-100)
        self.assertEqual(len(self.g.crossings), 1)
        self.assertEqual(self.g.crossings[0]['count'], 15)
        self.assertEqual(self.g.crossings[0]['missed'], 0)

    def test_short_outbound_return_never_enters_approach(self):
        # Zero-length outbound (re-run already at the grout end): the seeded
        # pose says 'at tag' but must not trip the approach bound instantly.
        self.tick()
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick(delta=-5)
        for _ in range(7):
            self.row['seq'] += 1
            self.tick()
            if self.g.stage == 'turnaround': break
        self.assertLess(self.g.outbound_mm, 1000)
        self.row.update(flags=3, reason=0, confidence=1)
        self.tick()
        self.assertEqual(self.g.stage, 'threshold_clearance')
        self.m.camera.request_scan.reset_mock()
        for _ in range(15):
            self.row['seq'] += 1
            self.tick(delta=10)
        self.assertEqual(self.g.stage, 'return')
        self.assertIsNone(self.g.result)
        self.tick(delta=10)
        self.assertEqual(self.g.stage, 'return')
        self.m.camera.request_scan.assert_not_called()

    def test_line_end_confirms_on_intermittent_losses(self):
        self.tick()
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick(delta=-5)
        # loss, good, loss, good, loss: never 3 in a row, but 3 total.
        plan = [(2, 1, 0), (3, 0, 1), (2, 1, 0), (3, 0, 1), (2, 1, 0)]
        for seq, (flags, reason, conf) in enumerate(plan, start=10):
            self.row.update(flags=flags, reason=reason, confidence=conf, seq=seq)
            self.tick()
            if self.g.stage == 'turnaround':
                break
        self.assertEqual(self.g.stage, 'turnaround')
        self.assertEqual(self.g.threshold['reason'], 'grout-line end')

    def test_legacy_zero_trailer_does_not_fabricate_crossings(self):
        self.tick()
        self.row.update(crossing_magic=0)
        self.tick(delta=-100)
        self.assertEqual(self.g.crossings,[])
        self.assertEqual(self.g.last['tiles'],0)

    def test_camera_target_preserves_mount_and_seeds_robot_right_of_grout(self):
        self.row.update(lens_left_mm=26, offset_mm=26, line_angle_rad=0)
        self.tick()
        self.assertAlmostEqual(self.g.last['correction'], 0)
        self.assertEqual(self.row['lens_left_mm'], 26)
        self.assertEqual(self.g.last['target_offset_mm'], 26)
        self.assertEqual(self.g.last['tracking_error_mm'], 0)
        self.assertAlmostEqual(self.g.pose['y_mm'], self.g.tag['y']-26)
        self.m._update_run_map(self.f.state)
        self.assertAlmostEqual(self.m._run_map['pose']['y_mm'], self.g.pose['y_mm'])
        self.row['offset_mm'] = 31
        self.tick(delta=-5)
        self.assertGreater(self.g.last['correction'], 0)
        self.assertEqual(self.g.last['tracking_error_mm'], 5)

    def test_slow_approach_pivots_then_drives_equal_wheels(self):
        import math
        self.begin_return()
        self.g.stage = 'approach'
        self.g.final_fix = self.g.tag_fix_applied = True
        self.g.checkpoints = []
        self.g.last_tag_distance = self.f.state['distance']
        self.g.pose.update(x_mm=self.g.tag['x']-550,
            y_mm=self.g.tag['y']-self.g.target_offset_mm+10, heading_rad=.12)
        self.row.update(flags=3, reason=0, confidence=1)
        modes = set()
        for _ in range(300):
            self.row['line_angle_rad'] = -self.g.pose['heading_rad']
            self.row['offset_mm'] = self.g.tag['y']-self.g.pose['y_mm']
            self.tick()
            if self.g.result is not None:
                break
            r = self.g.last
            modes.add(r['steering_mode'])
            left, right = r['left_velocity_mm_s'], r['right_velocity_mm_s']
            if r['steering_mode'] == 'pivot':
                self.assertEqual(left, -right)
                self.assertEqual(r['velocity_mm_s'], 0)
            else:
                self.assertEqual(left, right)
            self.f.state['distance'] += (left+right)/2*.2
            self.f.state['angle'] += math.degrees((right-left)/235*.2)
            if self.g.tag['x']-self.g.pose['x_mm'] <= 174:
                self.f.state['sensors'].bumps_and_wheel_drops.bump_left = True
        self.assertEqual(modes, {'pivot','straight','settling'})
        self.assertEqual(self.g.result['status'], 'complete', self.g.result)

    def test_pivot_stops_on_opposite_heading_response(self):
        self.begin_return()
        self.g.stage = 'approach'
        self.g.final_fix = True
        self.g.checkpoints = []
        self.g.last_tag_distance = self.f.state['distance']
        self.g.pose['heading_rad'] = .15
        self.row['line_angle_rad'] = -.15
        self.tick()
        for _ in range(3): self.tick()
        self.assertEqual(self.g.last['steering_mode'], 'pivot')
        # A right pivot was requested; an observed left turn must stop it.
        for _ in range(4):
            self.f.state['angle'] += 4
            self.tick()
            if self.g.result: break
        self.assertIn('opposite', self.g.result['reason'])

    def test_final_scan_needs_confirmation_and_emits_result_feedback(self):
        self.begin_return()
        self.g._tag_fix = lambda detections: dict(self.g.pose, accepted_tag_ids=(('tag16h5',15),))
        self.m.camera.latest_detections = ()
        self.m._button_beep = Mock()
        self.g._scan(500)
        self.m.camera.last_detection_time = self.g.scan_wall+.01
        self.tick()
        self.assertFalse(self.g.final_fix)
        self.assertEqual(self.g.stage, 'scanning')
        self.m._button_beep.assert_called_with('neutral')
        self.m.camera.last_detection_time = self.g.scan_wall+.01
        self.tick()
        self.assertTrue(self.g.final_fix)
        self.m._button_beep.assert_called_with('happy')

    def test_later_tag_fix_inconsistent_with_wheels_is_confirmed_stationary(self):
        self.begin_return()
        self.g.tag_fix_applied = True
        previous = dict(self.g.pose)
        self.g._tag_fix = lambda detections: dict(previous,
            x_mm=previous['x_mm']+250, accepted_tag_ids=(('tag16h5',15),))
        self.m.camera.latest_detections = ()
        self.m._button_beep = Mock()
        self.g._scan(2000)
        for _ in range(2):
            self.m.camera.last_detection_time = self.g.scan_wall+.01
            self.tick()
        self.assertEqual(self.g.pose['x_mm'], previous['x_mm']+250)
        self.assertFalse(self.g.records[-2]['accepted'])
        self.assertTrue(self.g.records[-1]['accepted'])
        self.assertIn('relocation confirmed', self.g.records[-1]['reason'])
        self.assertEqual(self.g.stage, 'return')
        self.m._button_beep.assert_called_with('happy')

    def test_large_relocation_over_outer_gate_needs_two_fresh_scans(self):
        self.begin_return()
        previous = dict(self.g.pose)
        corrected = dict(previous, x_mm=previous['x_mm']+700,
            accepted_tag_ids=(('tag16h5',15),))
        self.g._tag_fix = lambda detections: corrected
        self.m.camera.latest_detections = ()
        self.g._scan(2000)
        self.m.camera.last_detection_time = self.g.scan_wall+.01
        self.tick()
        self.assertEqual(self.g.pose, previous)
        self.assertEqual(self.g.stage, 'scanning')
        # Replaying an old capture cannot confirm the new request.
        self.m.camera.last_detection_time = self.g.scan_wall-.01
        self.tick()
        self.assertEqual(self.g.pose, previous)
        self.m.camera.last_detection_time = self.g.scan_wall+.01
        self.tick()
        self.assertEqual(self.g.pose['x_mm'], corrected['x_mm'])
        self.assertTrue(self.g.records[-1]['accepted'])

    def test_disagreeing_relocation_scans_hand_off_to_stopped_recovery(self):
        self.begin_return()
        previous = dict(self.g.pose)
        offsets = iter((700, 900))
        self.g._tag_fix = lambda detections: dict(previous,
            x_mm=previous['x_mm']+next(offsets), accepted_tag_ids=(('tag16h5',15),))
        self.m.camera.latest_detections = ()
        self.g._recover_tags = Mock()
        self.g._scan(2000)
        for _ in range(2):
            self.m.camera.last_detection_time = self.g.scan_wall+.01
            self.tick()
        self.assertEqual(self.g.pose, previous)
        self.g._recover_tags.assert_called_once()

    def test_invalid_scan_clears_final_confirmation_candidate(self):
        self.begin_return()
        pose = dict(self.g.pose, accepted_tag_ids=(('tag16h5',15),))
        poses = iter((pose, None, pose))
        self.g._tag_fix = lambda detections: next(poses)
        self.g._recover_tags = Mock()
        self.m.camera.latest_detections = ()
        self.g._scan(500)
        for _ in range(3):
            self.m.camera.last_detection_time = self.g.scan_wall+.01
            self.tick()
        self.assertFalse(self.g.final_fix)
        self.assertFalse(self.g.records[-1]['accepted'])
        self.g._recover_tags.assert_called_once()

    def test_line_end_brakes_immediately_and_confirms_while_stationary(self):
        self.tick()
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick(delta=-5)
        self.assertEqual(self.g.last['velocity_mm_s'], 0)
        self.assertIsNone(self.g.threshold)
        self.f.robot.end_motion_lease.assert_called()
        for _ in range(7):
            self.row['seq'] += 1
            self.tick()
            if self.g.stage == 'turnaround': break
        self.assertEqual(self.g.stage, 'turnaround')
        self.assertEqual(self.g.threshold['reason'], 'grout-line end')
        self.assertEqual(self.g.outbound_mm, 5)

    def test_brief_loss_resumes_only_after_three_good_frames(self):
        self.tick()
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick(delta=-5)
        self.row.update(flags=3, reason=0, confidence=1)
        for count in range(3):
            self.row['seq'] += 1
            self.tick()
            if count < 2: self.assertEqual(self.g.last['velocity_mm_s'], 0)
        self.assertEqual(self.g.last['velocity_mm_s'], -100)
        self.assertIsNone(self.g.threshold)

    def test_repeated_packet_cannot_confirm_line_end(self):
        self.tick()
        self.row.update(flags=2, reason=1, confidence=0)
        for _ in range(17): self.tick()
        self.assertEqual(self.g.stage, 'stopped')
        self.assertIsNone(self.g.threshold)

    def test_stale_telemetry_during_line_end_check_aborts(self):
        self.tick()
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick()
        self.f.now += 1
        self.g.tick(self.f.state)
        self.assertEqual(self.g.stage, 'stopped')
        self.assertIsNone(self.g.threshold)

    def test_stationary_scan_time_does_not_consume_line_loss_allowance(self):
        self.begin_return()
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick(delta=5)
        self.g._scan(2000)
        self.f.now += 12
        self.g._tag_fix = lambda detections: dict(self.g.pose, accepted_tag_ids=(('tag16h5',15),))
        self.m.camera.latest_detections = ()
        self.m.camera.last_detection_time = self.g.scan_wall+.01
        self.tick()
        self.assertLess(self.g.last['line_lost_s'], 1)

    def test_return_endpoint_follows_same_camera_offset(self):
        self.row.update(lens_left_mm=26, offset_mm=26, line_angle_rad=0)
        self.begin_return()
        self.g.stage = 'approach'
        self.g.final_fix = self.g.tag_fix_applied = True
        self.g.checkpoints = []
        self.g.last_tag_distance = self.f.state['distance']
        self.g.pose.update(x_mm=self.g.tag['x']-300,
                           y_mm=self.g.tag['y']-26, heading_rad=0)
        self.tick(delta=5)
        self.assertAlmostEqual(self.g.last['tag_correction'], 0)
        self.assertEqual(self.g.last['velocity_mm_s'], 40)

    def test_launch_bump_is_logged_consumed_and_not_replayed(self):
        self.tick()
        self.f.robot.phone_bump_speed_change.return_value=dict(at=self.f.now,before=(0,0),after=(-30,-30),delay_ms=95)
        self.f.health['bump_count'] += 1
        self.tick(delta=-5)
        self.assertEqual(self.g.stage,'driving')
        self.assertIsNone(self.g.threshold)
        self.f.robot.phone_bump_speed_change.return_value=None
        self.tick(delta=-5)
        self.assertEqual(self.g.stage,'driving')
        self.f.health['bump_count'] += 1
        self.tick(delta=-5)
        self.assertEqual(self.g.stage,'stopped')

    def test_isolated_weak_observations_do_not_move_lost_heading_anchor(self):
        self.tick()
        anchor = self.g.hold_heading
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick(delta=-5)
        self.f.state['angle'] = -6
        self.row.update(flags=3, reason=0, confidence=.5)
        self.tick()
        self.assertEqual(self.g.hold_heading, anchor)
        for _ in range(3): self.tick()
        self.assertEqual(self.g.last['velocity_mm_s'], 0)
        for seq in (2,3):
            self.row.update(seq=seq, confidence=1)
            self.tick()
            self.assertEqual(self.g.hold_heading, anchor)
        self.row['seq'] = 4
        self.tick()
        self.assertEqual(self.g.hold_heading, -6)

    def test_pivot_decision_uses_uncapped_line_error(self):
        import math
        self.begin_return()
        self.g.lost_at, self.g.lost_distance = self.f.now, self.f.state['distance']
        self.row.update(offset_mm=self.g.target_offset_mm+100, line_angle_rad=.1)
        self.tick()
        self.assertEqual(self.g.last['correction'], .25)
        self.assertGreater(self.g.last['heading_error_rad'], math.radians(5))
        for _ in range(3): self.tick()
        self.assertEqual(self.g.last['steering_mode'], 'pivot')

    def test_pi_steering_is_stronger_but_respects_phone_limit(self):
        self.row.update(offset_mm=self.row['lens_left_mm']-30, line_angle_rad=0)
        self.tick()
        self.assertAlmostEqual(self.g.last['correction'], -.2)
        self.row.update(offset_mm=-90)
        self.tick(delta=-10)
        self.assertAlmostEqual(self.g.last['correction'], -.25)
        self.assertEqual(self.g.last['left_velocity_mm_s'], -125)
        self.assertEqual(self.g.last['right_velocity_mm_s'], -75)

    def test_run_map_marks_cookies_from_odometry_in_both_directions(self):
        self.m.discovery_landmarks = {15: dict(world_from_tag=[[0,0,1,7.73],[-1,0,0,1.237],[0,-1,0,.16],[0,0,0,1]])}
        self.m.mapper.robot_radius_mm = 174
        self.m.mapper.cell_size_mm = 87
        self.m._update_run_map(self.f.state)
        self.f.state['distance'] -= 500
        self.m._update_run_map(self.f.state)
        self.assertAlmostEqual(self.m._run_map['pose']['x_mm'], 7056)
        self.assertGreater(self.m.mapper.record_cleaned_sweep.call_count, 10)
        self.f.state['distance'] += 500
        self.m._update_run_map(self.f.state)
        self.assertAlmostEqual(self.m._run_map['pose']['x_mm'], 7556)
        self.assertFalse(self.m.mapper.update_pose.call_args.kwargs['persist'])
        self.assertTrue(all(c.kwargs.get('persist') is False
                            for c in self.m.mapper.record_cleaned_sweep.call_args_list))

    def test_freshness_and_losses_stop_without_auto_resume(self):
        for problem in ('health','frame','receipt','stop','session','direction','config'):
            with self.subTest(problem=problem):
                self.m.set_mode('gridrunner');self.g=self.m.gridrunner
                self.row.update(flags=3,direction=-1,session=11,gain=2);self.f.health['bump_count']=0
                self.tick()
                if problem=='line':self.row['flags']=2
                elif problem=='stop':self.row['flags']=0
                elif problem=='health':self.f.health['received_monotonic']-=1
                elif problem=='frame':self.row['frame_monotonic']-=1
                elif problem=='receipt':self.row['received_monotonic']-=1
                elif problem=='session':self.row['session']=12
                elif problem=='direction':self.row['direction']=1
                elif problem=='config':self.row['gain']=3
                elif problem=='impact':self.f.health['bump_count']=1
                self.g.tick(self.f.state)
                self.assertEqual(self.m._mode,'idle')

    def test_loss_brakes_then_stable_reacquisition_accelerates(self):
        self.tick()
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick(delta=-10)
        self.assertEqual(self.g.stage, 'driving')
        self.assertEqual(self.g.last['velocity_mm_s'], 0)
        self.row.update(flags=3, reason=0, confidence=1)
        for seq in (2,3):
            self.row['seq'] = seq
            self.tick()
            self.assertEqual(self.g.last['velocity_mm_s'], 0)
        self.row['seq'] = 4
        self.tick()
        self.assertEqual(self.g.last['velocity_mm_s'], -100)

    def test_slow_loss_is_bounded_and_stale_telemetry_still_aborts(self):
        self.tick()
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick(delta=-5)
        self.f.now += 31
        self.tick(delta=-5)
        self.assertEqual(self.m._mode, 'idle')

    def begin_return(self):
        self.tick()
        for _ in range(46):
            self.tick(delta=-100)
        self.row.update(flags=2, reason=1, confidence=0)
        for _ in range(7):
            self.row['seq'] += 1
            self.tick()
            if self.g.stage == 'turnaround': break
        self.assertEqual(self.g.stage, 'turnaround')
        self.row.update(flags=3, reason=0, confidence=1)
        self.tick()
        self.assertEqual(self.g.stage, 'threshold_clearance')
        for _ in range(15):
            self.row['seq'] += 1
            self.tick(delta=10)
        self.assertEqual(self.g.stage, 'return')

    def start_clearance(self):
        self.tick()
        for _ in range(46):
            self.tick(delta=-100)
        self.row.update(flags=2, reason=1, confidence=0)
        for _ in range(7):
            self.row['seq'] += 1
            self.tick()
            if self.g.stage == 'turnaround': break
        self.tick()
        self.assertEqual(self.g.stage, 'threshold_clearance')

    def test_clearance_moves_straight_without_scanning_until_150mm(self):
        self.start_clearance()
        self.m.camera.request_scan.reset_mock()
        self.g._recover_tags = Mock()
        for _ in range(14):
            self.row['seq'] += 1
            self.tick(delta=10)
            self.assertEqual(self.g.stage, 'threshold_clearance')
            self.assertEqual(self.g.last['left_velocity_mm_s'], 40)
            self.assertEqual(self.g.last['right_velocity_mm_s'], 40)
        self.row.update(flags=3, reason=0, confidence=1)
        self.row['seq'] += 1
        self.tick(delta=10)
        self.assertEqual(self.g.stage, 'threshold_clearance')
        for _ in range(2):
            self.row['seq'] += 1
            self.tick()
        self.assertEqual(self.g.stage, 'return')
        self.assertEqual(self.g.threshold['clearance_mm'], 150)
        self.m.camera.request_scan.assert_not_called()
        self.g._recover_tags.assert_not_called()

    def test_missing_line_after_clearance_stops_before_tag_recovery(self):
        self.start_clearance()
        self.g._recover_tags = Mock()
        for _ in range(15):
            self.row['seq'] += 1
            self.tick(delta=10)
        self.assertIsNotNone(self.g.clearance_stopped_at)
        self.f.robot.end_motion_lease.assert_called()
        for _ in range(6):
            self.row['seq'] += 1
            self.tick()
        self.assertEqual(self.g.stage, 'stopped')
        self.assertIn('no stable grout line', self.g.result['reason'])

    def test_clearance_no_progress_and_stale_phone_abort(self):
        self.start_clearance()
        self.f.now += 3.1
        self.tick()
        self.assertIn('no wheel progress during threshold clearance', self.g.result['reason'])

    def test_clearance_phone_expiry_does_not_continue_blindly(self):
        self.start_clearance()
        self.f.now += 1
        self.g.tick(self.f.state)
        self.assertEqual(self.g.stage, 'stopped')

    def test_line_end_brakes_outbound_then_reverses_without_docking(self):
        self.begin_return()
        self.assertGreater(self.g.last['velocity_mm_s'], 0)
        self.f.robot.execute.assert_any_call('_change_mode', mode=2)
        self.assertFalse(any(c.args[0] == 'seek_dock' for c in self.f.robot.execute.call_args_list))
        self.f.health['bump_count'] += 1
        self.tick(delta=10)
        self.assertEqual(self.m._mode, 'idle')

    def test_explicit_return_resumes_stopped_trace_and_keeps_new_impact_guard(self):
        self.begin_return()
        self.f.health['bump_count'] += 1
        self.tick(delta=10)
        pose = dict(self.g.pose)
        self.assertEqual(self.m._mode, 'idle')
        self.m.return_to_tag15()
        recovery = self.m.gridrunner
        self.assertEqual(recovery.kind, 'return_to_tag15')
        self.assertEqual(recovery.pose, pose)
        self.assertEqual(recovery.stage, 'scanning')
        recovery.tick(self.f.state)
        self.f.health['bump_count'] += 1
        recovery.tick(self.f.state)
        self.assertEqual(self.m._mode, 'idle')

    def test_small_bump_does_not_turn_outbound_or_stop_return(self):
        self.tick()
        self.f.health.update(bump_count=1,last_bump_peak_mm_s2=3804)
        self.tick(delta=-5)
        self.assertEqual(self.g.stage,'driving')
        self.assertEqual(self.g.bump_policy.events[-1]['action'],'record-only')
        self.f.health['last_bump_peak_mm_s2']=6000
        self.tick(delta=-5)
        self.assertEqual(self.g.stage,'stopped')

    def test_return_loss_grace_and_last_good_steer_before_handoff(self):
        self.begin_return()
        self.row.update(flags=2,reason=1,confidence=0)
        # Flicker for 1-2 s must not hand off yet; last-good line heading
        # is reused for steering during the first 1.5 s of loss.
        for _ in range(5):
            self.tick(delta=5)
            self.assertIs(self.m.gridrunner,self.g)
            self.assertEqual(self.g.stage,'return')
            self.assertEqual(self.g.last['line_correction'], self.g.last_good_line['correction'])
        for _ in range(10):
            self.tick(delta=5)
            self.assertIs(self.m.gridrunner,self.g)
            self.assertEqual(self.g.stage,'return')
        self.assertLessEqual(self.g.last['last_good_line_age_s'], 3.1)
        # Past the 3 s grace the scan-free return aborts.
        for _ in range(10):
            self.tick(delta=5)
            if self.g.stage == 'stopped': break
        self.assertEqual(self.g.stage, 'stopped')
        self.assertIn('scan-free', self.g.result['reason'])

    def test_lost_return_line_aborts_scan_free_without_handoff(self):
        self.begin_return()
        self.row.update(flags=2,reason=1,confidence=0)
        for _ in range(20):
            self.tick(delta=5)
            if self.g.stage == 'stopped': break
        self.assertEqual(self.g.stage, 'stopped')
        self.assertIn('scan-free', self.g.result['reason'])
        self.assertIs(self.m.gridrunner, self.g)

    def test_visible_line_controls_final_approach_even_with_wrong_tag_heading(self):
        self.begin_return()
        self.g.stage='approach';self.g.final_fix=self.g.tag_fix_applied=True
        self.g.last_tag_distance=self.f.state['distance'];self.g.checkpoints=[]
        self.g.pose.update(x_mm=self.g.tag['x']-300,y_mm=self.g.tag['y']-26,heading_rad=.2)
        self.row.update(offset_mm=self.g.target_offset_mm,line_angle_rad=0,confidence=1)
        self.tick()
        self.assertEqual(self.g.last['steering_mode'],'straight')
        self.assertEqual(self.g.last['correction'],0)
        self.assertEqual(self.g.last['heading_error_rad'],0)

    def test_return_uses_observed_grout_before_first_tag_fix(self):
        self.begin_return()
        self.row.update(offset_mm=-50, line_angle_rad=.02)
        self.tick(delta=10)
        expected = grid_correction(-50, .02, 1, self.row['gain']*2,
                                   self.row['correction_limit'], self.row['lens_left_mm'])
        self.assertAlmostEqual(self.g.last['correction'], expected)
        self.assertFalse(self.g.last['tag_fix_applied'])

    def test_accepted_tag_pose_updates_position_without_biasing_visible_line(self):
        self.begin_return()
        self.g._scan(2000)
        fix = dict(self.g.pose, heading_rad=.1, accepted_tag_ids=(('tag16h5',15),))
        self.g._tag_fix = lambda detections: fix
        self.m.camera.latest_detections = ()
        self.m.camera.last_detection_time = self.g.scan_wall+.01
        self.tick()
        self.assertAlmostEqual(self.g.pose['heading_rad'], .1)
        self.assertTrue(self.g.tag_fix_applied)
        self.tick(delta=5)
        self.assertLess(self.g.last['tag_correction'], 0)
        self.assertAlmostEqual(self.g.last['correction'],
            self.g.last['line_correction'])

    def test_scan_free_return_needs_no_checkpoint_scan(self):
        self.begin_return()
        self.m.camera.request_scan.reset_mock()
        while self.g._range(self.f.state) > 510:
            self.tick(delta=min(100, self.g._range(self.f.state) - 500))
        if self.g.stage == 'return':
            self.tick(delta=5)
        self.assertEqual(self.g.stage, 'approach')
        self.m.camera.request_scan.assert_not_called()

    def test_final_scan_required_even_when_checkpoint_list_is_empty(self):
        self.begin_return()
        self.g.checkpoints = []
        self.g.pose.update(x_mm=self.g.tag['x']-450, y_mm=self.g.tag['y'])
        self.tick(delta=5)
        self.assertEqual(self.g.stage, 'approach')

    def test_return_line_loss_is_bounded_scan_free(self):
        self.begin_return()
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick(delta=5)
        self.f.now += 31
        self.f.state['distance'] += 5
        self.refresh()
        self.g.tick(self.f.state)
        self.assertEqual(self.g.stage, 'stopped')
        self.assertIn('line absent', self.g.result['reason'])

    def test_generic_phone_bump_indicator_does_not_replay_old_events_after_mode_change(self):
        self.m._baseline_phone_bumps()
        self.f.robot.set_bump_indicator.reset_mock()
        self.f.health['bump_count'] += 1
        self.m._observe_phone_bumps()
        self.f.robot.set_bump_indicator.assert_called_once_with(True)
        self.m.set_mode('idle')
        self.f.robot.set_bump_indicator.reset_mock()
        self.m._observe_phone_bumps()
        self.f.robot.set_bump_indicator.assert_not_called()
        self.f.health['bump_count'] += 1
        self.m._observe_phone_bumps()
        self.f.robot.set_bump_indicator.assert_called_once_with(True)

    def test_scan_free_return_still_allows_explicit_tag_return(self):
        self.begin_return()
        while self.g._range(self.f.state) > 510:
            self.tick(delta=min(100,self.g._range(self.f.state)-500))
        if self.g.stage == 'return':
            self.tick(delta=5)
        self.assertEqual(self.g.stage, 'approach')
        self.g.abort('test stop')
        self.assertEqual(self.m._mode, 'idle')
        self.refresh()
        self.m.return_to_tag15()
        self.assertEqual(self.m.gridrunner.stage, 'scanning')
        self.assertEqual(self.m.gridrunner.kind, 'return_to_tag15')
        self.assertFalse(self.m.gridrunner.final_fix)

    def test_return_queues_a_fresh_fix_while_camera_scan_is_active(self):
        self.begin_return()
        self.g.abort('test scan interruption')
        self.m._scan_active = True
        self.m.return_to_tag15()
        self.assertEqual(self.m.gridrunner.stage, 'scanning')
        self.assertEqual(self.m.gridrunner.kind, 'return_to_tag15')

    def test_phone_bump_latches_indicator_and_mode_change_clears_it(self):
        self.tick()
        self.f.robot.set_bump_indicator.reset_mock()
        self.f.health['bump_count'] += 1
        self.tick(delta=-5)
        self.f.robot.set_bump_indicator.assert_any_call(True)
        self.m.set_mode('idle')
        self.f.robot.set_bump_indicator.assert_called_with(False)

    def test_explicit_return_accepts_missing_trace_and_changed_phone(self):
        self.m.set_mode('idle')
        self.m.return_to_tag15()
        self.assertEqual(self.m.gridrunner.kind, 'return_to_tag15')
        self.m.set_mode('gridrunner')
        self.g = self.m.gridrunner
        self.begin_return()
        self.g.abort('test stop')
        self.row['session'] += 1
        self.m.return_to_tag15()
        self.assertEqual(self.m.gridrunner.kind, 'return_to_tag15')
        self.assertEqual(self.m.gridrunner.stage, 'scanning')

    def test_scan_free_return_completes_on_bumper_near_tag(self):
        self.begin_return()
        self.m.camera.request_scan.reset_mock()
        while self.g._range(self.f.state) > 200:
            self.tick(delta=min(100, max(0, self.g._range(self.f.state) - 174)))
            if self.g.result is not None:
                break
        self.assertEqual(self.g.stage, 'approach')
        self.m.camera.request_scan.assert_not_called()
        self.f.state['sensors'].bumps_and_wheel_drops.bump_left = True
        self.tick()
        self.assertEqual(self.g.result['status'], 'complete')
        self.assertEqual(self.m._mode, 'idle')

    def test_missing_final_tag_scan_free_overtravel_aborts(self):
        self.begin_return()
        while self.g._range(self.f.state) > 200:
            self.tick(delta=min(100, max(0, self.g._range(self.f.state) - 174)))
            if self.g.result is not None:
                break
        # No contact at all: the bounded travel guard must stop the run.
        for _ in range(7):
            self.tick(delta=100)
            if self.g.stage == 'stopped':
                break
        self.assertEqual(self.g.stage, 'stopped')
        self.assertIn('approach', self.g.result['reason'])

    def test_unexpected_front_contact_aborts_instead_of_claiming_target(self):
        self.begin_return()
        self.f.state['sensors'].bumps_and_wheel_drops.bump_right = True
        self.tick()
        self.assertEqual(self.g.result['status'], 'stopped')

    def test_final_approach_without_contact_stops_at_bounded_overtravel(self):
        self.begin_return()
        self.g.stage = 'approach'
        self.g.checkpoints = []
        self.g.final_fix = True
        self.g.last_tag_distance = self.f.state['distance']
        self.g.pose = dict(x_mm=self.g.tag['x']-120,y_mm=self.g.tag['y'],heading_rad=0)
        self.tick(delta=10)
        self.assertEqual(self.g.stage, 'stopped')
        self.assertIn('approach', self.g.result['reason'])

    def test_scan_timeout_stops_without_driving(self):
        self.begin_return()
        self.g._scan(2000)
        self.f.now += 21
        self.tick()
        self.assertIn('scan timeout', self.g.result['reason'])

    def test_stale_health_while_line_is_lost_still_stops(self):
        self.tick()
        self.row.update(flags=2, reason=1, confidence=0)
        self.tick(delta=-5)
        self.f.health['received_monotonic'] -= 1
        self.g.tick(self.f.state)
        self.assertEqual(self.m._mode, 'idle')

    def test_return_pose_error_cannot_steer_away_from_visible_grout(self):
        self.begin_return()
        self.g.pose['y_mm'] += 100
        self.g.tag_fix_applied = True
        self.tick(delta=10)
        self.assertAlmostEqual(self.g.last['correction'], self.g.last['line_correction'])

    def test_tag_solver_accepts_2m_checkpoint_without_relaxing_normal_gate(self):
        from roomberry_localization import AprilTagLocalizer as L
        config = json.loads((Path(__file__).resolve().parents[2]/'autonomy.json').read_text())
        landmark = next(r for r in config['landmarks'] if r['id'] == 15)
        world_tag = landmark['world_from_tag']
        self.m.localizer = L({('tag16h5',15):world_tag}, config['camera_from_robot'],
                            max_tag_distance_m_by_key={('tag16h5',15):1.2})
        world_robot = [[1,0,0,world_tag[0][3]-2],[0,1,0,world_tag[1][3]],
                       [0,0,1,0],[0,0,0,1]]
        camera_tag = L._multiply(config['camera_from_robot'], L._multiply(L._inverse(world_robot), world_tag))
        detection = dict(family='tag16h5', id=15, hamming=0, decision_margin=100,
            tag_pose_camera=dict(rotation=[r[:3] for r in camera_tag[:3]],
                                 translation_m=[r[3] for r in camera_tag[:3]], error=0))
        self.assertIsNone(self.m.localizer.update([detection],0,0))
        fix = self.g._tag_fix([detection])
        self.assertTrue(fix['accepted_tag_ids'])
        self.assertAlmostEqual(fix['x_mm'], (world_tag[0][3]-2)*1000)
        self.assertEqual(self.m.localizer.max_tag_distance_m_by_key[('tag16h5',15)], 1.2)

    def test_differential_drive_out_and_back_with_real_tag_geometry_and_line_losses(self):
        import math
        from roomberry_localization import AprilTagLocalizer as L
        config = json.loads((Path(__file__).resolve().parents[2]/'autonomy.json').read_text())
        landmark = next(r for r in config['landmarks'] if r['id'] == 15)
        tag = landmark['world_from_tag']
        self.m.discovery_landmarks = {15:landmark}
        self.m.localizer = L({('tag16h5',15):tag},config['camera_from_robot'])
        self.row['lens_left_mm'] = 26
        x, y, heading = tag[0][3]*1000-174, tag[1][3]*1000-26+20, .015
        threshold_x = x-4625
        bumped = False
        slowed = False
        for step in range(3000):
            self.f.now += .2
            self.refresh()
            self.row['seq'] += 2
            self.row.update(flags=3,reason=0,confidence=1,
                            offset_mm=(tag[1][3]*1000-y)*math.cos(heading),
                            line_angle_rad=-heading)
            # One intermediate loss and the final stripe disappearing before threshold.
            if (60 <= step < 62) or (not bumped and x < threshold_x+150):
                self.row.update(flags=2, reason=1, confidence=0)
            if self.g.stage in ('turnaround','threshold_clearance','return','approach'):
                bumped = True
            if self.g.stage == 'scanning':
                self.assertTrue(self.m.scan_pause())
                self.g.tick(self.f.state, scan_active=True)
                self.assertEqual(self.g.stage, 'scanning')
                world_robot = [[math.cos(heading),-math.sin(heading),0,x/1000],
                    [math.sin(heading),math.cos(heading),0,y/1000],[0,0,1,0],[0,0,0,1]]
                camera_tag = L._multiply(config['camera_from_robot'], L._multiply(L._inverse(world_robot),tag))
                self.m.camera.last_detection_time = self.g.scan_wall+.01
                self.m.camera.latest_detections = [dict(family='tag16h5',id=15,hamming=0,decision_margin=100,
                    tag_pose_camera=dict(rotation=[r[:3] for r in camera_tag[:3]],
                        translation_m=[r[3] for r in camera_tag[:3]],error=0))]
                self.m.scan_complete()
            if bumped and tag[0][3]*1000-x <= 174:
                self.f.state['sensors'].bumps_and_wheel_drops.bump_left = True
            previous_sample = self.g.last
            self.g.tick(self.f.state)
            if self.g.result is not None:
                break
            if self.g.stage not in ('driving','threshold_clearance','return','approach') or self.g.last is previous_sample:
                continue
            speed = self.g.last['velocity_mm_s']
            left, right = self.g.last['left_velocity_mm_s'], self.g.last['right_velocity_mm_s']
            slowed |= speed == 0
            # Persistent small drivetrain yaw bias; scans measure the real pose.
            yaw = ((right-left)/235+.0005)*.2
            dx = (left+right)/2*.2
            x += dx*math.cos(heading+yaw/2)
            y += dx*math.sin(heading+yaw/2)
            heading += yaw
            self.f.state['distance'] += dx
            self.f.state['angle'] += math.degrees(yaw)
        self.assertTrue(slowed)
        self.assertEqual(self.g.result['status'], 'complete', self.g.result)
        self.assertEqual(self.g.records, [])  # scan-free: no checkpoint scans
        self.assertLess(abs(y-(tag[1][3]*1000-26)), 40)

    def test_physical_hazards_stale_sensors_and_watchdog(self):
        for problem in ('bumper','cliff','stale','epoch','battery','distance','no_progress'):
            with self.subTest(problem=problem):
                self.f.state.update(age=0,safety_latched=False,odometry_epoch=1,battery_status='normal',distance=0)
                sensors=self.f.state['sensors'];sensors.bumps_and_wheel_drops.bump_left=False;sensors.cliff_left_sensor=False
                self.m.set_mode('gridrunner');self.g=self.m.gridrunner;self.row.update(flags=3,session=11,direction=-1,gain=2);self.f.health['bump_count']=0
                self.tick()
                if problem=='bumper':sensors.bumps_and_wheel_drops.bump_left=True
                elif problem=='cliff':sensors.cliff_left_sensor=True
                elif problem=='stale':self.f.state['age']=1
                elif problem=='epoch':self.f.state['odometry_epoch']=2
                elif problem=='battery':self.f.state['battery_status']='low'
                elif problem=='distance':self.f.state['distance']=-5001
                elif problem=='no_progress':self.f.now+=4
                self.refresh();self.g.tick(self.f.state)
                self.assertEqual(self.m._mode,'idle')

    def test_clock_grid_display_cancel_and_passive_restore(self):
        self.m.set_mode('idle');self.f.state['clock_button']=True
        self.assertTrue(self.m._handle_clock(self.f.state));self.assertEqual(self.m._mode,'gridrunner')
        display=SimpleNamespace(_drive_display=None)
        RobotCommandArbiter.set_drive_display(display,'gridrunner',scanning=True)
        self.assertEqual(display._drive_display,'GRID')
        self.f.state['clock_button']=False;self.m._handle_clock(self.f.state)
        self.f.state['clock_button']=True;self.m._handle_clock(self.f.state)
        self.assertEqual(self.m._mode,'idle')
        from irobot.openinterface.constants import MODES
        self.f.robot.execute.assert_any_call('_change_mode',mode=MODES.PASSIVE)

    def test_oi_stop_cannot_be_rearmed_by_clock(self):
        self.m.set_mode('idle');self.f.state.update(oi_stopped=True,clock_button=True)
        self.assertFalse(self.m._handle_clock(self.f.state));self.assertEqual(self.m._mode,'idle')

if __name__=='__main__':unittest.main()
