"""Asynchronous map-library jobs for the local console; never drives the robot."""
# @(#)roomberry_trek_maps.py 3.2.maps.2 2026/11/10 10:57:09
from contextlib import nullcontext
import copy
import json
from threading import Lock, Thread
from time import monotonic
import uuid


class TrekMapManager:
    ACTIONS = {'refresh', 'select', 'fresh', 'resume', 'save', 'stop', 'rename', 'delete', 'keep'}

    def __init__(self, survey, mission=None):
        self.survey, self.mission = survey, mission
        self._lock = Lock()
        self._thread = None
        self._busy = False
        self._mutation = False
        self._state = dict(maps=[], phone=None, connected=False, updated=None, job=None)

    def guard_mission(self, mode):
        self.survey.guard_operator_survey(mode)
        if mode != 'idle':
            with self._lock:
                if self._busy and self._mutation:
                    raise RuntimeError('RoomTrek map operation in progress; wait for completion')

    def snapshot(self):
        with self._lock:
            state = copy.deepcopy(self._state)
            state['busy'] = self._busy
        state['selection'] = self.survey.selection_snapshot()
        state['operator_survey'] = self.survey.snapshot()['operator_survey']
        state['age_s'] = None if state['updated'] is None else max(0, monotonic()-state['updated'])
        state.pop('updated')
        return state

    @classmethod
    def validate(cls, body):
        if not isinstance(body, dict) or not isinstance(body.get('action'), str) or body['action'] not in cls.ACTIONS:
            raise ValueError('Unknown map action')
        action = body['action']
        allowed = {'action'}
        if action in ('select', 'resume', 'rename', 'delete'): allowed.add('map_id')
        if action in ('rename', 'save'): allowed.add('name')
        if action == 'delete': allowed.add('confirm')
        if set(body)-allowed: raise ValueError('Unexpected map action fields')
        result = dict(body)
        if 'map_id' in allowed:
            map_id = body.get('map_id')
            if map_id is None and action == 'select': result['map_id'] = None
            else:
                try: result['map_id'] = str(uuid.UUID(map_id)).upper()
                except (ValueError, TypeError, AttributeError) as error:
                    raise ValueError('A saved map UUID is required') from error
        if 'name' in allowed:
            name = body.get('name')
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
                raise ValueError('Map name must contain 1–80 characters')
            result['name'] = name.strip()
        if action == 'delete' and body.get('confirm') is not True:
            raise ValueError('Confirm deletion of this saved map')
        return result

    def submit(self, body):
        body = self.validate(body)
        mutation = body['action'] != 'refresh'
        # Same lock as Clock and HTTP mission starts: reservation is atomic
        # with the idle check. The worker never holds the mission lock.
        with self.mission._coord_lock if self.mission is not None else nullcontext():
            if mutation and self.mission is not None:
                state = self.mission.status_snapshot()
                if state['mission_mode'] != 'idle' or self.mission._manual_motion_active() or self.mission._manual_step is not None:
                    raise RuntimeError('Stop / idle Rosie before managing maps')
            with self.survey._mode_lock:
                if mutation and (self.survey._active or self.survey._queue.unfinished_tasks):
                    raise RuntimeError('Wait for the mission survey start/save to finish')
                with self._lock:
                    if self._busy: raise RuntimeError('A map operation is already in progress')
                    self._busy, self._mutation = True, mutation
                    job = dict(id=str(uuid.uuid4()), action=body['action'], status='queued', detail='Waiting for phone')
                    self._state['job'] = job
                    self._thread = Thread(target=self._run, args=(body,), name='RoomTrekMaps', daemon=True)
                    self._thread.start()
                    return dict(job)

    def _reply(self, command, **args):
        reply = self.survey.command(command, **args)
        if reply.get('status') != 'completed':
            raise RuntimeError(command+': '+reply.get('detail', reply.get('status', 'No result')))
        return reply

    def _inventory(self):
        status = self._reply('STATUS')
        inventory = json.loads(status.get('detail', '{}'))
        if 'map_library_v1' not in inventory.get('capabilities', []):
            raise RuntimeError('Install the RoomTrek map-library update on the iPhone')
        maps, offset, revision = [], 0, None
        for _ in range(1000):
            page = json.loads(self._reply('MAP_LIST', offset=offset).get('detail', '{}'))
            if revision is not None and page['inventory_revision'] != revision:
                raise RuntimeError('Phone map library changed while reading; refresh again')
            revision = page['inventory_revision']
            maps.extend(page['maps'])
            if page['next_offset'] is None: break
            if page['next_offset'] <= offset: raise ValueError('Invalid map inventory page')
            offset = page['next_offset']
        else: raise RuntimeError('Map inventory exceeds page limit')
        with self._lock:
            self._state.update(maps=maps, phone=inventory, connected=True, updated=monotonic(),
                               inventory_errors=page.get('inventory_errors', 0),
                               storage_bytes=page.get('storage_bytes', 0))
        return inventory, maps

    def _perform(self, body):
        action = body['action']
        phone, maps = self._inventory()
        if action == 'refresh': return 'Phone status and saved maps refreshed'
        map_id = body.get('map_id')
        if map_id and not any(m['id'].upper() == map_id for m in maps):
            raise ValueError('Saved map is missing; refresh and choose again')
        if action == 'select':
            self.survey.select_map(map_id)
            return 'Mission map selected' if map_id else 'Automatic mission map selection restored'
        if action == 'keep':
            self.survey.keep_operator_survey(phone)
            return 'Current survey kept for steering; use the pad, Stop / idle, then refresh and save'
        if action in ('fresh', 'resume'):
            self._reply('SESSION_STOP')
            self.survey.release_operator_survey()
            started = self._reply('SURVEY_START', **(dict(map_id=map_id) if action == 'resume' else {}))
            self.survey.keep_operator_survey(dict(running=True, mode='survey', map_id=map_id,
                                                 session=started.get('operation', {}).get('session')))
            detail = 'Fresh survey started; saved maps preserved' if action == 'fresh' else 'Saved map resumed'
        elif action == 'stop':
            self._reply('SESSION_STOP')
            self.survey.release_operator_survey()
            detail = 'Phone session stopped; saved maps preserved'
        elif action == 'save':
            saved = json.loads(self._reply('SURVEY_SAVE', name=body['name']).get('detail', '{}'))
            saved_id = saved.get('map_id')
            if not saved_id: raise RuntimeError('Save returned no map UUID')
            _, after = self._inventory()
            if not any(m['id'].upper() == saved_id.upper() and m['name'] == body['name'] for m in after):
                raise RuntimeError('Save acknowledged but stored map not verified')
            self.survey.operator_survey_saved(saved_id)
            return 'Saved '+body['name']+'; select it below for Rosie’s next run'
        elif action == 'rename':
            self._reply('MAP_RENAME', map_id=map_id, name=body['name'])
            _, after = self._inventory()
            if not any(m['id'].upper() == map_id and m['name'] == body['name'] for m in after):
                raise RuntimeError('Rename acknowledged but stored name not verified')
            return 'Saved map renamed'
        elif action == 'delete':
            effective = self.survey.selected_map_id or (self.survey.seed_map_id or '').upper()
            if map_id == effective:
                raise ValueError('Choose another mission map before deleting this mission selection or configured seed')
            if phone.get('running') and phone.get('map_id', '').upper() == map_id:
                raise ValueError('Stop the phone session before deleting its active map')
            self._reply('MAP_DELETE', map_id=map_id)
            _, after = self._inventory()
            if any(m['id'].upper() == map_id for m in after): raise RuntimeError('Deletion not verified')
            return 'Saved map deleted'
        self._inventory()
        return detail

    def _run(self, body):
        try:
            with self._lock: self._state['job']['status'] = 'running'
            with self.survey.operation_lock:
                self.survey._target = None
                detail = self._perform(body)
            status = 'completed'
        except Exception as error:
            status, detail = 'failed', str(error)
            with self._lock: self._state['connected'] = False
        with self._lock:
            self._state['job'].update(status=status, detail=detail)
            self._busy = False
        self.survey.logger.info('RoomTrek map action=%s status=%s detail=%s', body['action'], status, detail,
                                extra=dict(speech_announce=False))

    def close(self):
        if self._thread is not None: self._thread.join(timeout=30)
