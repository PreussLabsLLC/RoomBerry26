"""Pi-owned survey start/save/stop without ARKit or robot motion."""
# @(#)roomberry_trek_survey_test.py 3.2 2026/11/09 18:53:01
import json
import unittest
from unittest.mock import Mock, MagicMock, patch
from roomberry_trek_survey import TrekSurveyController
import roomberry_mission_test


class SurveyTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.saved = False
        def command(command_name, **kwargs):
            self.calls.append((command_name, kwargs))
            if command_name == 'SURVEY_SAVE':
                self.saved = True
                return dict(status='completed',detail=json.dumps(dict(map_id='new-map')))
            return dict(status='completed', detail=json.dumps(dict(capabilities=['survey_resume_v1'], maps=[dict(id='new-map', name='kitchen-261109')] if self.saved else [])))
        self.controller = TrekSurveyController(b'1701', 5010, Mock(), command=command, date=lambda: '261109')

    def test_start_save_verify_stop_order(self):
        self.controller._start_survey('kitchen-261109')
        self.assertEqual(self.controller.snapshot()['status'], 'surveying')
        self.controller._save_survey()
        self.assertEqual([name for name, _ in self.calls], ['STATUS', 'SESSION_STOP', 'SURVEY_START', 'SURVEY_SAVE', 'STATUS', 'SESSION_STOP'])
        self.assertEqual(self.calls[3][1], dict(name='kitchen-261109'))
        self.assertEqual(self.controller.snapshot()['status'], 'saved')

    def test_mode_transitions_coalesce_and_capture_date(self):
        c=self.controller
        for mode in ('idle', 'wall', 'wall', 'discovery', 'idle', 'idle'):
            c.mode_changed(mode)
        self.assertEqual(c._queue.qsize(), 2)
        self.assertEqual(c._queue.get_nowait(), ('start', 'kitchen-261109'))
        self.assertEqual(c._queue.get_nowait()[0], 'save')

    def test_failed_start_never_reports_saved(self):
        self.controller.command = Mock(return_value=dict(status='failed', detail='App must be foreground'))
        self.controller._start_survey('kitchen-261109')
        self.controller._save_survey()
        self.assertEqual(self.controller.snapshot()['status'], 'failed')
        self.assertIsNone(self.controller._survey)
        self.controller.command.assert_called_once_with('STATUS', map_prefix='kitchen')

    def test_backgrounded_start_warns_beeps_and_does_not_start_survey(self):
        c=self.controller; c.startup_warning=Mock()
        c.command=Mock(side_effect=[dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=[]))),
                                   dict(status='failed',detail='App must be foreground')])
        c._start_survey('kitchen-261109')
        self.assertIn('open RoomTrek',c.snapshot()['warning'])
        self.assertIsNone(c._survey)
        self.assertEqual(c.command.call_count,2)
        c.startup_warning.assert_called_once_with()
        extras=c.logger.log.call_args.kwargs['extra']
        self.assertEqual(extras['speech_code'],'PHONE_BG')
        self.assertFalse(extras['speech_announce'])  # background phone cannot speak
        c.command=lambda *a,**k:dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=[])))
        c._start_survey('kitchen-261109')
        self.assertEqual(c.snapshot()['warning'],'')

    def test_offline_does_not_claim_backgrounded(self):
        c=self.controller;c.startup_warning=Mock()
        c._report('unavailable','No authenticated phone')
        self.assertEqual(c.snapshot()['warning'],'')
        c.startup_warning.assert_not_called()

    def test_failed_save_still_stops_phone_and_does_not_retry_new_id(self):
        self.controller._start_survey('kitchen-261109')
        def command(command_name, **kwargs):
            self.calls.append((command_name, kwargs))
            return dict(status='failed' if command_name == 'SURVEY_SAVE' else 'completed', detail='No world map available')
        self.controller.command=command
        self.controller._save_survey()
        self.assertEqual(self.calls[-1][0], 'SESSION_STOP')
        self.assertEqual(sum(name=='SURVEY_SAVE' for name,_ in self.calls),1)
        self.assertEqual(self.controller.snapshot()['status'], 'failed')

    def test_old_same_name_map_is_not_verification(self):
        self.controller.command=lambda *a,**k: dict(status='completed', detail=json.dumps(dict(capabilities=['survey_resume_v1'], maps=[dict(id='old',name='kitchen-261109')])))
        self.controller._start_survey('kitchen-261109'); self.controller._save_survey()
        self.assertEqual(self.controller.snapshot()['status'], 'failed')

    def test_resume_latest_kitchen_across_dates_and_verify_parent(self):
        c=self.controller
        maps=[dict(id='other',name='bedroom-261109',created=200),
              dict(id='old',name='kitchen-261108',created=100),
              dict(id='parent',name='kitchen-261109',created=150)]
        def command(command_name, **args):
            self.calls.append((command_name,args))
            if command_name=='SURVEY_SAVE':
                maps.insert(0,dict(id='revision',name='kitchen-261110',created=201,parent_map_id='parent',revision=2))
                return dict(status='completed',detail=json.dumps(dict(map_id='revision')))
            return dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=maps)))
        c.command=command;c._start_survey('kitchen-261110')
        self.assertIn(('SURVEY_START',dict(map_id='parent')),self.calls)
        self.assertEqual(c.snapshot()['parent_map_id'],'parent')
        c._save_survey()
        self.assertEqual(c.snapshot()['status'],'saved')
        self.assertEqual(c.snapshot()['saved_map_id'],'revision')
        c._start_survey('kitchen-261111')
        self.assertEqual(self.calls[-1],('SURVEY_START',dict(map_id='revision')))

    def test_bootstrap_prefers_mapped_snapshot_to_newer_limited_one(self):
        c=self.controller
        maps=[dict(id='limited',name='kitchen-261109',mapping='limited',created=200),
              dict(id='mapped',name='kitchen-261109',mapping='mapped',created=100)]
        c.command=Mock(return_value=dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=maps))))
        c._start_survey('kitchen-261109')
        self.assertIn(unittest.mock.call('SURVEY_START',map_id='mapped'),c.command.call_args_list)
        maps.append(dict(id='child',name='kitchen-261109',mapping='mapped',created=50,parent_map_id='mapped'))
        c.command.return_value=dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=maps)))
        c.command.reset_mock();c._start_survey('kitchen-261109')
        self.assertIn(unittest.mock.call('SURVEY_START',map_id='child'),c.command.call_args_list)

    def test_resume_failure_preserves_map_and_never_falls_back_or_saves(self):
        c=self.controller
        def command(command_name,**args):
            self.calls.append((command_name,args))
            if command_name=='SURVEY_START':return dict(status='failed',detail='relocalization_timeout')
            return dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=[dict(id='parent',name='kitchen-261109')])))
        c.command=command;c._start_survey('kitchen-261109');c._save_survey()
        self.assertIsNone(c._survey)
        self.assertEqual([x for x in self.calls if x[0]=='SURVEY_START'],[('SURVEY_START',dict(map_id='parent'))]*2)
        self.assertNotIn('SURVEY_SAVE',[x[0] for x in self.calls])
        self.assertIn('relocalization_timeout',c.snapshot()['error'])

    def test_relocalization_retry_stops_before_second_start(self):
        c=self.controller;starts=0
        def command(name,**args):
            nonlocal starts
            self.calls.append((name,args))
            if name=='SURVEY_START':
                starts+=1
                return dict(status='failed' if starts==1 else 'completed',detail='relocalization_timeout' if starts==1 else 'localized')
            return dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=[dict(id='parent',name='kitchen-261109')])))
        c.command=command;c._start_survey('kitchen-261109')
        self.assertEqual(c.snapshot()['status'],'surveying')
        self.assertEqual(c.snapshot()['start_attempt'],2)
        self.assertEqual([n for n,_ in self.calls],['STATUS','SESSION_STOP','SURVEY_START','SESSION_STOP','SURVEY_START'])

    def test_load_failure_unknown_and_failed_stop_do_not_restart(self):
        for reason,reply_status,stop_fails in [('map_load: corrupt','failed',False),('timeout','unknown',False),('relocalization_timeout','failed',True)]:
            c=self.controller;calls=[];stops=0
            def command(name,**args):
                nonlocal stops
                calls.append(name)
                if name=='SESSION_STOP':
                    stops+=1
                    if stop_fails and stops>1:return dict(status='failed',detail='stop unavailable')
                if name=='SURVEY_START':return dict(status=reply_status,detail=reason)
                return dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=[dict(id='parent',name='kitchen-261109')])))
            c.command=command;c._start_survey('kitchen-261109')
            self.assertEqual(calls.count('SURVEY_START'),1)
            self.assertIsNone(c._survey)

    def test_cancelled_start_does_not_issue_second_resume(self):
        c=self.controller;c._thread=object();c._active=False
        calls=[]
        def command(name,**args):
            calls.append(name)
            if name=='SURVEY_START':return dict(status='failed',detail='relocalization_timeout')
            return dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=[dict(id='parent',name='kitchen-261109')])))
        c.command=command;c._start_survey('kitchen-261109')
        self.assertEqual(calls.count('SURVEY_START'),1)
        self.assertEqual(calls[-1],'SESSION_STOP')
        self.assertIsNone(c._survey)
        c._thread=None

    def test_old_phone_or_malformed_inventory_never_starts_fresh(self):
        for detail in ('{}','not-json',json.dumps(dict(maps=[])),json.dumps(dict(capabilities=['survey_resume_v1'],maps=None)),json.dumps(dict(capabilities=['survey_resume_v1'],maps=[],map_inventory_errors=1))):
            c=TrekSurveyController(b'1701',5010,Mock(),command=Mock(return_value=dict(status='completed',detail=detail)))
            c._start_survey('kitchen-261109')
            self.assertEqual(c.snapshot()['status'],'failed')
            c.command.assert_called_once_with('STATUS',map_prefix='kitchen')

    def test_saved_revision_must_have_expected_parent(self):
        c=self.controller;phase=False
        def command(command_name,**args):
            nonlocal phase
            if command_name=='SURVEY_SAVE':
                phase=True
                return dict(status='completed',detail=json.dumps(dict(map_id='wrong')))
            maps=[dict(id='parent',name='kitchen-261109')]
            if phase:maps.insert(0,dict(id='wrong',name='kitchen-261109',parent_map_id='wrong-parent'))
            return dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=maps)))
        c.command=command;c._start_survey('kitchen-261109');c._save_survey()
        self.assertEqual(c.snapshot()['status'],'failed')
        self.assertIsNone(c.snapshot()['saved_map_id'])

    def test_configured_seed_used_only_until_a_revision_exists(self):
        c=self.controller;c.seed_map_id='chosen-seed'
        maps=[dict(id='recent-independent',name='kitchen-261109')]
        c.command=Mock(side_effect=lambda *a,**k:dict(status='completed',detail=json.dumps(dict(capabilities=['survey_resume_v1'],maps=maps))))
        c._start_survey('kitchen-261109')
        self.assertIn(unittest.mock.call('SURVEY_START',map_id='chosen-seed'),c.command.call_args_list)
        c._save_survey();maps.insert(0,dict(id='revision',name='kitchen-261109',parent_map_id='chosen-seed',created=10))
        c.command.reset_mock();c._start_survey('kitchen-261109')
        self.assertIn(unittest.mock.call('SURVEY_START',map_id='revision'),c.command.call_args_list)

    def test_real_worker_drains_save_on_close(self):
        c=self.controller;c.start();c.mode_changed('wall');c.close()
        self.assertEqual(c.snapshot()['status'], 'saved')
        self.assertIsNone(c._thread)

    def test_mission_hook_is_nonblocking_and_not_submode_driven(self):
        fixture=roomberry_mission_test.RoomberryMissionTest();fixture.setUp()
        mission=fixture.mission; callback=Mock();mission.on_mode_change=callback
        mission._mode='wall';mission._announce_mode();mission._announce_mode()
        callback.assert_called_once_with('wall')
        mission._mode='idle';mission._announce_mode()
        self.assertEqual(callback.call_args.args,('idle',))

    def test_command_retries_pin_id_target_and_free_map_name(self):
        from roomberry_trek_control import encode, decode
        key=b'1701'; requests=[]; sock=MagicMock()
        sock.__enter__.return_value=sock
        sock.send.side_effect=lambda data: requests.append(decode(data,key))
        sock.recv.side_effect=lambda size: encode(dict(kind='response',id=requests[-1]['id'],target='phone',
                                                       status='accepted' if len(requests)==1 else 'completed'),key)
        c=TrekSurveyController(key,5010,Mock())
        with patch('roomberry_trek_survey.socket.socket',return_value=sock):
            reply=c._command('SURVEY_SAVE',name='kitchen-261109')
        self.assertEqual(reply['status'],'completed')
        self.assertEqual(requests[0]['id'],requests[1]['id'])
        self.assertEqual(requests[1]['target'],'phone')
        self.assertEqual(requests[1]['name'],'kitchen-261109')
        self.assertEqual(c._target,'phone')

    def test_server_stops_robot_before_survey_and_closes_relay_on_error(self):
        from roomberry import RoomberryServer
        from types import SimpleNamespace
        for failure in (False,True):
            with self.subTest(survey_close_failure=failure):
                order=[]
                server=SimpleNamespace(logger=Mock(),speech_filter=Mock(),speech_sender=Mock(),trek_survey=Mock(),
                                       server_close=Mock(),mission=None,map_log=None,camera_service=Mock(),
                                       roomba_control=Mock(),navlink=Mock())
                server.roomba_control.close.side_effect=lambda: order.append('robot')
                def close_survey():
                    order.append('survey')
                    if failure: raise OSError('survey shutdown failed')
                server.trek_survey.close.side_effect=close_survey
                server.speech_sender.close.side_effect=lambda: order.append('speech')
                server.navlink.close.side_effect=lambda: order.append('relay')
                if failure:
                    with self.assertRaises(OSError): RoomberryServer.stop(server)
                else: RoomberryServer.stop(server)
                self.assertEqual(order,['robot','survey','speech','relay'])


if __name__=='__main__': unittest.main()
