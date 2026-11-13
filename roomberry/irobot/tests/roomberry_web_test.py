# @(#)roomberry_web_test.py 3.2.imu.1 2026/11/12 15:16:02
"""Local console routes, precise JSON identities and safe mission command routing."""
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from roomberry import RoomberryHandler
from roomberry_navlink import NavLinkReceiver, decode_packet
from roomberry_web import command_index, groundhog_snapshot


class LocalConsoleTest(unittest.TestCase):
    def test_restart_oi_uses_coordinator_and_button_is_present(self):
        self.assertTrue(self.handler._mission_operation('restart_oi', {}))
        self.handler.server.mission.restart_oi.assert_called_once_with()
        self.handler.server.roomba_control.execute.assert_not_called()
        self.handler.path = '/'
        self.handler.do_GET()
        self.assertIn('op=restart_oi', self.handler.wfile.getvalue().decode())

    def test_steering_pad_commands_use_measured_mission_steps(self):
        for direction in ('left','right','left_15','right_15','left_30','right_30','forward','backward','forward_500','backward_500'):
            self.assertTrue(self.handler._mission_operation('step_'+direction, {}))
            self.handler.server.mission.manual_step.assert_called_with(direction)
        self.handler.server.roomba_control.execute.assert_not_called()
        with self.assertRaises(ValueError):
            self.handler._mission_operation('step_forward', {'distance': 500})

    def test_wall_controls_route_to_coordinator_and_dashboard(self):
        for operation, method in (('wall', 'start_wall'), ('wall_capture_100mm', 'capture_wall_clearance')):
            self.assertTrue(self.handler._mission_operation(operation, {}))
            getattr(self.handler.server.mission, method).assert_called_once_with()
            self.assertEqual(any(c['name'] == operation for c in command_index()['commands']), operation == 'wall')
            with self.assertRaises(ValueError):
                self.handler._mission_operation(operation, {'velocity': 500})
        self.handler.server.roomba_control.execute.assert_not_called()
        self.handler.path = '/'
        self.handler.do_GET()
        page = self.handler.wfile.getvalue().decode()
        self.assertIn('op=wall"', page)
        self.assertNotIn('op=wall_capture_100mm', page)
        self.assertIn('30 right light-bumper units', page)

    def test_return_to_tag15_routes_to_coordinator(self):
        self.assertTrue(self.handler._mission_operation('return_to_tag15', {}))
        self.handler.server.mission.return_to_tag15.assert_called_once_with()
        self.handler.server.roomba_control.execute.assert_not_called()
        self.assertTrue(any(c['name'] == 'return_to_tag15' for c in command_index()['commands']))

    def test_reset_uses_driver_path_and_run_modes_use_mission(self):
        self.assertFalse(self.handler._mission_operation('reset', {}))
        self.handler.server.roomba_control.execute.assert_not_called()
        for mode in ('clean', 'return_to_base', 'remote_control'):
            self.assertTrue(self.handler._mission_operation(mode, {}))
            self.handler.server.mission.set_mode.assert_called_with(mode)

    def setUp(self):
        self.handler=RoomberryHandler.__new__(RoomberryHandler)
        self.handler.server=SimpleNamespace(logger=Mock(),mission=Mock(),roomba_control=Mock(),navlink=None)
        self.handler.wfile=io.BytesIO()
        for name in ('send_response','send_header','end_headers','send_error','send_reply','send_error_reply'):
            setattr(self.handler,name,Mock())

    def test_index_and_allowlisted_assets_are_read_only(self):
        for route,fragment in (('/','GroundHog'),('/index.html','Command index'),('/ui/','Recent scans'),
                               ('/ui/style.css','--green'),('/ui/app.js','renderCommands')):
            with self.subTest(route=route):
                self.handler.wfile=io.BytesIO();self.handler.path=route
                self.handler.do_GET()
                self.assertIn(fragment,self.handler.wfile.getvalue().decode())
        self.handler.server.roomba_control.execute.assert_not_called()
        self.handler.server.mission.set_mode.assert_not_called()
        self.handler.server.mission.start_calibration.assert_not_called()
        self.handler.path='/ui/../autonomy.json'
        self.assertFalse(self.handler._serve_vision())

    def test_command_index_matches_actual_driver_and_mission_aliases(self):
        catalog=command_index()
        commands={c['name']:c for c in catalog['commands']}
        self.assertIn('cal',commands['calibrate']['aliases'])
        self.assertIn('drive_direct',commands)
        self.assertEqual([p['name'] for p in commands['drive_direct']['parameters']],['right_velocity','left_velocity'])
        self.assertNotIn('left_encoder_counts',commands)
        self.assertNotIn('auto_wake',commands)
        self.assertIn('request_scan',commands)
        self.assertAlmostEqual(catalog['calibration_acceptance']['heading_rad'],.3)
        acceptance=catalog['calibration_acceptance']
        self.assertEqual(acceptance['endpoint_tolerance_mm'],15)
        self.assertFalse(acceptance['scans'])
        self.assertTrue(acceptance['manual_start_alignment'])
        self.assertNotIn('start_gap_mm',acceptance)
        self.handler.path='/commands.json';self.handler.do_GET()
        self.assertEqual(json.loads(self.handler.wfile.getvalue()),catalog)
        self.handler.server.roomba_control.execute.assert_not_called()

    def test_groundhog_disabled_endpoint(self):
        self.handler.path='/groundhog.json';self.handler.do_GET()
        payload=json.loads(self.handler.wfile.getvalue())
        self.assertFalse(payload['enabled']);self.assertIsNone(payload['motion'])

    def test_groundhog_json_handles_bytes_staleness_and_64_bit_tokens(self):
        from roomberry_groundhog_test import ground
        from roomberry_health_test import health
        from roomberry_compass_test import compass
        receiver=NavLinkReceiver()
        for data in (ground(session=18446744073709551615),health(),compass()):
            receiver._observe(decode_packet(data),100)
        payload=groundhog_snapshot(receiver,now=100.1)
        self.assertEqual(payload['motion']['session'],'18446744073709551615')
        self.assertNotIn('magic',payload['motion']);self.assertNotIn('reserved',payload['health'])
        self.assertNotIn('padding',payload['compass'])
        self.assertTrue(payload['motion']['usable']);self.assertTrue(payload['compass']['usable'])
        json.dumps(payload,allow_nan=False)
        stale=groundhog_snapshot(receiver,now=110)
        self.assertFalse(stale['motion']['usable']);self.assertFalse(stale['health']['fresh'])
        self.assertFalse(stale['compass']['usable'])
        self.handler.server.navlink=receiver
        self.handler.path='/groundhog.json';self.handler.do_GET()
        json.loads(self.handler.wfile.getvalue())
        self.handler.server.roomba_control.execute.assert_not_called()

    def test_snapshot_freshness_uses_time_after_each_receive_snapshot(self):
        def row(t,flags): return dict(received_monotonic=t,flags=flags,session=1,calibration=2)
        receiver=SimpleNamespace(received=3,rejected=0,
            latest_ground_observation=lambda:row(100,7),
            latest_health_observation=lambda:row(101,1),
            latest_compass_observation=lambda:row(102,1))
        with patch('roomberry_web.monotonic',side_effect=[100,101,102]):
            payload=groundhog_snapshot(receiver)
        self.assertTrue(all(payload[k]['fresh'] for k in ('motion','health','compass')))

    def test_stop_cancels_autonomy_and_always_brakes(self):
        for operation in ('stop','emergency_stop'):
            self.handler.server.mission.reset_mock();self.handler.server.roomba_control.reset_mock()
            self.handler.path='/roomba/?op='+operation;self.handler.do_GET()
            self.handler.server.mission.set_mode.assert_called_once_with('idle')
            self.handler.server.roomba_control.execute.assert_called_once_with(operation)
        self.handler.server.mission=None
        self.handler.path='/roomba/?op=stop';self.handler.do_GET()
        self.handler.server.roomba_control.execute.assert_called_with('stop')

    def test_stop_brakes_before_mode_change_feedback_and_discovery_respects_oi_stop(self):
        order=Mock()
        order.attach_mock(self.handler.server.roomba_control,'control')
        order.attach_mock(self.handler.server.mission,'mission')
        self.handler.path='/roomba/?op=stop';self.handler.do_GET()
        self.assertEqual(order.mock_calls[0].args,('stop',))
        self.assertEqual(str(order.mock_calls[1]),"call.mission.set_mode('idle')")
        self.handler.server.roomba_control.snapshot.return_value=dict(oi_stopped=True)
        self.handler.server.mission.reset_mock()
        self.handler.path='/roomba/?op=discovery';self.handler.do_GET()
        self.handler.server.mission.set_mode.assert_not_called()
        self.handler.send_error_reply.assert_called_once()

    def test_discovery_idle_and_scan_controls(self):
        self.handler.path='/roomba/?op=discovery';self.handler.do_GET()
        self.handler.server.mission.set_mode.assert_called_with('discovery',wake_robot=False)
        self.handler.path='/roomba/?op=idle';self.handler.do_GET()
        self.handler.server.mission.set_mode.assert_called_with('idle')
        self.handler.server.roomba_control.execute.assert_called_with('stop')
        self.handler.server.camera_service=Mock()
        self.handler.path='/cam/?op=request_scan';self.handler.do_GET()
        self.handler.server.camera_service.request_scan.assert_called_once()


if __name__=='__main__':unittest.main()
