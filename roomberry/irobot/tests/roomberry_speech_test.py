"""Catalogue, log tagging and speech delivery without a robot or speech audio."""
# @(#)roomberry_speech_test.py 3.2.speechlog.1 2026/11/12 16:13:04
import logging
import json
import io
import unittest
from unittest.mock import Mock, patch
from roomberry_speech import PHRASES, MODE_CODES, BATTERY_CODES, phrase, SpeechLogFilter, SpeechSender
from roomberry_trek_control import decode, encode


class SpeechTests(unittest.TestCase):
    def record(self, level=logging.INFO, **fields):
        record = logging.LogRecord('Roomberry', level, '', 0, 'Battery %s', ('low',), None)
        record.__dict__.update(fields)
        return record

    def test_catalogue_and_modes(self):
        self.assertEqual(len(PHRASES['en-AU']), 34)
        self.assertTrue(set(MODE_CODES.values()) <= PHRASES['en-AU'].keys())
        self.assertTrue(set(BATTERY_CODES.values()) <= PHRASES['en-AU'].keys())
        self.assertEqual(phrase('LOW_BATT'), 'G’day, Captain! I’m running a bit low on juice!')
        self.assertTrue(all(0 < len(text) <= 500 for text in PHRASES['en-AU'].values()))
        with self.assertRaises(KeyError):
            phrase('missing')
        with self.assertRaises(KeyError):
            phrase('IDLE', 'missing')

    def test_logs_have_codes_and_original_details(self):
        send = Mock(); filter_ = SpeechLogFilter(send)
        record = self.record(speech_code='LOW_BATT', speech_announce=True)
        self.assertTrue(filter_.filter(record))
        self.assertEqual(record.getMessage(), '[LOW_BATT] Battery low')
        self.assertEqual(record.speech_text, phrase('LOW_BATT'))
        send.assert_called_once_with('LOW_BATT', phrase('LOW_BATT'))
        filter_.filter(record)
        self.assertEqual(record.getMessage(), '[LOW_BATT] Battery low')
        send.assert_called_once()
        info = self.record(); filter_.filter(info)
        self.assertEqual(info.speech_code, 'STATUS')
        send.assert_called_once()
        error = self.record(logging.ERROR); filter_.filter(error)
        self.assertEqual(error.speech_code, 'ERROR')
        self.assertEqual(send.call_count, 2)

    def test_repeat_suppression_and_transport_logging_no_loop(self):
        send = Mock(); filter_ = SpeechLogFilter(send)
        with patch('roomberry_speech.monotonic', side_effect=[0, 1, 31]):
            for _ in range(3):
                filter_.filter(self.record(logging.ERROR))
        self.assertEqual(send.call_count, 2)
        filter_.filter(self.record(logging.ERROR, speech_announce=False))
        self.assertEqual(send.call_count, 2)
        send.side_effect = OSError('unavailable')
        self.assertTrue(filter_.filter(self.record(speech_code='SAFETY', speech_announce=True)))

    def test_queue_bounded_and_catalogue_validation(self):
        sender = SpeechSender(b'A'*32, 5010, Mock())
        for _ in range(5):
            sender.submit('IDLE', phrase('IDLE'))
        self.assertEqual(sender._queue.qsize(), 4)
        self.assertIn('queue full', sender.logger.info.call_args.args[-1])
        with self.assertRaises(ValueError):
            sender.submit('IDLE', 'unmapped text')

    def test_delivery_text_ids_and_target_pinned_on_retry(self):
        key = b'A'*32; logger = Mock(); sock = Mock(); requests = []
        sender = SpeechSender(key, 5010, logger)
        def send(data): requests.append(decode(data, key))
        def receive(size):
            return encode(dict(kind='response', id=requests[-1]['id'], target='phone',
                               status='accepted' if len(requests) == 1 else 'completed'), key)
        sock.send.side_effect = send; sock.recv.side_effect = receive
        sock.__enter__ = Mock(return_value=sock); sock.__exit__ = Mock(return_value=False)
        with patch('roomberry_speech.socket.socket', return_value=sock):
            sender._deliver('LOW_BATT', phrase('LOW_BATT'))
        sock.connect.assert_called_once_with(('127.0.0.1', 5010))
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]['id'], requests[1]['id'])
        self.assertEqual(requests[1]['target'], 'phone')
        self.assertEqual(requests[0]['command'], 'SPEAK')
        self.assertEqual(requests[0]['text'], phrase('LOW_BATT'))
        self.assertEqual(requests[0]['speech_code'], 'LOW_BATT')
        self.assertIn('completed', logger.info.call_args.args)

    def test_transcript_retains_exact_text_without_speech_feedback(self):
        logger = logging.Logger('TranscriptTest')
        sink = Mock()
        logger.addFilter(SpeechLogFilter(sink))
        output = io.StringIO()
        logger.addHandler(logging.StreamHandler(output))
        sender = SpeechSender(b'key',5010,logger)
        text = 'Captain, left.\n"Please stop."'
        command_id = sender.submit_text(text)
        self.assertEqual(sender.job_snapshot(command_id)['text'],text)
        self.assertIn(json.dumps(text,ensure_ascii=False),output.getvalue())
        self.assertEqual(len(output.getvalue().splitlines()),1)
        sender._log('STATUS','completed','Speech finished',command_id)
        self.assertEqual(sender.job_snapshot(command_id)['text'],text)
        self.assertIn(command_id,output.getvalue())
        sink.assert_not_called()

    def test_direct_battery_delivery_logs_attempt_once_across_retries(self):
        key=b'k'*32;logger=Mock();sock=Mock();requests=[]
        sender=SpeechSender(key,5010,logger)
        sock.send.side_effect=lambda data:requests.append(decode(data,key))
        sock.recv.side_effect=lambda _:encode(dict(kind='response',id=requests[-1]['id'],
            status='accepted' if len(requests)==1 else 'completed'),key)
        sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock(return_value=False)
        text='Roomba battery 86 percent. iPhone battery 42 percent.'
        with patch('roomberry_speech.socket.socket',return_value=sock):
            sender._deliver('STATUS',text)
        transcripts=[c for c in logger.info.call_args_list if c.args[0].startswith('Speech transcript')]
        self.assertEqual(len(transcripts),1)
        self.assertEqual(transcripts[0].args[2],'attempt')
        self.assertEqual(json.loads(transcripts[0].args[-1]),text)
        self.assertEqual(sender.job_snapshot(requests[0]['id'])['text'],text)
        self.assertEqual(sender.job_snapshot(requests[0]['id'])['status'],'completed')

    def test_server_worker_lifecycle_and_brake_cleanup_order(self):
        from roomberry import RoomberryServer
        from types import SimpleNamespace
        calls = []
        sender = Mock(); sender.close.side_effect = lambda: calls.append('speech')
        robot = Mock(); robot.close.side_effect = lambda: calls.append('robot')
        navlink = Mock(port=5010); navlink.close.side_effect = lambda: calls.append('navlink')
        server = SimpleNamespace(logger=Mock(), speech_filter=Mock(), speech_sender=sender,
                                 navlink=navlink, map_log=None, mission=None, roomba_control=robot,
                                 camera_service=Mock(), serve_forever=Mock(), server_close=Mock())
        RoomberryServer.start(server)
        sender.start.assert_called_once_with()
        self.assertEqual(sender.port, 5010)
        RoomberryServer.stop(server)
        self.assertEqual(calls, ['robot', 'speech', 'navlink'])
        server.logger.removeFilter.assert_called_once_with(server.speech_filter)
        self.assertIsNone(server.speech_filter.send)

    def test_offline_is_not_replayed(self):
        sock = Mock(); requests = []; key = b'A'*32; sender = SpeechSender(key, 5010, Mock())
        sock.send.side_effect = lambda data: requests.append(decode(data, key))
        sock.recv.side_effect = lambda size: encode(dict(kind='response', id=requests[-1]['id'], status='unavailable'), key)
        sock.__enter__ = Mock(return_value=sock); sock.__exit__ = Mock(return_value=False)
        with patch('roomberry_speech.socket.socket', return_value=sock):
            sender._deliver('IDLE', phrase('IDLE'))
        self.assertEqual(len(requests), 1)

    def test_critical_confirmation_supersedes_queued_chatter(self):
        sender=SpeechSender(b'1701',5010,Mock())
        old=sender.submit('WALL_LOST',phrase('WALL_LOST'))
        for _ in range(3): sender.submit('SEARCH_WALL',phrase('SEARCH_WALL'))
        confirmation=sender.submit('TAG15_VALIDATED',phrase('TAG15_VALIDATED'))
        self.assertEqual(sender._queue.qsize(),4)
        self.assertEqual(sender.job_snapshot(old)['status'],'dropped')
        self.assertEqual(sender.job_snapshot(confirmation)['status'],'queued')

    def test_map_confirmation_does_not_discard_queued_safety(self):
        sender=SpeechSender(b'1701',5010,Mock())
        safety=sender.submit('SAFETY',phrase('SAFETY'))
        for _ in range(3): sender.submit('SEARCH_WALL',phrase('SEARCH_WALL'))
        saved=sender.submit('MAP_READY',phrase('MAP_READY'))
        self.assertEqual(sender.job_snapshot(safety)['status'],'queued')
        self.assertEqual(sender.job_snapshot(saved)['status'],'dropped')


if __name__ == '__main__':
    unittest.main()
