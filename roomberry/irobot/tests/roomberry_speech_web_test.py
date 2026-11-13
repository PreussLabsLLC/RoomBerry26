"""Speech test web input, authentication diagnostics and observable outcomes."""
# @(#)roomberry_speech_web_test.py 3.2 2026/11/09 21:00:00
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from roomberry import RoomberryHandler
from roomberry_navlink import NavLinkReceiver
from roomberry_speech import SpeechSender, phrase
from roomberry_trek_control import TrekRelay
from roomberry_web import speech_snapshot
from time import monotonic


class SpeechWebTests(unittest.TestCase):
    def setUp(self):
        self.sender = SpeechSender(b'A'*32, 5010, Mock())
        self.sender._thread = SimpleNamespace(is_alive=lambda: True)
        self.receiver = NavLinkReceiver()
        self.receiver._thread = SimpleNamespace(is_alive=lambda: True)
        self.receiver.trek_control = TrekRelay(b'A'*32)
        self.receiver.trek_control.peer = ('192.0.2.10', 45000)
        self.receiver.trek_control.last_peer = monotonic()
        self.handler = RoomberryHandler.__new__(RoomberryHandler)
        self.handler.server = SimpleNamespace(speech_sender=self.sender, navlink=self.receiver, logger=Mock())
        self.handler.wfile = io.BytesIO()
        self.handler.headers = {'Content-Type': 'application/json'}
        for name in ('send_response', 'send_header', 'end_headers', 'send_error'):
            setattr(self.handler, name, Mock())

    def post(self, body):
        data = json.dumps(body).encode()
        self.handler.rfile = io.BytesIO(data)
        self.handler.headers['Content-Length'] = str(len(data))
        self.handler.path = '/speech'
        self.handler.do_POST()
        return json.loads(self.handler.wfile.getvalue())

    def test_free_text_is_queued_and_outcomes_can_be_polled(self):
        text = '<Captain> & crew: G’day!'
        result = self.post(dict(text=text))
        self.handler.send_response.assert_called_with(202)
        code, queued_text, created, command_id = self.sender._queue.get_nowait()
        self.assertEqual(queued_text, text)
        self.assertEqual(result['id'], command_id)
        self.assertEqual(code, 'STATUS')
        self.sender._remember(command_id, code, 'accepted', 'Phone ACK')
        self.handler.wfile = io.BytesIO()
        self.handler.path = '/speech.json?id='+command_id
        self.assertTrue(self.handler._serve_vision())
        state = json.loads(self.handler.wfile.getvalue())
        self.assertEqual(state['job']['status'], 'accepted')
        self.assertTrue(state['ready'])
        self.sender._remember(command_id, code, 'completed', 'Speech finished')
        self.assertEqual(self.sender.job_snapshot(command_id)['status'], 'completed')

    def test_missing_key_and_stale_peer_explain_unavailability(self):
        for source in ('key', 'peer', 'worker'):
            with self.subTest(source=source):
                self.setUp()
                if source == 'key': self.receiver.trek_control = None
                if source == 'peer': self.receiver.trek_control.last_peer -= 11
                if source == 'worker': self.sender._thread = None
                result = self.post(dict(text=phrase('LOW_BATT')))
                self.handler.send_response.assert_called_with(503)
                self.assertEqual(result['status'], 'unavailable')
                self.assertTrue(result['detail'])
                self.assertTrue(self.sender._queue.empty())

    def test_bad_text_and_content_type(self):
        for text in ('', '   ', 'x'*501, None, 5):
            with self.subTest(text_type=type(text)):
                self.setUp()
                self.assertEqual(self.post(dict(text=text))['status'], 'failed')
                self.handler.send_response.assert_called_with(400)
        self.setUp(); self.handler.headers['Content-Type'] = 'text/plain'
        self.post(dict(text='hello'))
        self.handler.send_response.assert_called_with(415)

    def test_full_queue_reports_drop(self):
        for _ in range(4): self.sender.submit('IDLE', phrase('IDLE'))
        result = self.post(dict(text='G’day!'))
        self.handler.send_response.assert_called_with(429)
        self.assertEqual(result['status'], 'dropped')
        self.assertEqual(self.sender._queue.qsize(), 4)

    def test_snapshot_never_treats_binary_as_authenticated(self):
        self.receiver.received = 15
        self.receiver.trek_control.peer = None
        state = speech_snapshot(self.receiver, self.sender)
        self.assertFalse(state['ready'])
        self.assertEqual(state['received'], 15)
        self.assertFalse(state['imu_received'])
        self.assertNotIn('key', state)

    def test_free_text_input_and_script_are_served(self):
        for route, fragment in (('/', 'id="speech-text"'), ('/ui/speech.js', "fetch('/speech'")):
            self.handler.path=route; self.handler.wfile=io.BytesIO()
            self.assertTrue(self.handler._serve_vision())
            self.assertIn(fragment, self.handler.wfile.getvalue().decode())
        script=self.handler.wfile.getvalue().decode()
        self.assertNotIn('innerHTML', script)
        self.assertIn('completed', script)

    def test_live_http_free_text_and_poll(self):
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from urllib.request import Request, urlopen
        server = ThreadingHTTPServer(('127.0.0.1', 0), RoomberryHandler)
        server.logger = Mock()
        server.navlink = self.receiver; server.speech_sender = self.sender
        worker = Thread(target=server.serve_forever, daemon=True); worker.start()
        try:
            root = 'http://127.0.0.1:'+str(server.server_port)
            request = Request(root+'/speech', data=json.dumps(dict(text='G’day, Captain!')).encode(),
                              headers={'Content-Type': 'application/json'}, method='POST')
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 202)
                job = json.load(response)
            self.sender._remember(job['id'], 'STATUS', 'completed', 'Phone confirmed speech finished')
            with urlopen(root+'/speech.json?id='+job['id'], timeout=3) as response:
                self.assertEqual(json.load(response)['job']['status'], 'completed')
            with urlopen(root+'/', timeout=3) as response:
                self.assertIn('Test Speech', response.read().decode())
        finally:
            server.shutdown(); worker.join(timeout=2); server.server_close()

    def test_results_retained_with_a_bound(self):
        for number in range(70): self.sender._remember(str(number), 'STATUS', 'completed', 'done')
        self.assertEqual(len(self.sender._results), 64)
        self.assertIsNone(self.sender.job_snapshot('0'))
        self.assertEqual(self.sender.job_snapshot('69')['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
