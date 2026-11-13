"""Thirty-second quiet announcements and freshness of both battery readings."""
# @(#)roomberry_battery_speech_test.py 3.2.maps.1 2026/11/10 10:15:00
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
from roomberry_speech import SpeechSender, battery_announcement
from roomberry_trek_control import TrekRelay, encode, decode


class BatterySpeechTests(unittest.TestCase):
    def test_both_batteries_charging_zero_and_stale_readings(self):
        robot = Mock()
        state = dict(age=.1, sensors=SimpleNamespace(battery_charge=1500, battery_capacity=3000), charging=False)
        robot.snapshot.return_value=state
        relay = SimpleNamespace(peer=('phone', 1), last_peer=100, operation=dict(battery_percent=0, battery_state=2))
        receiver = SimpleNamespace(trek_control=relay)
        text = battery_announcement(robot, receiver, now=101)
        self.assertIn('Roomba battery 50 percent', text)
        self.assertIn('iPhone battery 0 percent, charging', text)
        state['age'] = 3
        self.assertIn('Roomba battery reading unavailable', battery_announcement(robot, receiver, now=101))
        relay.operation['battery_percent'] = -1
        self.assertIsNone(battery_announcement(robot, receiver, now=101))
        self.assertIsNone(battery_announcement(robot, receiver, now=111))

    def test_quiet_timer_uses_speech_ack_and_finish_and_never_cuts_queue(self):
        sender=SpeechSender(b'key', 5010, Mock(), battery_status=Mock(return_value='Both batteries healthy'))
        sender._deliver=Mock()
        sender._quiet_since=sender._last_battery_attempt=100
        sender._announce_batteries_if_quiet(now=129.9)
        sender._deliver.assert_not_called()
        sender._announce_batteries_if_quiet(now=130)
        sender._deliver.assert_called_once_with('STATUS', 'Both batteries healthy')
        sender._announce_batteries_if_quiet(now=131)
        self.assertEqual(sender._deliver.call_count, 1)
        sender.submit_text('Mission message')
        sender._announce_batteries_if_quiet(now=160)
        self.assertEqual(sender._deliver.call_count, 1)
        sender._queue.get_nowait()
        sender._log('STATUS','completed','finished')
        sender._announce_batteries_if_quiet(now=sender._quiet_since+29)
        self.assertEqual(sender._deliver.call_count, 1)

    def test_failures_are_throttled_and_do_not_fake_speech(self):
        sender=SpeechSender(b'key', 5010, Mock(), battery_status=lambda: None)
        sender._deliver=Mock()
        sender._quiet_since=sender._last_battery_attempt=100
        sender._announce_batteries_if_quiet(now=130)
        self.assertEqual(sender._quiet_since, 100)
        self.assertEqual(sender._last_battery_attempt, 130)
        sender._deliver.assert_not_called()

    def test_battery_snapshot_only_accepted_after_endpoint_challenge(self):
        relay=TrekRelay(b'key'); sock=Mock(); source=('phone', 123)
        relay.handle(encode(dict(kind='hello', target='phone', operation=dict(battery_percent=65)), b'key'), source, sock)
        self.assertEqual(relay.operation, {})
        challenge=decode(sock.sendto.call_args.args[0], b'key')
        relay.handle(encode(dict(kind='peer', target='phone', nonce=challenge['nonce']), b'key'), source, sock)
        self.assertEqual(relay.operation['battery_percent'],65)


if __name__ == '__main__': unittest.main()
