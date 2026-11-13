"""Roomberry mnemonic speech catalogue and nonblocking RoomTrek speech delivery."""
# @(#)roomberry_speech.py 3.2.speechlog.1 2026/11/12 16:13:04
import json
import logging
from math import isfinite
from collections import OrderedDict
from queue import Queue, Empty, Full
import socket
from threading import Event, Thread, Lock
from time import monotonic
import uuid

from roomberry_trek_control import encode, decode, MAX_DATAGRAM

# Keep language text here, separate from mission logic. Age/gender are selected
# by listening to the installed RoomTrek voices, not inferred from these words.
PHRASES = {'en-AU': {
    'IDLE': "Righto, Captain. Standing by.",
    'REMOTE': "You're at the wheel now, Captain!",
    'DISCOVER': "Let's have a squiz around, Captain!",
    'CLEAN': "Time to tidy up, Captain!",
    'HOME': "Heading back to base, Captain!",
    'RECOVER': "Hang on, Captain. I'll get my bearings.",
    'CALIBRATE': "Just checking my moves, Captain!",
    'GRID': "Off along the grid, Captain!",
    'WALL': "Following the wall, nice and steady, Captain!",
    'LOW_BATT': "G’day, Captain! I’m running a bit low on juice!",
    'CRIT_BATT': "Captain, my battery's nearly flat. I've stopped to save juice.",
    'CHARGING': "On the charger, Captain. Topping up the juice!",
    'SCAN': "Hold tight, Captain. Just having a look around.",
    'SCAN_RESULT': "Tag scan complete, Captain.",
    'STATUS': "Righto, Captain. Here's the latest update.",
    'SAFETY': "Steady on, Captain! Safety stop. Please check around me.",
    'ERROR': "Something's not quite right, Captain. Please check the log.",
    'ANCHOR_OK': "Tag sixteen's lined up, Captain. Off we go!",
    'WALL_FOUND': "Found the wall, Captain. Nice and steady.",
    'WALL_LOST': "Lost the wall for a tick, Captain. Having another look.",
    'SEARCH_WALL': "Easy does it, Captain. Looking for the wall again.",
    'WALL_BACK': "There's the wall, Captain. Back on track!",
    'FRIDGE_AROUND': "Bit of a corner here, Captain. Going around to the left.",
    'CONTACT_CLEAR': "Touched something, Captain. Backing clear before turning.",
    'BYPASS_DONE': "Around that bit now, Captain. Carrying on!",
    'IR_UNSTEADY': "The wall reading's a bit jumpy. Holding still for a tick.",
    'NEAR_TAG15': "Let's check tag fifteen, Captain. Stopping for a proper look.",
    'TAG15_APPROACH': "Tag fifteen's in sight, Captain. Moving a little closer.",
    'TAG15_VALIDATED': "Within thirty centimetres and tag fifteen checked, Captain!",
    'RUN_DONE': "All done, Captain. That's the validation run wrapped up.",
    'RUN_STOPPED': "I've stopped the run, Captain. Please check the log.",
    'MAP_READY': "Kitchen map saved, Captain. Ready for the next outing!",
    'PHONE_BG': "Captain, please open RoomTrek on the phone. Mapping hasn't started.",
    'PHONE_LOST': "Can't reach the phone, Captain. Please check RoomTrek.",
}}
MODE_CODES = dict(idle='IDLE', remote_control='REMOTE', discovery='DISCOVER',
                  clean='CLEAN', return_to_base='HOME', recovery='RECOVER',
                  calibration='CALIBRATE', gridrunner='GRID', wall='WALL')
BATTERY_CODES = dict(low='LOW_BATT', critical='CRIT_BATT', charging='CHARGING')


def phrase(code, language='en-AU'):
    """Unknown languages/codes are explicit configuration errors, never spoken IDs."""
    return PHRASES[language][code]


