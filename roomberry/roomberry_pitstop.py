#!/usr/bin/env python3
# @(#)roomberry_pitstop.py 3.1.pit.3 2026/11/04
"""Serial-exclusive, explicitly armed suspended-wheel test. Default: dry-run."""
import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import signal
import statistics
import subprocess
import tempfile
import threading
import time

from irobot.openinterface import commands as oi
from irobot.openinterface.constants import ROBOT
from irobot.openinterface.response_parsers import SensorGroup100

VERSION = '3.1.pit.3'
PERIOD = .05
LEASE = .6
MAX_SECONDS = 1200.
BASELINE = 3.
SLOT = 6.4
TICK_MM = ROBOT.TICK_TO_DISTANCE
ARM_PHRASE = 'WHEELS FREE'
CHARGING_STATES = ('not charging', 'reconditioning charging', 'full charging',
                   'trickle charging', 'waiting', 'charging fault')
SPEEDS = (15, 20, 25, 30, 40, 50, 75, 100, 150, 200, 300, 400, 500)


class BenchFault(RuntimeError):
    pass


@dataclass(frozen=True)
class Stage:
    label: str
    left: int
    right: int

    def __post_init__(self):
        if any(type(v) is not int or abs(v) > 500 for v in (self.left, self.right)):
            raise ValueError('wheel commands must be integer mm/s within -500..500')


def patterns(speed, prefix):
    return [Stage(f'{prefix}/{name}', left, right) for name, left, right in (
        ('left+', speed, 0), ('left-', -speed, 0),
        ('right+', 0, speed), ('right-', 0, -speed),
        ('both+', speed, speed), ('both-', -speed, -speed),
        ('pivot-left', -speed, speed), ('pivot-right', speed, -speed))]


def schedule(profile):
    stages = patterns(20, 'smoke20')
    if profile == '20m':
        for speed in SPEEDS:
            stages += patterns(speed, f'sweep{speed}')
        for repeat in (1, 2):
            for speed in (20, 30, 50):
                stages += patterns(speed, f'repeat{repeat}-{speed}')
        stages += [Stage(f'asymmetric{i+1}', *pair) for i, pair in enumerate(
            ((20, 30), (30, 20), (30, 50), (50, 30), (45, 54), (54, 45), (-30, -50), (-50, -30)))]
    elif profile != 'smoke':
        raise ValueError('unknown profile')
    assert BASELINE + len(stages)*SLOT < MAX_SECONDS
    return stages


def encoder_delta(current, previous):
    return (current-previous+32768) % 65536-32768


def decode(raw):
    if len(raw) != 80:
        raise BenchFault(f'short sensor packet: {len(raw)}/80 bytes')
    s = SensorGroup100(raw)
    values = {key: getattr(s, key) for key in (
        'oi_mode', 'left_encoder_counts', 'right_encoder_counts',
        'requested_left_velocity', 'requested_right_velocity',
        'left_motor_current', 'right_motor_current', 'main_brush_motor_current',
        'side_brush_motor_current', 'voltage', 'current', 'temperature',
        'battery_charge', 'battery_capacity', 'charging_state',
        'cliff_left_sensor', 'cliff_front_left_sensor',
        'cliff_front_right_sensor', 'cliff_right_sensor',
        'cliff_left_signal', 'cliff_front_left_signal',
        'cliff_front_right_signal', 'cliff_right_signal')}
    values.update(bumps_raw=raw[0], overcurrents_raw=raw[7], buttons_raw=raw[11],
                  charging_sources_raw=raw[39], stasis_raw=raw[79],
                  stasis_toggling=s.stasis.toggling, stasis_disabled=s.stasis.disabled,
                  packet_hex=raw.hex())
    if (values['oi_mode'] not in (0, 1, 2, 3) or raw[0] & ~15 or raw[39] & ~3
            or values['charging_state'] not in range(6)
            or not 8000 <= s.voltage <= 20000 or not 0 < s.battery_capacity <= 20000
            or not 0 <= s.battery_charge <= s.battery_capacity
            or any(abs(values[k]) > 500 for k in ('requested_left_velocity', 'requested_right_velocity'))
            or any(raw[i] not in (0, 1) for i in (2, 3, 4, 5))):
        raise BenchFault('implausible sensor packet; refusing motion')
    return values


