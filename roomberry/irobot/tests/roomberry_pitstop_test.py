# @(#)roomberry_pitstop_test.py 3.1.pit.3 2026/11/04
"""Bench-only arming, measured stops, serial faults and telemetry regression tests."""
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import roomberry_pitstop as pit


def packet(**overrides):
    raw = bytearray(80)
    raw[0], raw[40] = 12, 3
    struct.pack_into('>HhbHH', raw, 17, 15000, -200, 25, 2000, 3000)
    for name, value in overrides.items():
        offset, fmt = dict(bumps=(0, 'B'), cliff=(2, 'B'), overcurrent=(7, 'B'),
                           buttons=(11, 'B'), mode=(40, 'B'), charging=(39, 'B'),
                           charging_state=(16, 'B'),
                           left=(52, '>H'), right=(54, '>H'), voltage=(17, '>H'),
                           temperature=(21, 'b'), current=(71, '>h'))[name]
        struct.pack_into(fmt, raw, offset, value)
    return bytes(raw)


class Clock:
    def __init__(self):
        self.now = 0.

    def __call__(self):
        return self.now


class Hardware:
    def __init__(self):
        self.raw = packet()
        self.drives = []
        self.commands = []
        self.startup_text = ''
        self.closed = False

    def initialize(self):
        pass

    def drive(self, left, right):
        self.drives.append((left, right))

    def poll(self):
        return pit.decode(self.raw)

    def cleanup(self):
        self.closed = True
        return []