def battery_announcement(robot, receiver, now=None):
    """Use fresh robot sensors and the authenticated phone heartbeat, even in idle."""
    now = monotonic() if now is None else now
    relay = None if receiver is None else receiver.trek_control
    if relay is None or relay.peer is None or not 0 <= now-relay.last_peer <= 10:
        return None
    state = robot.snapshot()
    sensors = state.get('sensors')
    age = state.get('age')
    roomba = None
    if sensors is not None and isinstance(age, (int, float)) and 0 <= age <= 2:
        charge, capacity = sensors.battery_charge, sensors.battery_capacity
        if (isinstance(charge, (int, float)) and isinstance(capacity, (int, float))
                and isfinite(charge) and isfinite(capacity) and 0 <= charge <= capacity and capacity > 0):
            roomba = round(100*charge/capacity)
    phone = relay.operation.get('battery_percent')
    if not isinstance(phone, (int, float)) or isinstance(phone, bool) or not 0 <= phone <= 100:
        phone = None
    if roomba is None and phone is None: return None
    robot_text = 'Roomba battery reading unavailable' if roomba is None else 'Roomba battery {} percent{}'.format(roomba, ', charging' if state.get('charging') else '')
    phone_text = 'iPhone battery reading unavailable' if phone is None else 'iPhone battery {} percent{}'.format(round(phone), ', charging' if relay.operation.get('battery_state') in (2, 3) else '')
    return 'Captain, '+robot_text+'. '+phone_text+'.'


def scan_announcement(report, mapped_tags=None, min_margin=10.0, max_pose_error=10.0):
    """Detector read quality, not a claim of localization or AR map accuracy."""
    if report.get('detection_skipped'):
        return 'Tag scan skipped while moving, Captain.'
    if report.get('detector_error'):
        return 'Tag scan failed, Captain. Please check the log.'
    known = None if mapped_tags is None else set(map(tuple, mapped_tags))
    best = {}
    for row in report.get('tags', ()):
        if not isinstance(row, dict) or not isinstance(row.get('id'), int) or isinstance(row['id'], bool):
            continue
        key = (row.get('family', 'tag16h5'), row['id'])
        margin, hamming = row.get('decision_margin'), row.get('hamming')
        error = (row.get('tag_pose_camera') or {}).get('error')
        complete = all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)
                       for v in (margin, hamming, error))
        if not complete:
            score, label = 1, 'quality unavailable'
        elif hamming != 0 or margin < min_margin or error > max_pose_error or error < 0:
            score, label = 0, 'weak read'
        elif margin < 2*min_margin or error > max_pose_error/2:
            score, label = 2, 'marginal read'
        else:
            score, label = 3, 'clear read'
        item = (score, known is None or key in known, float(margin) if complete else -1, label, row)
        if key not in best or item[:3] > best[key][:3]: best[key] = item
    if not best:
        return 'No tags found, Captain.'
    candidates = sorted(best.values(), key=lambda x:x[:3], reverse=True)
    readable = [x for x in candidates if x[0] > 0]
    if not readable:
        return 'No reliable tag, Captain. Weak detections only.'
    # Prefer surveyed tags when their read quality is at least marginal.
    mapped = [x for x in readable if x[1] and x[0] >= 2]
    selected = (mapped or readable)[:2]
    descriptions = []
    for score, is_mapped, margin, label, row in selected:
        description = '{}tag {}, {}'.format('' if is_mapped else 'unmapped ', row['id'], label)
        distance = row.get('distance_mm')
        if isinstance(distance, (float, int)) and not isinstance(distance, bool) and isfinite(distance) and distance > 0:
            description += '. Camera range {} centimetres'.format(max(1, round(distance/10)))
        descriptions.append(description)
    return 'Captain, '+'. '.join(descriptions)+'.'