def check_sample(row, suspended_pattern=None):
    if row['oi_mode'] != 3:
        raise BenchFault('Full OI mode lost')
    if row['bumps_raw'] & 3:
        raise BenchFault('bumper contact')
    if row['overcurrents_raw']:
        raise BenchFault('motor overcurrent flag')
    if row['buttons_raw']:
        raise BenchFault('Roomba button pressed (operator stop)')
    source, state = row['charging_sources_raw'], row['charging_state']
    detail = (f"sources=0x{source:02x}, charging_state={state} ({CHARGING_STATES[state]}), "
              f"battery_current_ma={row['current']}")
    if source:
        raise BenchFault('powered charging source reported: '+detail)
    if state in (1, 2, 3):
        raise BenchFault('active charging state reported without a powered source: '+detail)
    if state == 5:
        raise BenchFault('battery charging fault reported (not proof of an attached charger): '+detail)
    # State 4 is waiting, not active charging. Without a powered source it does
    # not establish charger attachment. Battery/temperature checks still apply.
    if row['voltage'] < 12000 or row['battery_charge']/row['battery_capacity'] < .15:
        raise BenchFault('battery too low for bench test')
    if row['temperature'] >= 50:
        raise BenchFault('battery temperature at or above 50 C')
    pattern = (row['bumps_raw'] & 12, *(row[k] for k in (
        'cliff_left_sensor', 'cliff_front_left_sensor', 'cliff_front_right_sensor', 'cliff_right_sensor')))
    if pattern[0] != 12:
        raise BenchFault('both drive wheels must remain suspended (both wheel-drop bits set)')
    # Cliff sensors see the box/floor/light while suspended. Their changing
    # readings are telemetry, not proof the drive wheels touched the floor.
    # Both wheel-drop bits above remain mandatory on every sample.
    return pattern


class Sequencer:
    """Pure measured-stop state machine. No serial, files, or sleeping."""
    def __init__(self, stages, started):
        self.stages, self.started = stages, started
        self.index, self.phase = -1, 'baseline'
        self.stage_start = None
        self.quiet_since = None
        self.settled = False
        self.done = False

    def update(self, now, row):
        elapsed = now-self.started
        if elapsed >= MAX_SECONDS:
            raise BenchFault('20-minute runtime limit')
        quiet = all(row.get(k) is not None and abs(row[k]) <= 10 for k in ('left_mm_s', 'right_mm_s'))
        if quiet:
            if self.quiet_since is None:
                self.quiet_since = now
        else:
            self.quiet_since = None
        quiet_long = self.quiet_since is not None and now-self.quiet_since >= .5
        if self.index < 0:
            if elapsed < BASELINE:
                return (0, 0)
            if not quiet_long:
                raise BenchFault('wheels not settled during initial baseline')
            self.index, self.stage_start = 0, now
        position = now-self.stage_start
        if position >= SLOT:
            if not self.settled or not quiet_long:
                raise BenchFault('wheels did not settle after zero command')
            self.index += 1
            if self.index == len(self.stages):
                self.phase, self.done = 'complete', True
                return (0, 0)
            self.stage_start = now
            self.settled = False
            position = 0
        stage = self.stages[self.index]
        if position < .5:
            self.phase = 'rest'
            return (0, 0)
        if position < 3.:
            # Start detection is measured from fresh samples after this command.
            self.phase = 'startup' if position < 1. else 'hold'
            self.quiet_since = None
            return (stage.left, stage.right)
        self.phase = 'settle'
        self.settled = quiet_long
        if position >= 6. and not self.settled:
            raise BenchFault('wheels failed to stop within three seconds')
        return (0, 0)

    def context(self):
        return dict(stage=self.index, label=self.stages[self.index].label if 0 <= self.index < len(self.stages) else '',
                    phase=self.phase)


def reject_other_owner(port):
    """Refuse running service and visible users of any alias of this device."""
    try:
        result = subprocess.run(['systemctl', 'is-active', 'roomberry.service'],
                                capture_output=True, text=True, timeout=3)
    except FileNotFoundError:
        result = None
    if result is not None and result.stdout.strip() in ('active', 'activating', 'reloading'):
        raise BenchFault('stop roomberry.service before opening the serial port')
    target = os.path.realpath(port)
    for fd in Path('/proc').glob('[0-9]*/fd/*'):
        if fd.parts[2] == str(os.getpid()):
            continue
        try:
            if os.path.realpath(str(fd)) == target:
                raise BenchFault(f'serial device is already open: {fd}')
        except (OSError, PermissionError):
            continue