class PitStopTest(unittest.TestCase):
    def row(self, left=0, right=0):
        return dict(left_mm_s=left, right_mm_s=right)

    def owner(self):
        clock, hw = Clock(), Hardware()
        owner = pit.Owner(hw, clock)
        owner.started = owner.sent_at = 0.
        owner.applied = (0, 0)
        return clock, hw, owner

    def test_default_schedule_under_twenty_minutes(self):
        stages = pit.schedule('20m')
        self.assertEqual(len(stages), 168)
        self.assertAlmostEqual(pit.BASELINE+len(stages)*pit.SLOT, 1078.2)
        self.assertFalse(any(abs(v) in (5, 10) for s in stages for v in (s.left, s.right)))
        self.assertLess(pit.BASELINE+len(stages)*pit.SLOT, pit.MAX_SECONDS)
        for speed in pit.SPEEDS:
            group = [s for s in stages if s.label.startswith(f'sweep{speed}/')]
            self.assertEqual(len(group), 8)
            self.assertEqual({(s.left,s.right) for s in group},
                             {(speed,0),(-speed,0),(0,speed),(0,-speed),
                              (speed,speed),(-speed,-speed),(-speed,speed),(speed,-speed)})
        self.assertEqual(max(abs(v) for s in stages[:8] for v in (s.left,s.right)), 20)

    def test_no_exhaustive_profile(self):
        with self.assertRaises(ValueError):
            pit.schedule('exhaustive')

    def test_invalid_wheel_commands(self):
        for value in (501, -501, .5, True):
            with self.assertRaises(ValueError):
                pit.Stage('invalid', value, 0)

    def test_wrap_safe_signed_encoder_deltas(self):
        self.assertEqual(pit.encoder_delta(2,65534), 4)
        self.assertEqual(pit.encoder_delta(65534,2), -4)

    def test_signed_currents_raw_stasis_and_encoder_fields(self):
        row = pit.decode(packet(current=-321, left=65535))
        self.assertEqual(row['left_motor_current'], -321)
        self.assertEqual(row['left_encoder_counts'], 65535)
        self.assertEqual(row['stasis_raw'], 0)
        self.assertEqual(len(row['packet_hex']), 160)
        self.assertFalse(row['stasis_toggling'])

    def test_short_or_invalid_packets_abort(self):
        for raw in (b'', packet()[:-1], packet(mode=255), packet(voltage=0), packet(cliff=9)):
            with self.assertRaises(pit.BenchFault):
                pit.decode(raw)

    def test_suspended_wheels_and_stasis_allowed_only_in_full(self):
        self.assertEqual(pit.check_sample(pit.decode(packet())), (12,False,False,False,False))
        for raw in (packet(mode=2), packet(bumps=0), packet(bumps=4), packet(bumps=13),
                    packet(overcurrent=4), packet(buttons=1), packet(charging=2),
                    packet(voltage=11000), packet(temperature=50)):
            with self.assertRaises(pit.BenchFault):
                pit.check_sample(pit.decode(raw))

    def test_bench_cliff_changes_are_telemetry_but_lowered_wheels_abort(self):
        pattern = pit.check_sample(pit.decode(packet()))
        self.assertEqual(pit.check_sample(pit.decode(packet(cliff=1)), pattern)[0], 12)
        with self.assertRaisesRegex(pit.BenchFault, 'both drive wheels'):
            pit.check_sample(pit.decode(packet(bumps=4)), pattern)

    def test_real_pit_abort_packet_is_accepted_in_bench_mode(self):
        raw = bytes.fromhex('0c000001010100000000000000000000043640fe7918076d0a88000400a9002a00270030000000000300000000000000004e0000f328f0360000040009000e0000000e00120000000200780005000000')
        pattern = (12, True, True, True, True)
        self.assertEqual(pit.check_sample(pit.decode(raw), pattern), (12,False,True,True,True))

    def test_cliff_changes_are_written_as_events(self):
        with TemporaryDirectory() as tmp, patch.object(pit, 'make_report'):
            recorder = pit.Recorder(Path(tmp)/'session', {})
            row = pit.decode(packet())
            row.update(stage=-1, label='', phase='baseline', monotonic_s=0.)
            recorder.sample(dict(row))
            row['cliff_left_sensor'] = True
            row['monotonic_s'] = .05
            recorder.sample(dict(row))
            recorder.finish('complete', 'test')
            events = [json.loads(line) for line in (recorder.directory/'events.jsonl').read_text().splitlines()]
            changes = [event for event in events if event['event']=='cliff_change']
            self.assertEqual(len(changes), 1)
            self.assertFalse(changes[0]['before']['cliff_left_sensor'])
            self.assertTrue(changes[0]['after']['cliff_left_sensor'])

    def test_waiting_state_without_powered_charger_is_allowed(self):
        row = pit.decode(packet(charging_state=4))
        self.assertEqual(pit.check_sample(row)[0], 12)

    def test_waiting_state_with_powered_charger_is_blocked(self):
        for source in (1, 2, 3):
            with self.assertRaisesRegex(pit.BenchFault, f'sources=0x{source:02x}.*charging_state=4'):
                pit.check_sample(pit.decode(packet(charging_state=4, charging=source)))

    def test_active_charging_and_fault_have_precise_messages(self):
        for state in (1, 2, 3):
            with self.assertRaisesRegex(pit.BenchFault, f'active charging.*sources=0x00.*charging_state={state}'):
                pit.check_sample(pit.decode(packet(charging_state=state)))
        with self.assertRaisesRegex(pit.BenchFault, 'charging fault.*not proof.*charging_state=5'):
            pit.check_sample(pit.decode(packet(charging_state=5)))

    def test_waiting_state_retains_other_battery_safeguards(self):
        for kwargs in (dict(voltage=11000), dict(temperature=50)):
            with self.assertRaises(pit.BenchFault):
                pit.check_sample(pit.decode(packet(charging_state=4, **kwargs)))

    def test_invalid_charging_state_is_malformed_packet(self):
        with self.assertRaisesRegex(pit.BenchFault, 'implausible'):
            pit.decode(packet(charging_state=255))

    def test_no_motion_before_measured_baseline(self):
        seq = pit.Sequencer(pit.schedule('smoke'), 0)
        self.assertEqual(seq.update(0, self.row()), (0,0))
        self.assertEqual(seq.update(2.99, self.row()), (0,0))
        self.assertEqual(seq.update(3., self.row()), (0,0))
        self.assertEqual(seq.update(3.49, self.row()), (0,0))
        self.assertEqual(seq.update(3.5, self.row()), (20,0))

    def test_moving_baseline_aborts(self):
        seq = pit.Sequencer(pit.schedule('smoke'), 0)
        seq.update(0, self.row())
        with self.assertRaisesRegex(pit.BenchFault, 'baseline'):
            seq.update(3., self.row(20))

    def test_zero_and_sustained_settle_before_reversal(self):
        seq = pit.Sequencer(pit.schedule('smoke'), 0)
        seq.update(0, self.row()); seq.update(3., self.row())
        self.assertEqual(seq.update(3.5, self.row()), (20,0))
        self.assertEqual(seq.update(5.99, self.row(20)), (20,0))
        self.assertEqual(seq.update(6.01, self.row(20)), (0,0))
        seq.update(6.2, self.row()); seq.update(6.8, self.row())
        self.assertTrue(seq.settled)
        self.assertEqual(seq.update(9.5, self.row()), (0,0))
        self.assertEqual(seq.update(10.01, self.row()), (-20,0))

    def test_failed_stop_prevents_next_stage(self):
        seq = pit.Sequencer(pit.schedule('smoke'), 0)
        seq.update(0, self.row()); seq.update(3., self.row())
        seq.update(3.5, self.row(20))
        with self.assertRaisesRegex(pit.BenchFault, 'failed to stop'):
            seq.update(9.01, self.row(20))

    def test_resumed_movement_invalidates_previously_settled_state(self):
        seq = pit.Sequencer(pit.schedule('smoke'), 0)
        seq.update(0, self.row()); seq.update(3., self.row())
        seq.update(3.5, self.row(20))
        seq.update(6.1, self.row()); seq.update(6.7, self.row())
        self.assertTrue(seq.settled)
        with self.assertRaisesRegex(pit.BenchFault, 'settle'):
            seq.update(9.5, self.row(20))

    def test_hard_runtime_cap(self):
        seq = pit.Sequencer(pit.schedule('smoke'), 0)
        with self.assertRaisesRegex(pit.BenchFault, 'runtime limit'):
            seq.update(1200, self.row())
        clock, hw, owner = self.owner()
        clock.now = 1200
        owner.publish((0,0), {})
        with self.assertRaisesRegex(pit.BenchFault, 'runtime limit'):
            owner.step()
        self.assertEqual(hw.drives, [])

    def test_expired_heartbeat_refuses_pending_motion(self):
        clock, hw, owner = self.owner()
        owner.publish((30,30), {})
        clock.now = .61
        with self.assertRaisesRegex(pit.BenchFault, 'heartbeat'):
            owner.step()
        self.assertEqual(hw.drives, [])

    def test_owner_encoder_measurements_and_order(self):
        clock, hw, owner = self.owner()
        owner.step()
        clock.now = .1
        hw.raw = packet(left=2, right=65534)
        owner.publish((20,-20), dict(phase='hold',stage=0,label='test'))
        row = owner.step()
        self.assertEqual(hw.drives, [(20,-20)])
        self.assertAlmostEqual(row['left_ticks_s'], 20)
        self.assertAlmostEqual(row['right_ticks_s'], -20)
        self.assertAlmostEqual(row['left_mm_s'], 20*pit.TICK_MM)

    def test_encoder_discontinuity_aborts(self):
        clock, hw, owner = self.owner()
        owner.step(); clock.now = .05; hw.raw = packet(left=10000)
        with self.assertRaisesRegex(pit.BenchFault, 'encoder discontinuity'):
            owner.step()

    def test_stale_previous_sample_blocks_dispatch_of_new_command(self):
        clock, hw, owner = self.owner()
        owner.step(); clock.now = .31
        owner.publish((50,50), {})
        with self.assertRaisesRegex(pit.BenchFault, 'before motor dispatch'):
            owner.step()
        self.assertEqual(hw.drives, [])

    def test_queue_backpressure_stops_test(self):
        clock, hw, owner = self.owner()
        owner.samples = __import__('queue').Queue(maxsize=1)
        owner.step(); clock.now = .05
        with self.assertRaisesRegex(pit.BenchFault, 'writer'):
            owner.step()

    def test_serial_failure_cleanup_stops_then_closes(self):
        clock, hw, owner = self.owner()
        hw.poll = Mock(side_effect=OSError('serial unavailable'))
        owner.run()
        self.assertIn('serial unavailable', owner.error)
        self.assertEqual(hw.drives[-1], (0,0))
        self.assertTrue(hw.closed)
        self.assertTrue(owner.cleanup_errors)

    def test_watchdog_during_sequence_stall(self):
        hw = Hardware()
        owner = pit.Owner(hw)
        owner.start()
        owner.join(3)
        self.assertFalse(owner.is_alive())
        self.assertIn('heartbeat', owner.error)
        self.assertEqual(hw.drives[-1], (0,0))
        self.assertTrue(owner.shutdown_stopped)
        self.assertTrue(hw.closed)

    def test_drop_fault_stops_and_closes(self):
        hw = Hardware(); hw.raw = packet(bumps=0)
        owner = pit.Owner(hw)
        owner.run()
        self.assertIn('suspended', owner.error)
        self.assertEqual(hw.drives[-1], (0,0))
        self.assertTrue(hw.closed)

    def test_fault_sensor_snapshot_survives_cleanup_readings(self):
        hw = Hardware()
        replies = iter((packet(charging_state=5),))
        def poll():
            return pit.decode(next(replies, packet()))
        hw.poll = poll
        owner = pit.Owner(hw)
        owner.run()
        self.assertIn('charging fault', owner.error)
        self.assertEqual(owner.fault_sensor_sample['charging_state'], 5)
        self.assertEqual(owner.fault_sensor_sample['charging_sources_raw'], 0)
        self.assertTrue(owner.shutdown_stopped)

    def test_slow_reads_fall_back_to_ten_hz(self):
        clock, hw, owner = self.owner()
        original = hw.poll
        def slow():
            clock.now += .06
            return original()
        hw.poll = slow
        for _ in range(5):
            owner.publish((0,0), {})
            owner.step()
        self.assertEqual(owner.period, .1)

    def test_late_sensor_reply_aborts(self):
        clock, hw, owner = self.owner()
        original = hw.poll
        def late():
            clock.now += .31
            return original()
        hw.poll = late
        with self.assertRaisesRegex(pit.BenchFault, '300 ms'):
            owner.step()

    def test_serial_adapter_uses_correct_wheel_order_and_cleanup(self):
        fake = Mock()
        fake.write.side_effect = lambda data: len(data)
        with patch('serial.Serial', return_value=fake) as serial, patch.object(pit, 'reject_other_owner'):
            hw = pit.SerialBench('/dev/fake', 115200)
            hw.drive(20,-30)
            self.assertEqual(fake.write.call_args.args[0], bytes([145])+struct.pack('>hh', -30,20))
            self.assertTrue(serial.call_args.kwargs['exclusive'])
            fake.write.side_effect = OSError('failed write')
            self.assertEqual(len(hw.cleanup()), 4)
            fake.close.assert_called_once()

    def test_initialize_zeros_in_full_sets_pit_and_never_resets_or_wakes(self):
        fake = Mock(in_waiting=0)
        fake.write.side_effect = lambda data: len(data)
        fake.read.return_value = b''
        with patch('serial.Serial', return_value=fake), patch.object(pit, 'reject_other_owner'), \
             patch.object(pit.time, 'sleep'):
            hw = pit.SerialBench('/dev/fake', 115200)
            hw.initialize()
            commands = [call.args[0] for call in fake.write.call_args_list]
            self.assertEqual(commands[0], bytes([128]))
            full = commands.index(bytes([132]))
            self.assertEqual(commands[full+1], bytes([145,0,0,0,0]))
            self.assertEqual(commands[-1], bytes([164])+b' pit')
            self.assertNotIn(bytes([7]), commands)  # RESET never sent.
            hw.cleanup()
            self.assertEqual(fake.write.call_args.args[0], bytes([128]))

    def test_partial_serial_write_is_failure(self):
        fake = Mock(); fake.write.return_value = 1
        with patch('serial.Serial', return_value=fake), patch.object(pit, 'reject_other_owner'):
            hw = pit.SerialBench('/dev/fake', 115200)
            with self.assertRaisesRegex(pit.BenchFault, 'short serial write'):
                hw.drive(30,30)

    def test_live_serial_thread_stops_and_restores_passive(self):
        fake = Mock(in_waiting=0)
        fake.write.side_effect = lambda data: len(data)
        fake.read.side_effect = lambda n: packet() if n == 80 else b''
        with patch('serial.Serial', return_value=fake), patch.object(pit, 'reject_other_owner'):
            hw = pit.SerialBench('/dev/fake', 115200)
            owner = pit.Owner(hw)
            owner.start()
            owner.samples.get(timeout=2)
            owner.publish((20,0), dict(phase='startup',stage=0,label='test'))
            owner.samples.get(timeout=2)
            owner.stop_event.set()
            owner.join(3)
            self.assertFalse(owner.is_alive())
            self.assertIsNone(owner.error)
            self.assertTrue(owner.shutdown_stopped)
            self.assertEqual(owner.cleanup_errors, [])
            commands = [call.args[0] for call in fake.write.call_args_list]
            self.assertIn(bytes([145,0,0,0,20]), commands)
            self.assertEqual(commands[-1], bytes([128]))
            fake.close.assert_called_once()

    def test_active_service_rejected(self):
        with patch.object(pit.subprocess, 'run', return_value=Mock(stdout='active\n')):
            with self.assertRaisesRegex(pit.BenchFault, 'stop roomberry.service'):
                pit.reject_other_owner('/dev/fake')

    def test_another_serial_owner_rejected(self):
        with patch.object(pit.subprocess, 'run', return_value=Mock(stdout='inactive\n')), \
             patch.object(pit.Path, 'glob', return_value=[Path('/proc/123/fd/4')]), \
             patch.object(pit.os.path, 'realpath', return_value='/dev/ttyFAKE'):
            with self.assertRaisesRegex(pit.BenchFault, 'already open'):
                pit.reject_other_owner('/dev/fake')

    def test_dry_run_never_opens_serial_or_creates_output(self):
        with patch.object(pit, 'SerialBench') as serial, patch('builtins.print'):
            self.assertEqual(pit.main(['--profile','smoke']), 0)
            serial.assert_not_called()

    def test_noninteractive_live_run_refused_before_serial(self):
        with patch.object(pit.os, 'isatty', return_value=False), \
             patch.object(pit, 'SerialBench') as serial, patch('builtins.print'):
            with self.assertRaises(SystemExit):
                pit.main(['--run'])
            serial.assert_not_called()

    def test_wrong_arm_phrase_never_opens_serial(self):
        with patch.object(pit.os, 'isatty', return_value=True), \
             patch('builtins.input', return_value='no'), patch('builtins.print'), \
             patch.object(pit, 'SerialBench') as serial:
            self.assertEqual(pit.main(['--run']), 1)
            serial.assert_not_called()

    def test_output_never_overwrites_existing_session(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                pit.Recorder(tmp, {})

    def test_accelerated_smoke_profile_writes_report_and_all_stages(self):
        with TemporaryDirectory() as tmp, patch.object(pit, 'SerialBench') as serial, \
             patch('builtins.print'), patch.dict('sys.modules', {'matplotlib': None}):
            directory = Path(tmp)/'session'
            status = pit.main(['--simulate','--profile','smoke','--output',str(directory)])
            self.assertEqual(status, 0)
            serial.assert_not_called()
            manifest = json.loads((directory/'manifest.json').read_text())
            self.assertTrue(manifest['simulated'])
            self.assertEqual(manifest['result'], 'complete')
            self.assertEqual(len((directory/'stage-summary.csv').read_text().splitlines()), 9)
            self.assertIn('Plot omitted', (directory/'report.md').read_text())
            self.assertIn('packet_hex', (directory/'samples.csv').read_text().splitlines()[0])
            events = [json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines()]
            commands = [e for e in events if e['event']=='simulated_command']
            for a,b in zip(commands,commands[1:]):
                if a['left'] or a['right']:
                    self.assertEqual((b['left'],b['right']), (0,0))


if __name__ == '__main__':
    unittest.main()
