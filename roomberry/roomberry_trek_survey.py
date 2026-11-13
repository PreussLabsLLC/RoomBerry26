"""Pi-owned RoomTrek survey lifecycle, independent of the robot control loop."""
# @(#)roomberry_trek_survey.py 3.2.maps.4 2026/11/10 11:24:31
from datetime import datetime
import json
import logging
from queue import Queue, Empty, Full
from pathlib import Path
import os
import socket
from threading import Thread, Event, Lock, RLock
from time import monotonic
import uuid

from roomberry_speech import phrase
from roomberry_trek_control import encode, decode, MAX_DATAGRAM


class TrekSurveyController:
    def __init__(self, key, port, logger, map_prefix='kitchen', command=None, date=None, startup_warning=None, seed_map_id=None, selection_path=None):
        self.key, self.port, self.logger = key, port, logger
        self.startup_warning = startup_warning
        self._warning = ''
        self.map_prefix = map_prefix
        self.command = command or self._command
        self.date = date or (lambda: datetime.now().strftime('%y%m%d'))
        self._queue = Queue(maxsize=8)
        self._stop = Event()
        self._thread = None
        self._mode_lock = Lock()
        self._active = False
        self._survey = None
        self._last_map = None
        self._error = ''
        self._state = 'idle'
        self._target = None
        self._previous_maps = set()
        self.seed_map_id = seed_map_id
        self._parent_map_id = None
        self._saved_map_id = None
        self._start_attempt = 0
        self._phone_session = None
        self._operator_survey = None
        self.operation_lock = RLock()
        self.selection_path = Path(selection_path) if selection_path else None
        self.selected_map_id = None
        self.selection_error = ''
        if self.selection_path and self.selection_path.exists():
            # Refuse an unreadable override rather than silently using another map.
            try:
                self.selected_map_id = json.loads(self.selection_path.read_text())['map_id']
                if self.selected_map_id is not None:
                    self.selected_map_id = str(uuid.UUID(self.selected_map_id)).upper()
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                self.selected_map_id = None
                self.selection_error = 'Saved mission map selection unreadable; choose a map in the web console: '+str(error)

    def select_map(self, map_id):
        """Called with operation_lock held, after library verification."""
        if map_id is not None:
            map_id = str(uuid.UUID(map_id)).upper()
        if self.selection_path:
            self.selection_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.selection_path.with_suffix('.tmp')
            try:
                temporary.write_text(json.dumps(dict(map_id=map_id))+'\n')
                os.replace(temporary, self.selection_path)
            finally:
                temporary.unlink(missing_ok=True)
        self.selected_map_id = map_id
        self.selection_error = ''

    def selection_snapshot(self):
        return dict(map_id=self.selected_map_id, policy='selected' if self.selected_map_id else 'automatic',
                    seed_map_id=self.seed_map_id, persistent=self.selection_path is not None, error=self.selection_error)

    def keep_operator_survey(self, phone):
        """An explicit console survey survives manual steering and Stop / idle."""
        if not phone.get('running') or phone.get('mode') != 'survey':
            raise ValueError('Start a Surveyor session before keeping it for steering')
        with self._mode_lock:
            self._operator_survey = dict(session=phone.get('session'), map_id=phone.get('map_id'), saved_id=None)

    def release_operator_survey(self):
        with self._mode_lock:
            self._operator_survey = None

    def operator_survey_saved(self, map_id):
        with self._mode_lock:
            if self._operator_survey is not None:
                self._operator_survey = dict(self._operator_survey, saved_id=map_id)

    def guard_operator_survey(self, mode):
        with self._mode_lock:
            if (mode not in ('idle', 'remote_control', 'return_to_tag15') and self._operator_survey is not None
                    and not self._operator_survey['saved_id']):
                raise RuntimeError('Save the current phone survey or Stop phone session before starting a mission; use the steering pad to collect coverage')

    def start(self):
        if self._thread is None:
            self._thread = Thread(target=self._run, name='RoomTrekSurvey', daemon=True)
            self._thread.start()

    def mode_changed(self, mode):
        active = mode != 'idle'
        with self._mode_lock:
            # Manual controls do not own the phone lifecycle. In particular,
            # preserve a locally started survey after a Pi restart even when
            # the operator has not used the console's Keep action. A takeover
            # from an autonomous run still closes that run's survey at idle.
            if mode in ('remote_control', 'return_to_tag15') and not self._active:
                return
            if self._operator_survey is not None:
                if mode in ('idle', 'remote_control', 'return_to_tag15'):
                    return  # No AR stop/restart or automatic save for manual survey steps.
                self._operator_survey = None
            if active == self._active:
                return
            try:
                self._queue.put_nowait(('start' if active else 'save', self.map_prefix+'-'+self.date()))
            except Full:
                self._report('failed', 'Survey lifecycle queue full; action not dispatched')
                return
            self._active = active
            if active: self._report('connecting', 'Waiting for authenticated phone')

    def _report(self, state, detail):
        backgrounded = 'app must be foreground' in detail.lower()
        if backgrounded:
            self._warning = phrase('PHONE_BG')
            if self.startup_warning is not None:
                try: self.startup_warning()
                except Exception:
                    self.logger.exception('RoomTrek startup warning beep failed', extra=dict(speech_announce=False))
        elif state == 'surveying':
            self._warning = ''
        self._state = state
        if state in ('failed', 'unknown', 'unavailable'):
            self._error = detail
        level = logging.WARNING if state in ('failed', 'unknown', 'unavailable') else logging.INFO
        self.logger.log(level, 'RoomTrek survey status=%s detail=%s', state, detail,
                        extra=dict(speech_code='PHONE_BG' if backgrounded else 'MAP_READY' if state=='saved' else 'PHONE_LOST' if state=='unavailable' else 'STATUS',
                                   speech_announce=not backgrounded and state in ('saved','unavailable')))

    def snapshot(self):
        return dict(status=self._state, map_name=self._survey or self._last_map, error=self._error, warning=self._warning, start_attempt=self._start_attempt, phone_session=self._phone_session, parent_map_id=self._parent_map_id, saved_map_id=self._saved_map_id, selection=self.selection_snapshot(), operator_survey=self._operator_survey)

    def _command(self, command_name, **arguments):
        body = dict(kind='command', id=str(uuid.uuid4()), command=command_name, **arguments)
        if self._target is not None:
            body['target'] = self._target
        deadline = monotonic()+(45 if command_name == 'SURVEY_START' and arguments.get('map_id') else 25)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('127.0.0.1', self.port)); sock.settimeout(1)
            while not self._stop.is_set() and monotonic() < deadline:
                sock.send(encode(body, self.key))
                try:
                    reply = decode(sock.recv(MAX_DATAGRAM+1), self.key)
                except (socket.timeout, ValueError):
                    continue
                if reply.get('kind') != 'response' or reply.get('id') != body['id']:
                    continue
                if reply.get('target'):
                    body['target'] = reply['target']
                    self._target = reply['target']
                if reply.get('status') in ('completed', 'failed', 'unavailable'):
                    return reply
                self._stop.wait(.25)
        return dict(status='unknown', detail='Command result timeout; not replayed with a new ID')

    def _require(self, command_name, **arguments):
        reply = self.command(command_name, **arguments)
        if reply.get('status') != 'completed':
            self._report(reply.get('status', 'failed'), command_name+': '+reply.get('detail', 'No result'))
            return None
        self.logger.info('RoomTrek survey command=%s status=completed id=%s', command_name, reply.get('id'),
                         extra=dict(speech_announce=False))
        return reply

    def _start_survey(self, name):
        self._survey = None
        self._parent_map_id = None
        self._phone_session = None
        self._start_attempt = 0
        self._error = ''
        if self.selection_error:
            self._report('failed', self.selection_error)
            return
        self._target = None
        self._report('connecting', 'Waiting for authenticated phone')
        deadline = monotonic()+12
        while not self._stop.is_set():
            status = self.command('STATUS', **(dict(map_id=self.selected_map_id) if self.selected_map_id else dict(map_prefix=self.map_prefix)))
            if status.get('status') == 'completed':
                break
            if status.get('status') != 'unavailable' or monotonic() >= deadline:
                self._report(status.get('status', 'failed'), status.get('detail', 'Phone unavailable'))
                return
            self._stop.wait(1)
        if self._stop.is_set(): return
        try:
            inventory = json.loads(status.get('detail', '{}'))
            if inventory.get('map_inventory_errors', 0):
                raise ValueError('Unreadable map packages; existing maps preserved, fresh start refused')
            maps = inventory['maps']
            if not isinstance(maps, list): raise ValueError('maps must be a list')
            self._previous_maps = {entry['id'] for entry in maps}
            if 'survey_resume_v1' not in inventory.get('capabilities', []):
                raise ValueError('RoomTrek update required: survey_resume_v1 unavailable')
            candidates = [entry for entry in maps if entry.get('name') == self.map_prefix
                          or entry.get('name', '').startswith(self.map_prefix+'-')]
            # STATUS is newest-first; explicit timestamps also support unsorted fixtures.
            candidates.sort(key=lambda entry: (bool(entry.get('parent_map_id')), entry.get('mapping') in ('mapped', 'extending'), entry.get('created', 0)), reverse=True)
            parent = candidates[0]['id'] if candidates else None
            if self.seed_map_id and not any(entry.get('parent_map_id') for entry in candidates):
                parent = self.seed_map_id
            if self.selected_map_id:
                if not any(entry.get('id', '').upper() == self.selected_map_id for entry in maps):
                    raise ValueError('Selected mission map is missing; choose a map in the web console')
                parent = self.selected_map_id
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            self._report('failed', 'Map inventory unavailable: '+str(error))
            return
        self._parent_map_id = parent
        if self._require('SESSION_STOP') is None: return
        if parent:
            for attempt in (1, 2):
                self._start_attempt = attempt
                self._report('relocalizing' if attempt == 1 else 'restarting',
                             'Resuming kitchen map '+parent+' attempt='+str(attempt)+'/2')
                reply = self.command('SURVEY_START', map_id=parent)
                if reply.get('status') == 'completed':
                    self.logger.info('RoomTrek survey command=SURVEY_START status=completed id=%s', reply.get('id'),
                                     extra=dict(speech_announce=False))
                    break
                detail = reply.get('detail', 'No result')
                retryable = reply.get('status') == 'failed' and any(
                    reason in detail for reason in ('relocalization_timeout', 'tracking_failure'))
                if attempt == 1 and retryable:
                    self.logger.warning('RoomTrek startup attempt1 failed: %s; one stopped-session retry', detail,
                                        extra=dict(speech_code='RECOVER', speech_announce=True))
                    # An acknowledged stop resolves the old operation before
                    # issuing a distinct intentional restart, with a new ID.
                    self._report('restarting', detail)
                    if self._require('SESSION_STOP') is None: return
                    if self._thread is not None and not self._active:
                        self._report('failed', 'Startup cancelled while restarting; phone remains stopped')
                        return
                    continue
                self._report(reply.get('status', 'failed'), 'SURVEY_START: '+detail)
                self._require('SESSION_STOP')
                return
        else:
            self._start_attempt = 1
            reply = self._require('SURVEY_START')
            if reply is None: return
        session = reply.get('operation', {}).get('session')
        self._phone_session = str(session) if session is not None else None
        self._survey = name
        self._last_map = name
        self._report('surveying', name)

    def _save_survey(self):
        if self._survey is None:
            return
        name = self._survey
        self._report('saving', name)
        saved = self._require('SURVEY_SAVE', name=name)
        if saved is not None:
            try: saved_id = json.loads(saved.get('detail', '{}')).get('map_id')
            except (ValueError, AttributeError): saved_id = None
            # Verify persisted library metadata, not just command dispatch.
            verified = self._require('STATUS', map_prefix=self.map_prefix)
            maps = []
            if verified is not None:
                try: maps = json.loads(verified.get('detail', '{}')).get('maps', [])
                except (ValueError, AttributeError): pass
            if not isinstance(maps, list): maps = []
            revisions = [entry for entry in maps if isinstance(entry, dict) and entry.get('name') == name
                         and entry.get('id') == saved_id and saved_id not in self._previous_maps
                         and entry.get('parent_map_id', '') == (self._parent_map_id or '')]
            if revisions:
                self._saved_map_id = revisions[0]['id']
                self._report('saved', name+' revision='+str(revisions[0].get('revision', 1))+' id='+self._saved_map_id)
            else:
                self._report('failed', 'Save acknowledged but map name not confirmed in STATUS: '+name)
        stopped = self._require('SESSION_STOP')
        self._survey = None
        if stopped is None: self._report('failed', 'Phone session stop not confirmed after save')

    def _run(self):
        while not self._stop.is_set():
            try: action, name = self._queue.get(timeout=.2)
            except Empty: continue
            try:
                with self.operation_lock:
                    if action == 'start': self._start_survey(name)
                    else: self._save_survey()
            except Exception as error:
                self._report('failed', str(error))
            finally:
                self._queue.task_done()

    def close(self):
        # Called after robot shutdown. Allow queued map save before relay closes.
        self.mode_changed('idle')
        if self._thread is not None:
            with self._queue.all_tasks_done:
                self._queue.all_tasks_done.wait_for(lambda: self._queue.unfinished_tasks == 0, timeout=30)
            self._stop.set()
            self._thread.join(timeout=2)
            self._thread = None