class SerialBench:
    """Uses shared command packers/parser without GPIO, wake, reset or auto-rearm."""
    def __init__(self, port, baud, timeout=.12):
        import serial
        reject_other_owner(port)
        self.serial = serial.Serial(port, baudrate=baud, timeout=timeout,
                                    write_timeout=timeout, exclusive=True)
        self.commands = []
        self.startup_text = ''
        self.last_packet_hex = None
        self.last_sensor_sample = None

    def send(self, data):
        requested = time.monotonic()
        if self.serial.write(data) != len(data):
            raise BenchFault('short serial write')
        self.commands.append(dict(requested=requested, completed=time.monotonic(), bytes_hex=data.hex()))

    def initialize(self):
        self.send(oi.start())
        time.sleep(.05)
        self.send(oi.drive_direct(0, 0))
        # Observe only bytes already received; do not reset/wake the robot.
        pending = self.serial.read(self.serial.in_waiting)
        self.startup_text = ''.join(chr(c) for c in pending if c in (9, 10, 13) or 32 <= c <= 126)
        self.serial.reset_input_buffer()
        self.send(oi.set_mode_full())
        time.sleep(.05)
        self.drive(0, 0)
        self.send(oi.set_motors(False, False, False, False, False))
        self.send(oi.set_ascii_leds(*map(ord, ' pit')))

    def drive(self, left, right):
        self.send(oi.drive_direct(right, left))

    def poll(self):
        self.send(oi.request_sensor_data(100))
        data = self.serial.read(80)
        self.last_packet_hex = data.hex()
        if not data:
            raise BenchFault('no sensor response (0/80 bytes); wake Roomba manually, '
                             'then check the selected serial port/baud and retry')
        self.last_sensor_sample = decode(data)
        return self.last_sensor_sample

    def cleanup(self):
        # Try each cleanup even if earlier writes fail. Never re-enter Full.
        errors = []
        for data in (oi.drive_direct(0, 0), oi.set_motors(False, False, False, False, False),
                     oi.set_ascii_leds(32, 32, 32, 32), oi.set_mode_passive()):
            try:
                self.send(data)
            except Exception as exc:
                errors.append(str(exc))
        try:
            self.serial.close()
        except Exception as exc:
            errors.append(str(exc))
        return errors


