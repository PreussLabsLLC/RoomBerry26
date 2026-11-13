"""Map library workflow, persistence, motion exclusion and HTTP contracts."""
# @(#)roomberry_trek_maps_test.py 3.2.maps.3 2026/11/10 11:14:37
import io
import json
from pathlib import Path
import tempfile
from threading import Event, RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from roomberry import RoomberryHandler
from roomberry_trek_maps import TrekMapManager
from roomberry_trek_survey import TrekSurveyController
from roomberry_mission import RoomberryMission

FIRST = '00000000-0000-0000-0000-000000000001'
SECOND = '00000000-0000-0000-0000-000000000002'


class MapTests(unittest.TestCase):
    def setUp(self):
        self.maps = [dict(id=FIRST, name='kitchen-old', created=1, mapping='mapped', revision=1, features=20, bytes=100)]
        self.phone = dict(running=True, mode='survey', map_id='', can_amend=True)
        self.calls = []
        self.survey = TrekSurveyController(b'key', 5010, Mock(), command=self.command, seed_map_id=FIRST)
        self.mission = SimpleNamespace(_coord_lock=RLock(), _manual_step=None,
                                      _manual_motion_active=lambda: False,
                                      status_snapshot=lambda: dict(mission_mode='idle'))
        self.manager = TrekMapManager(self.survey, self.mission)

    def command(self, command, **args):
        self.calls.append((command, args))
        result = {}
        if command == 'STATUS':
            result = dict(self.phone, capabilities=['survey_resume_v1', 'map_library_v1'],
                          maps=[m for m in self.maps if not args.get('map_id') or m['id'] == args['map_id']])
        elif command == 'MAP_LIST':
            result = dict(maps=self.maps[args['offset']:args['offset']+1], next_offset=args['offset']+1 if args['offset']+1 < len(self.maps) else None,
                          inventory_revision='stable', inventory_errors=0, storage_bytes=100)
        elif command == 'SESSION_STOP': self.phone['running'] = False
        elif command == 'SURVEY_START': self.phone.update(running=True, map_id=args.get('map_id', ''))
        elif command == 'SURVEY_SAVE':
            self.maps.append(dict(self.maps[0], id=SECOND, name=args['name'], parent_map_id=self.phone['map_id']))
            result = dict(map_id=SECOND)
        elif command == 'MAP_RENAME':
            next(m for m in self.maps if m['id'] == args['map_id'])['name'] = args['name']
        elif command == 'MAP_DELETE': self.maps[:] = [m for m in self.maps if m['id'] != args['map_id']]
        return dict(status='completed', detail=json.dumps(result))

    def run_job(self, action, **args):
        job = self.manager.submit(dict(action=action, **args))
        self.manager._thread.join(2)
        state = self.manager.snapshot()
        self.assertFalse(state['busy'])
        self.assertEqual(state['job']['id'], job['id'])
        return state['job']

    def test_fresh_save_select_resume_and_rename(self):
        for action, args in [('fresh', {}), ('save', dict(name='kitchen-daylight')), ('select', dict(map_id=SECOND)),
                             ('resume', dict(map_id=SECOND)), ('rename', dict(map_id=SECOND, name='<daylight> & kitchen'))]:
            self.assertEqual(self.run_job(action, **args)['status'], 'completed')
        self.assertEqual(self.survey.selected_map_id, SECOND)
        self.assertEqual(self.phone['map_id'], SECOND)
        self.assertEqual(self.maps[1]['name'], '<daylight> & kitchen')
        self.assertIn(('SURVEY_START', {}), self.calls)
        self.assertIn(('SURVEY_START', dict(map_id=SECOND)), self.calls)

    def test_existing_fresh_survey_survives_real_steering_pad_and_idle(self):
        from roomberry_manual_step_test import ManualStepTest
        steering = ManualStepTest('test_four_directions_are_measured_and_braked')
        steering.setUp()
        self.addCleanup(steering.doCleanups)
        self.manager.mission = steering.m
        steering.m.on_mode_change = self.survey.mode_changed
        steering.m.before_mode_change = self.manager.guard_mission
        self.assertEqual(self.run_job('keep')['status'], 'completed')
        before = list(self.calls)
        for direction in ('left', 'right', 'forward', 'backward'):
            result = steering.m.manual_step(direction)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(steering.wheels, (0, 0))
            self.assertEqual(steering.m._mode, 'idle')
        self.assertEqual(self.calls, before)
        self.assertTrue(self.survey._queue.empty())
        self.assertIsNotNone(self.manager.snapshot()['operator_survey'])

    def test_steering_never_restarts_local_phone_survey_without_keep(self):
        from roomberry_manual_step_test import ManualStepTest
        steering = ManualStepTest('test_four_directions_are_measured_and_braked')
        steering.setUp()
        self.addCleanup(steering.doCleanups)
        steering.m.on_mode_change = self.survey.mode_changed
        steering.m.before_mode_change = self.manager.guard_mission
        self.assertIsNone(self.survey.snapshot()['operator_survey'])
        for direction in ('left', 'right', 'forward', 'backward'):
            self.assertEqual(steering.m.manual_step(direction)['status'], 'complete')
            self.assertEqual(steering.wheels, (0, 0))
            self.assertEqual(steering.m._mode, 'idle')
        # Also cover rapid repeated mode notifications, beyond queue capacity.
        for _ in range(100):
            self.survey.mode_changed('remote_control')
            self.survey.mode_changed('idle')
        self.assertEqual(self.calls, [])
        self.assertTrue(self.survey._queue.empty())
        self.assertFalse(self.survey._active)

    def test_manual_takeover_ends_only_the_existing_automatic_survey(self):
        for mode in ('wall', 'remote_control', 'idle', 'remote_control', 'idle'):
            self.survey.mode_changed(mode)
        self.assertEqual(self.survey._queue.qsize(), 2)
        self.assertEqual(self.survey._queue.get_nowait()[0], 'start')
        self.assertEqual(self.survey._queue.get_nowait()[0], 'save')
        self.assertFalse(self.survey._active)

    def test_unsaved_survey_blocks_wall_until_saved_or_explicitly_stopped(self):
        self.run_job('fresh')
        for mode in ('wall', 'gridrunner', 'discovery', 'clean'):
            with self.assertRaisesRegex(RuntimeError, 'Save the current phone survey'):
                self.manager.guard_mission(mode)
        for mode in ('idle', 'remote_control'): self.manager.guard_mission(mode)
        self.run_job('save', name='kitchen-daylight')
        self.manager.guard_mission('wall')
        self.run_job('select', map_id=SECOND)
        self.survey.mode_changed('wall')
        self.assertIsNone(self.survey.snapshot()['operator_survey'])
        self.assertEqual(self.survey._queue.get_nowait()[0], 'start')
        self.survey._start_survey('kitchen-today')
        self.assertIn(('SURVEY_START', dict(map_id=SECOND)), self.calls)

    def test_stop_releases_survey_and_keep_rejects_stopped_or_navigator(self):
        self.run_job('fresh')
        self.run_job('stop')
        self.assertIsNone(self.manager.snapshot()['operator_survey'])
        self.manager.guard_mission('wall')
        self.assertEqual(self.run_job('keep')['status'], 'failed')
        self.phone.update(running=True, mode='navigate')
        self.assertEqual(self.run_job('keep')['status'], 'failed')

    def test_selected_map_overrides_seed_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'selection.json'
            self.survey.selection_path = path
            self.maps.append(dict(self.maps[0], id=SECOND, name='unrelated-room'))
            self.run_job('select', map_id=SECOND)
            c = TrekSurveyController(b'key', 5010, Mock(), command=self.command, seed_map_id=FIRST, selection_path=path)
            c._start_survey('kitchen-today')
            self.assertEqual(c.snapshot()['parent_map_id'], SECOND)
            self.assertIn(('STATUS', dict(map_id=SECOND)), self.calls)
            self.assertIn(('SURVEY_START', dict(map_id=SECOND)), self.calls)
            self.run_job('select', map_id=None)
            self.assertIsNone(json.loads(path.read_text())['map_id'])

    def test_missing_selected_map_does_not_fall_back_to_seed_or_fresh(self):
        self.survey.select_map(SECOND)
        self.survey._start_survey('kitchen-today')
        self.assertEqual(self.survey.snapshot()['status'], 'failed')
        self.assertIn('missing', self.survey.snapshot()['error'])
        self.assertFalse(any(c == 'SURVEY_START' for c, _ in self.calls))

    def test_corrupt_selection_blocks_start_but_can_be_replaced_from_console(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'selection.json'
            path.write_text('broken json')
            c = TrekSurveyController(b'key', 5010, Mock(), command=self.command, selection_path=path)
            c._start_survey('kitchen-today')
            self.assertEqual(c.snapshot()['status'], 'failed')
            self.assertIn('unreadable', c.snapshot()['selection']['error'])
            self.assertEqual(self.calls, [])
            c.select_map(FIRST)
            self.assertEqual(c.snapshot()['selection']['error'], '')
            self.assertEqual(json.loads(path.read_text())['map_id'], FIRST)

    def test_delete_refuses_effective_mission_map_and_active_map(self):
        job = self.run_job('delete', map_id=FIRST, confirm=True)
        self.assertIn('mission', job['detail'])
        self.maps.append(dict(self.maps[0], id=SECOND))
        self.survey.select_map(SECOND)
        self.phone.update(running=True, map_id=FIRST)
        self.assertIn('Stop the phone', self.run_job('delete', map_id=FIRST, confirm=True)['detail'])
        self.run_job('stop')
        self.assertEqual(self.run_job('delete', map_id=FIRST, confirm=True)['status'], 'completed')
        self.assertEqual([m['id'] for m in self.maps], [SECOND])

    def test_no_changes_during_mission_or_pending_save(self):
        self.mission.status_snapshot=lambda: dict(mission_mode='wall')
        with self.assertRaises(RuntimeError): self.manager.submit(dict(action='fresh'))
        self.mission.status_snapshot=lambda: dict(mission_mode='idle')
        self.survey._queue.put(('save', 'kitchen'))
        with self.assertRaises(RuntimeError): self.manager.submit(dict(action='select', map_id=FIRST))
        self.assertEqual(self.calls, [])

    def test_busy_mutation_prevents_mission_before_any_robot_commands(self):
        entered, release = Event(), Event()
        original = self.survey.command
        def blocked(*args, **kwargs):
            entered.set(); release.wait(2); return original(*args, **kwargs)
        self.survey.command = blocked
        self.manager.submit(dict(action='fresh'))
        self.assertTrue(entered.wait(1))
        robot = Mock()
        mission = RoomberryMission(robot, Mock(), Mock(), Mock(), Mock(), Mock())
        mission.before_mode_change = self.manager.guard_mission
        try:
            with self.assertRaises(RuntimeError): mission.set_mode('remote_control')
            self.assertEqual(robot.mock_calls, [])
            with self.assertRaises(RuntimeError): self.manager.submit(dict(action='stop'))
            self.manager.guard_mission('idle')  # Stop always remains available.
        finally: release.set(); self.manager._thread.join(2)

    def test_old_app_and_uncertain_save_not_replayed(self):
        self.survey.command = lambda *a, **k: dict(status='completed', detail='{"capabilities": []}')
        self.assertIn('Install', self.run_job('fresh')['detail'])
        self.survey.command = lambda c, **kw: dict(status='unknown', detail='lost response') if c == 'SURVEY_SAVE' else self.command(c, **kw)
        self.assertIn('lost response', self.run_job('save', name='kitchen')['detail'])
        self.assertFalse(any(c == 'SURVEY_START' for c, _ in self.calls))

    def test_validation_and_cached_get_have_no_side_effects(self):
        for body in [[], {}, dict(action=[]), dict(action={}), dict(action='delete', map_id=FIRST), dict(action='resume', map_id='bad'),
                     dict(action='save', name=' '), dict(action='select', map_id=FIRST, extra=True)]:
            with self.assertRaises(ValueError): TrekMapManager.validate(body)
        handler = RoomberryHandler.__new__(RoomberryHandler)
        handler.server = SimpleNamespace(trek_maps=self.manager)
        handler.wfile = io.BytesIO()
        for name in ('send_response', 'send_header', 'end_headers'): setattr(handler, name, Mock())
        handler.path = '/roomtrek/maps.json'
        self.assertTrue(handler._serve_vision())
        self.assertTrue(json.loads(handler.wfile.getvalue())['enabled'])
        self.assertEqual(self.calls, [])
        data = json.dumps(dict(action='refresh')).encode()
        handler.rfile = io.BytesIO(data)
        handler.headers = {'Content-Type':'application/json', 'Content-Length':str(len(data))}
        handler.path = '/roomtrek/maps'
        handler.do_POST()
        handler.send_response.assert_called_with(202)
        self.manager._thread.join(2)


if __name__ == '__main__': unittest.main()