class SpeechLogFilter(logging.Filter):
    """Tag all records; announce semantic events/errors with per-code cooldown.

    No network I/O on the logging/robot thread. Other diagnostics retain
    original details, tagged STATUS or ERROR, without narrating every tick.
    """
    def __init__(self, send=None, language='en-AU', cooldown=30):
        super().__init__()
        self.send = send
        self.language = language
        self.cooldown = cooldown
        self._last = {}
        self._lock = Lock()

    def filter(self, record):
        if getattr(record, '_speech_tagged', False):
            return True
        code = getattr(record, 'speech_code', 'ERROR' if record.levelno >= logging.WARNING or record.exc_info else 'STATUS')
        if code not in PHRASES[self.language]:
            code = 'ERROR'
        text = phrase(code, self.language)
        record.speech_code = code
        record.speech_text = text
        record.msg = '[%s] %s' % (code, record.msg)
        record._speech_tagged = True
        announce = getattr(record, 'speech_announce', record.levelno >= logging.WARNING or bool(record.exc_info))
        if announce and self.send is not None:
            now = monotonic()
            with self._lock:
                previous = self._last.get(code)
                if previous is not None and now-previous < self.cooldown:
                    return True
                self._last[code] = now
            # The sink must only enqueue; transport errors never affect motion.
            try:
                self.send(code, text)
            except Exception:
                pass  # A logging filter must not interrupt robot safety handling.
        return True