class Owner(threading.Thread):
    """Only thread touching serial. Disk/plots/sequence never block this watchdog."""
    def __init__(self, hardware, clock=time.monotonic):
        super().__init__(name='pit-serial-owner', daemon=True)
        self.hardware, self.clock = hardware, clock
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.command, self.heartbeat = (0, 0), clock()
        self.context = dict(stage=-1, label='', phase='baseline')
        self.samples = queue.Queue(maxsize=200)
        self.error = None
        self.cleanup_errors = []
        self.shutdown_stopped = False
        self.previous = None
        self.pattern = None
        self.last_received = None
        self.fault_sensor_sample = None
        self.fault_packet_hex = None
        self.period = PERIOD
        self.slow_reads = 0

    def publish(self, command, context):
        with self.lock:
            self.command, self.context, self.heartbeat = command, dict(context), self.clock()

    def step(self):
        with self.lock:
            command, context, heartbeat = self.command, dict(self.context), self.heartbeat
        now = self.clock()
        if now-heartbeat >= LEASE:
            raise BenchFault('sequence heartbeat expired (600 ms motion lease)')
        if now-self.started >= MAX_SECONDS:
            raise BenchFault('20-minute I/O-owner runtime limit')
        if self.previous is not None and now-self.previous['monotonic_s'] > .3:
            raise BenchFault('last sensor sample stale before motor dispatch')
        if command != self.applied:
            self.hardware.drive(*command)
            self.applied = command
            self.sent_at = self.clock()
        requested = self.clock()
        row = self.hardware.poll()
        self.last_received = dict(row)
        now = self.clock()
        if now-requested > .3:
            raise BenchFault('sensor read exceeded 300 ms')
        self.slow_reads = self.slow_reads+1 if now-requested > .045 else 0
        if self.slow_reads >= 5:
            self.period = .1  # Preserve serial headroom; never overlap queries.
        row.update(context, monotonic_s=now, sensor_requested_s=requested,
                   sensor_age_s=now-requested, command_left=self.applied[0], command_right=self.applied[1],
                   command_sent_s=self.sent_at, target_period_s=self.period,
                   wall_time=datetime.now(timezone.utc).isoformat())
        for wheel in ('left', 'right'):
            row[wheel+'_ticks_delta'] = row[wheel+'_ticks_s'] = row[wheel+'_mm_s'] = None
        if self.previous is not None:
            dt = now-self.previous['monotonic_s']
            if not 0 < dt <= .5:
                raise BenchFault('stale sensor interval')
            row['interval_s'] = dt
            for wheel in ('left', 'right'):
                delta = encoder_delta(row[wheel+'_encoder_counts'], self.previous[wheel+'_encoder_counts'])
                if abs(delta)*TICK_MM/dt > 1200:
                    raise BenchFault('encoder discontinuity / implausible wheel speed')
                row[wheel+'_ticks_delta'] = delta
                row[wheel+'_ticks_s'] = delta/dt
                row[wheel+'_mm_s'] = delta*TICK_MM/dt
        else:
            row['interval_s'] = None
        self.pattern = check_sample(row, self.pattern)
        self.previous = row
        try:
            self.samples.put_nowait(row)
        except queue.Full:
            raise BenchFault('telemetry writer stopped draining samples')
        return row

    def run(self):
        self.started = self.clock()
        self.applied, self.sent_at = (0, 0), self.started
        try:
            self.hardware.initialize()
            while not self.stop_event.is_set():
                before = self.clock()
                self.step()
                self.stop_event.wait(max(0, self.period-(self.clock()-before)))
        except BaseException as exc:
            self.error = f'{type(exc).__name__}: {exc}'
            self.fault_sensor_sample = self.last_received
            self.fault_packet_hex = getattr(self.hardware, 'last_packet_hex', None)
        finally:
            # Measured final stop while Full, bounded; restore Passive even on failure.
            try:
                self.hardware.drive(0, 0)
                until = self.clock()+1.5
                previous = None
                quiet = 0
                while self.clock() < until:
                    row = self.hardware.poll()
                    counts = (row['left_encoder_counts'], row['right_encoder_counts'])
                    quiet = quiet+1 if previous is not None and all(abs(encoder_delta(a,b)) <= 1 for a,b in zip(counts,previous)) else 0
                    if quiet >= 5:
                        self.shutdown_stopped = True
                        break
                    previous = counts
                    time.sleep(PERIOD)
            except Exception as exc:
                self.cleanup_errors.append('stop verification: '+str(exc))
            self.cleanup_errors.extend(self.hardware.cleanup())


class Recorder:
    def __init__(self, directory, manifest):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.manifest = manifest
        self.rows = []
        self.csvfile = (self.directory/'samples.csv').open('w', newline='')
        self.events = (self.directory/'events.jsonl').open('w')
        self.writer = None
        self.previous_context = None
        self.previous_cliffs = None
        self.event('session', **manifest)
        self.save_manifest()

    def event(self, name, **fields):
        self.events.write(json.dumps(dict(event=name, **fields))+'\n')
        self.events.flush()

    def save_manifest(self):
        (self.directory/'manifest.json').write_text(json.dumps(self.manifest, indent=2)+'\n')

    def sample(self, row):
        if self.writer is None:
            self.writer = csv.DictWriter(self.csvfile, fieldnames=list(row))
            self.writer.writeheader()
        self.writer.writerow(row)
        self.rows.append(row)
        cliffs = {key: row[key] for key in ('cliff_left_sensor', 'cliff_front_left_sensor',
                                           'cliff_front_right_sensor', 'cliff_right_sensor')}
        if self.previous_cliffs is not None and cliffs != self.previous_cliffs:
            self.event('cliff_change', at=row['monotonic_s'], stage=row['stage'],
                       before=self.previous_cliffs, after=cliffs,
                       signals={key: row[key] for key in ('cliff_left_signal', 'cliff_front_left_signal',
                                                        'cliff_front_right_signal', 'cliff_right_signal')})
        self.previous_cliffs = cliffs
        context = (row['stage'], row['phase'])
        if context != self.previous_context:
            self.event('phase', at=row['monotonic_s'], stage=row['stage'], label=row['label'], phase=row['phase'])
            self.csvfile.flush()
            self.previous_context = context

    def finish(self, result, reason, hardware=None, owner=None):
        self.manifest.update(result=result, reason=reason, samples=len(self.rows))
        self.manifest['recorded_seconds'] = (self.rows[-1]['monotonic_s']-self.rows[0]['monotonic_s']
                                             if len(self.rows) > 1 else 0.)
        if hardware is not None:
            self.manifest.update(startup_text_observed=hardware.startup_text,
                                 last_packet_hex=getattr(hardware, 'last_packet_hex', None),
                                 last_sensor_sample=getattr(hardware, 'last_sensor_sample', None),
                                 startup_note='No reset performed; boot/firmware text may be absent.')
            for command in hardware.commands:
                self.event('serial_send', **command)
        if owner is not None:
            self.manifest.update(stop_verified=owner.shutdown_stopped, cleanup_errors=owner.cleanup_errors,
                                 fault_sensor_sample=owner.fault_sensor_sample,
                                 fault_packet_hex=owner.fault_packet_hex)
        self.event('result', result=result, reason=reason)
        self.save_manifest()
        self.csvfile.close()
        self.events.close()
        try:
            make_report(self.directory, self.rows, self.manifest)
        except Exception as exc:
            # Hardware is already stopped; retain recordings if plotting fails.
            (self.directory/'report-error.txt').write_text(str(exc)+'\n')


def stage_statistics(rows):
    results = []
    groups = {}
    for row in rows:
        if row['stage'] >= 0:
            groups.setdefault(row['stage'], []).append(row)
    for index, samples in sorted(groups.items()):
        item = dict(stage=index, label=samples[0]['label'])
        for wheel in ('left', 'right'):
            hold = [r for r in samples if r['phase'] == 'hold' and r[wheel+'_mm_s'] is not None]
            startup = [r for r in samples if r['phase'] in ('startup', 'hold')]
            rest = [r for r in samples if r['phase'] == 'settle']
            commanded = next((r['command_'+wheel] for r in startup), 0)
            vals = [r[wheel+'_mm_s'] for r in hold]
            item[wheel+'_command'] = commanded
            item[wheel+'_mean'] = statistics.mean(vals) if vals else None
            item[wheel+'_sd'] = statistics.pstdev(vals) if vals else None
            item[wheel+'_error'] = statistics.mean(vals)-commanded if vals else None
            item[wheel+'_peak_current_ma'] = max((abs(r[wheel+'_motor_current']) for r in samples), default=None)
            moving = next((r for r in startup if r[wheel+'_mm_s'] is not None and abs(r[wheel+'_mm_s']) > 10), None)
            item[wheel+'_start_delay_s'] = moving['monotonic_s']-startup[0]['command_sent_s'] if moving and startup else None
            item[wheel+'_coast_ticks'] = sum(abs(r[wheel+'_ticks_delta'] or 0) for r in rest)
            # Time to first sustained quiet half-second following the stop command.
            quiet_since = None
            stopped_at = None
            for r in rest:
                if r[wheel+'_mm_s'] is not None and abs(r[wheel+'_mm_s']) <= 10:
                    if quiet_since is None:
                        quiet_since = r['monotonic_s']
                    if r['monotonic_s']-quiet_since >= .5:
                        stopped_at = quiet_since
                        break
                else:
                    quiet_since = None
            item[wheel+'_stop_delay_s'] = stopped_at-rest[0]['command_sent_s'] if stopped_at and rest else None
        results.append(item)
    return results