class SpeechSender:
    """Bounded worker using an ephemeral loopback client, existing Pi UDP relay.

    Never binds a second service port or sends directly to an unverified phone.
    Retries preserve ID and pin target after ACK. Queue expires quickly offline.
    """
    def __init__(self, key, port, logger, language='en-AU', battery_status=None, quiet_seconds=30, scan_quality=None):
        self.key, self.port, self.logger, self.language = key, port, logger, language
        self._queue = Queue(maxsize=4)
        self._stop = Event()
        self._thread = None
        self._results = OrderedDict()
        self._results_lock = Lock()
        self._enqueue_lock = Lock()
        self.battery_status = battery_status
        self.quiet_seconds = quiet_seconds
        self._quiet_since = monotonic()
        self._last_battery_attempt = self._quiet_since
        self.scan_quality = scan_quality or {}

    def start(self):
        if self._thread is None:
            self._thread = Thread(target=self._run, name='RoomberrySpeech', daemon=True)
            self._thread.start()

    def submit(self, code, text):
        if text != phrase(code, self.language):
            raise ValueError('Speech text must match catalogue')
        return self._enqueue(code, text)

    def submit_text(self, text):
        """Free text uses existing SPEAK; no extra catalogue slot or UDP type."""
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise ValueError('Speech text must contain 1–500 characters')
        return self._enqueue('STATUS', text)

    def submit_scan_result(self, report):
        text = scan_announcement(report, **self.scan_quality)
        command_id = self._enqueue('SCAN_RESULT', text)
        self.logger.info('Tag scan announcement id=%s text=%s', command_id, text,
                         extra=dict(speech_code='SCAN_RESULT', speech_announce=False))
        return command_id

    def _enqueue(self, code, text):
        command_id = str(uuid.uuid4())
        self._remember(command_id, code, 'queued', 'Waiting for speech worker', text=text)
        self._transcript(code, text, 'queued', command_id)
        priorities={'SAFETY':3,'RUN_STOPPED':2,'TAG15_VALIDATED':2,'RUN_DONE':1,'MAP_READY':1,'PHONE_LOST':1}
        with self._enqueue_lock:
            try:
                self._queue.put_nowait((code,text,monotonic(),command_id))
            except Full:
                priority=priorities.get(code,0)
                if priority:
                    try:
                        old_code,old_text,old_time,old_id=self._queue.get_nowait()
                        if priorities.get(old_code,0) >= priority:
                            self._queue.put_nowait((old_code,old_text,old_time,old_id))
                            self._log(code,'dropped','higher-priority speech already queued',command_id)
                        else:
                            self._log(old_code,'dropped','superseded by '+code,old_id)
                            self._queue.put_nowait((code,text,monotonic(),command_id))
                    except (Empty,Full): self._log(code,'dropped','speech queue full',command_id)
                else: self._log(code,'dropped','speech queue full',command_id)
        return command_id

    def _transcript(self, code, text, phase, command_id):
        # JSON quoting keeps a multiline/user-entered phrase on one log line.
        self.logger.info('Speech transcript code=%s phase=%s id=%s text=%s',
                         code, phase, command_id, json.dumps(text, ensure_ascii=False),
                         extra=dict(speech_code=code, speech_announce=False))

    def _remember(self, command_id, code, status, detail, text=None):
        if command_id is None:
            return
        with self._results_lock:
            prior = self._results.get(command_id, {})
            self._results[command_id] = dict(id=command_id, code=code, status=status,
                text=prior.get('text', '') if text is None else text,
                detail=detail, updated=monotonic())
            self._results.move_to_end(command_id)
            while len(self._results) > 64:
                self._results.popitem(last=False)

    def job_snapshot(self, command_id):
        with self._results_lock:
            result = self._results.get(command_id)
            if result is None:
                return None
            result = dict(result)
        result['age_s'] = max(0, monotonic()-result.pop('updated'))
        return result

    def _log(self, code, status, detail, command_id=None):
        if status in ('accepted', 'completed'):
            self._quiet_since = monotonic()
        self._remember(command_id, code, status, detail)
        if command_id:
            detail = '{} (id={})'.format(detail, command_id)
        self.logger.info('Speech delivery code=%s status=%s detail=%s', code, status, detail,
                         extra=dict(speech_code=code, speech_announce=False))

    def _deliver(self, code, text, command_id=None):
        command_id = command_id or str(uuid.uuid4())
        self._remember(command_id, code, 'sending', 'Starting speech delivery', text=text)
        self._transcript(code, text, 'attempt', command_id)
        command = dict(kind='command', id=command_id, command='SPEAK', text=text, speech_code=code)
        deadline = monotonic()+45
        acknowledged = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(('127.0.0.1', self.port)); sock.settimeout(1)
                while not self._stop.is_set() and monotonic() < deadline:
                    sock.send(encode(command, self.key))
                    try:
                        result = decode(sock.recv(MAX_DATAGRAM+1), self.key)
                    except (socket.timeout, ValueError):
                        continue
                    if result.get('kind') != 'response' or result.get('id') != command['id']:
                        continue
                    if result.get('target'):
                        command['target'] = result['target']
                    status = result.get('status')
                    if status in ('completed', 'failed', 'unavailable'):
                        self._log(code, status, result.get('detail', ''), command_id)
                        return
                    if status == 'accepted' and not acknowledged:
                        acknowledged = True
                        self._log(code, 'accepted', 'RoomTrek acknowledged SPEAK; waiting for completion', command_id)
                    self._stop.wait(0.5)
            if not self._stop.is_set():
                self._log(code, 'unknown', 'response timeout; not replayed with a new ID', command_id)
        except OSError as error:
            self._log(code, 'unavailable', str(error), command_id)

    def _run(self):
        while not self._stop.is_set():
            try:
                code, text, created, command_id = self._queue.get(timeout=0.2)
            except Empty:
                self._announce_batteries_if_quiet()
                continue
            if monotonic()-created > 10:
                self._log(code, 'dropped', 'stale announcement', command_id)
                continue
            self._deliver(code, text, command_id)

    def _announce_batteries_if_quiet(self, now=None):
        now = monotonic() if now is None else now
        if (self.battery_status is None or not self._queue.empty()
                or now-self._quiet_since < self.quiet_seconds
                or now-self._last_battery_attempt < self.quiet_seconds):
            return
        self._last_battery_attempt = now
        try:
            text = self.battery_status()
        except Exception:
            self.logger.exception('Battery announcement readings unavailable', extra=dict(speech_announce=False))
            return
        # Mission/safety announcements arriving during the reading take priority.
        if text and self._queue.empty() and not self._stop.is_set():
            self._deliver('STATUS', text)

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