def make_report(directory, rows, manifest):
    directory = Path(directory)
    stages = stage_statistics(rows)
    if stages:
        with (directory/'stage-summary.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(stages[0]))
            writer.writeheader()
            writer.writerows(stages)
    intervals = [r['interval_s'] for r in rows if r['interval_s'] is not None]
    mean = statistics.mean(intervals) if intervals else None
    lines = ['# Pit-stop report', '', f"Result: **{manifest['result']}** — {manifest['reason']}", '',
             f"Build {VERSION}; simulated: {manifest['simulated']}; samples: {len(rows)}.",
             f'Mean polling interval: {mean:.4f} s ({1/mean:.1f} Hz).' if mean else 'No polling intervals.', '',
             'Unloaded encoder compliance only: this does not measure chassis travel, floor traction, or caster movement.',
             'Raw stasis/drop/cliff states are retained; absent fields are never replaced with zeros.', '',
             'Per-stage speed error, variability, current peaks, startup/stop delay and coast ticks: stage-summary.csv.', '',
             '| Stage | Left requested / measured mm/s | Right requested / measured mm/s |', '|---|---:|---:|']
    def number(value):
        return '—' if value is None else f'{value:.1f}'
    for s in stages:
        lines.append(f"| {s['label']} | {s['left_command']} / {number(s['left_mean'])} | {s['right_command']} / {number(s['right_mean'])} |")
    (directory/'report.md').write_text('\n'.join(lines)+'\n')
    if not rows:
        return
    try:
        os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir())/'roomberry-pit-matplotlib'))
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
        x = [r['monotonic_s']-rows[0]['monotonic_s'] for r in rows]
        for wheel, color in (('left', 'tab:blue'), ('right', 'tab:orange')):
            axes[0].plot(x, [r['command_'+wheel] for r in rows], '--', color=color, alpha=.5, label=wheel+' requested')
            axes[0].plot(x, [r[wheel+'_mm_s'] for r in rows], color=color, lw=.7, label=wheel+' encoder')
            axes[1].plot(x, [r[wheel+'_motor_current'] for r in rows], color=color, lw=.7, label=wheel)
        axes[0].set_ylabel('Wheel mm/s')
        axes[1].set_ylabel('Motor mA')
        axes[2].plot(x, [r['interval_s'] for r in rows], lw=.7)
        axes[2].set_ylabel('Poll interval s')
        axes[2].set_xlabel('Elapsed seconds')
        for ax in axes:
            ax.grid(alpha=.25)
        axes[0].legend(ncol=4)
        axes[1].legend()
        fig.suptitle('SIMULATED — pit-stop' if manifest['simulated'] else 'Pit-stop — suspended wheels')
        fig.tight_layout()
        fig.savefig(directory/'telemetry.png', dpi=140)
        plt.close(fig)
    except ImportError:
        with (directory/'report.md').open('a') as stream:
            stream.write('\nPlot omitted: install matplotlib or generate from samples.csv on another computer.\n')


def live_run(args, recorder, stages):
    hardware = SerialBench(args.port, args.baud)
    owner = Owner(hardware)
    interrupted = threading.Event()
    old_handlers = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        old_handlers[sig] = signal.signal(sig, lambda *_: interrupted.set())
    started = time.monotonic()
    seq = Sequencer(stages, started)
    result, reason = 'aborted', 'operator stop'
    owner.start()
    try:
        last = started
        last_stage = -2
        while not interrupted.is_set():
            if owner.error:
                raise BenchFault(owner.error)
            now = time.monotonic()
            if now-started >= MAX_SECONDS:
                raise BenchFault('20-minute runtime limit')
            try:
                row = owner.samples.get(timeout=.1)
            except queue.Empty:
                if now-last >= .5:
                    raise BenchFault('no fresh sensor samples')
                owner.publish((0, 0), seq.context())
                continue
            recorder.sample(row)
            last = row['monotonic_s']
            if time.monotonic()-last > .3:
                raise BenchFault('telemetry backlog / stale sequence sample')
            command = seq.update(last, row)
            owner.publish(command, seq.context())
            if seq.index != last_stage and not seq.done:
                print(f"{last-started:6.1f}s  {seq.index+1}/{len(stages)} {seq.context()['label']}", flush=True)
                last_stage = seq.index
            if seq.done:
                result, reason = 'complete', 'all planned stages complete'
                break
    except Exception as exc:
        reason = str(exc)
    finally:
        owner.stop_event.set()
        owner.join(timeout=5)
        if owner.is_alive():
            result, reason = 'aborted', 'serial owner failed to exit; physical stop may be necessary'
        elif owner.error:
            result, reason = 'aborted', owner.error
        elif not owner.shutdown_stopped or owner.cleanup_errors:
            result, reason = 'aborted', 'final stop/cleanup not verified; inspect manifest'
        while not owner.samples.empty():
            recorder.sample(owner.samples.get_nowait())
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        recorder.finish(result, reason, hardware, owner)
        print(f'{result.upper()}: {reason}')
    return 0 if result == 'complete' else 1


def simulate(recorder, stages):
    """Accelerated, explicitly synthetic telemetry through the same sequencer."""
    seq = Sequencer(stages, 0.)
    counts, speeds = [0., 0.], [0., 0.]
    command = (0, 0)
    sent = now = 0.
    previous = None
    try:
        while not seq.done:
            raw = bytearray(80)
            raw[0], raw[40] = 12, 3
            import struct
            struct.pack_into('>HhbHH', raw, 17, 15000, -200, 25, 2000, 3000)
            for i in range(2):
                speeds[i] += (command[i]-speeds[i])*(1-math.exp(-PERIOD/.12))
                counts[i] += speeds[i]*PERIOD/TICK_MM
                struct.pack_into('>H', raw, 52+2*i, round(counts[i]) % 65536)
                struct.pack_into('>h', raw, 71+2*i, round(40+abs(speeds[i])*1.5))
            struct.pack_into('>hh', raw, 48, command[1], command[0])
            row = decode(bytes(raw))
            row.update(seq.context(), monotonic_s=now, sensor_requested_s=now,
                       sensor_age_s=0., interval_s=PERIOD if previous else None,
                       target_period_s=PERIOD,
                       command_left=command[0], command_right=command[1], command_sent_s=sent,
                       wall_time='SIMULATED')
            for i, wheel in enumerate(('left', 'right')):
                delta = encoder_delta(row[wheel+'_encoder_counts'], previous[wheel+'_encoder_counts']) if previous else None
                row[wheel+'_ticks_delta'] = delta
                row[wheel+'_ticks_s'] = delta/PERIOD if delta is not None else None
                row[wheel+'_mm_s'] = delta*TICK_MM/PERIOD if delta is not None else None
            check_sample(row)
            recorder.sample(row)
            previous = row
            next_command = seq.update(now, row)
            if next_command != command:
                command, sent = next_command, now
                recorder.event('simulated_command', at=now, left=command[0], right=command[1])
            now = round(now+PERIOD, 6)
        recorder.finish('complete', 'synthetic profile complete; no hardware accessed')
        return 0
    except Exception as exc:
        recorder.finish('aborted', str(exc))
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--run', action='store_true', help='open hardware; requires interactive bench arming')
    action.add_argument('--simulate', action='store_true', help='accelerated synthetic run; no serial access')
    parser.add_argument('--profile', choices=('20m', 'smoke'), default='20m')
    parser.add_argument('--port', default='/dev/serial0')
    parser.add_argument('--baud', type=int, choices=(115200, 57600, 19200), default=115200)
    parser.add_argument('--output', type=Path, help='new session directory; never overwrites existing output')
    args = parser.parse_args(argv)
    stages = schedule(args.profile)
    duration = BASELINE+len(stages)*SLOT
    print(f'{VERSION}: {args.profile}, {len(stages)} stages, nominal {duration/60:.2f} minutes; hard limit 20 minutes.')
    if not args.run and not args.simulate:
        print('DRY RUN: no serial device opened. Commands below are left/right mm/s.')
        for i, stage in enumerate(stages):
            print(f'{i+1:3} {BASELINE+i*SLOT:6.1f}s {stage.label:24} {stage.left:4} {stage.right:4}')
        return 0
    if args.run:
        if not os.isatty(0):
            parser.error('--run requires an interactive terminal for fresh bench arming')
        print('Stop roomberry.service. Support chassis securely with BOTH wheels freely hanging.\n'
              'Full OI mode disables cliff/wheel-drop protection. Keep power cutoff accessible.\n'
              'Clean/any robot button, Ctrl-C or SIGTERM stops this test. No automatic rearm.')
        if input(f'Type {ARM_PHRASE!r} to arm this bench session: ') != ARM_PHRASE:
            print('Not armed; no serial device opened.')
            return 1
    directory = args.output or Path('output')/('pit-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    manifest = dict(version=VERSION, simulated=args.simulate, profile=args.profile,
                    port=None if args.simulate else args.port, baud=args.baud,
                    nominal_seconds=duration, hard_limit_seconds=MAX_SECONDS,
                    target_hz=1/PERIOD, tick_to_mm=TICK_MM, ticks_per_revolution=ROBOT.TICK_PER_REV,
                    wheel_diameter_mm=ROBOT.WHEEL_DIAMETER,
                    conversion_note='Nominal wheel geometry; raw encoder ticks retained.',
                    startup_seconds=.5, hold_seconds=2., stage_seconds=SLOT,
                    stages=[asdict(stage) for stage in stages])
    recorder = Recorder(directory, manifest)
    try:
        status = simulate(recorder, stages) if args.simulate else live_run(args, recorder, stages)
    except Exception as exc:
        recorder.finish('aborted', str(exc))
        status = 1
    print(f'Results: {directory}/report.md')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
