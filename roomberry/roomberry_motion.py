"""Core Motion wire validation and diagnostic relative-heading comparison."""
# @(#)roomberry_motion.py 3.2.nudge.1 2026/11/12 18:01:48
import json
import math
import struct
from time import monotonic
from roomberry_trek_anchor import TrekTagAnchor, wrap

MOTION_PACKET = struct.Struct('<4sBBHQIHBBQQ14fII24s')
MOTION_FIELDS = ('magic','version','type','length','session','seq','flags','motion_state',
    'reserved','sample_us','send_us','motion_qx','motion_qy','motion_qz','motion_qw',
    'gyro_x_rad_s','gyro_y_rad_s','gyro_z_rad_s','user_ax_ms2','user_ay_ms2','user_az_ms2',
    'gravity_x_g','gravity_y_g','gravity_z_g','integrated_yaw_rad','sample_age_us',
    'motion_generation','padding')


def decode_motion_packet(data):
    if len(data) != 128: raise ValueError('length')
    values = MOTION_PACKET.unpack(data)
    r = dict(zip(MOTION_FIELDS, values))
    if values[:4] != (b'NVLK',1,7,128): raise ValueError('framing')
    if not r['session'] or r['flags'] & ~1 or r['motion_state'] > 3 or r['reserved'] or any(r['padding']):
        raise ValueError('motion fields')
    if r['send_us'] < r['sample_us'] or not all(math.isfinite(x) for x in values[11:25]):
        raise ValueError('motion representation')
    if r['flags']:
        age = r['send_us']-r['sample_us']
        if r['motion_state'] != 2 or not r['sample_us'] or age > 250000 or abs(age-r['sample_age_us']) > 2:
            raise ValueError('motion freshness')
        if not .95 <= sum(r[k]**2 for k in ('motion_qx','motion_qy','motion_qz','motion_qw'))**.5 <= 1.05:
            raise ValueError('motion quaternion')
        if not .8 < sum(r[k]**2 for k in ('gravity_x_g','gravity_y_g','gravity_z_g'))**.5 < 1.2:
            raise ValueError('motion gravity')
    return values


class MotionComparison:
    """Compare relative turns only; never correct pose, fuse sensors or steer."""
    def __init__(self, logger):
        self.logger = logger
        self.identity = self.baseline = self.last = self.sequence = None
        self.ar_previous = None
        self.ar_delta = 0.0
        self.state = 'waiting_for_motion'

    def snapshot(self):
        result = self.last
        fresh = self.state == 'comparing' and result is not None and 0 <= monotonic()-result['compared_monotonic'] <= .5
        return dict(state=self.state if fresh or result is None else 'stale',
                    last=None if result is None else dict(result), fresh=fresh)

    def update(self, receiver, wheel, now=None):
        now = monotonic() if now is None else now
        if receiver is None: return
        getter = getattr(receiver, 'latest_motion_observation', None)
        motion = getter() if callable(getter) else None
        if not isinstance(motion, dict) or not motion.get('flags') or not 0 <= now-motion['frame_monotonic'] <= .25:
            self.state = 'motion_unavailable'; return
        if not wheel.get('ready') or wheel.get('age') is None or wheel['age'] > .15:
            self.state = 'wheel_unavailable'; return
        sample_time = wheel.get('sensor_monotonic_s')
        if not isinstance(sample_time, (int,float)) or abs(sample_time-motion['frame_monotonic']) > .15:
            self.state = 'wheel_pair_unavailable'; return
        rows = receiver.trek_history()
        if not isinstance(rows, list): return
        candidates = [r for r in rows if r['session'] == motion['session']
                      and TrekTagAnchor.usable(r) and abs(r['frame_monotonic']-motion['frame_monotonic']) <= .15]
        if not candidates:
            self.state = 'ar_pair_unavailable'; return
        ar = min(candidates,key=lambda r:abs(r['frame_monotonic']-motion['frame_monotonic']))
        identity = (motion['session'],motion['motion_generation'],wheel.get('odometry_epoch'))
        sequence = (identity,motion['seq'])
        self.state = 'comparing'
        if sequence == self.sequence: return
        heading = TrekTagAnchor.axis_heading(ar,'optical_forward')
        if identity != self.identity:
            self.identity = identity
            self.baseline = (motion['integrated_yaw_rad'],wheel['angle'])
            self.ar_previous = heading
            self.ar_delta = 0.0
        else:
            self.ar_delta += wrap(heading-self.ar_previous)
            self.ar_previous = heading
        self.sequence = sequence
        gyro = motion['integrated_yaw_rad']-self.baseline[0]
        wheels = math.radians(wheel['angle']-self.baseline[1])
        self.last = dict(session=str(motion['session']),motion_generation=motion['motion_generation'],
            odometry_epoch=wheel.get('odometry_epoch'),motion_sequence=motion['seq'],
            compared_monotonic=now,motion_sample_us=motion['sample_us'],ar_frame_us=ar['frame_us'],
            ar_pair_delta_s=ar['frame_monotonic']-motion['frame_monotonic'],
            wheel_pair_delta_s=sample_time-motion['frame_monotonic'],
            gyro_turn_deg=math.degrees(gyro),ar_turn_deg=math.degrees(self.ar_delta),
            wheel_turn_deg=math.degrees(wheels),ar_minus_gyro_deg=math.degrees(self.ar_delta-gyro),
            wheel_minus_gyro_deg=math.degrees(wheels-gyro))
        self.state = 'comparing'
        self.logger.info('RoomTrek motion comparison: %s',json.dumps(self.last,sort_keys=True),
                         extra=dict(speech_announce=False))


class GyroHeadingNudge:
    """Small tag-anchored heading corrections for homing, never raw odometry."""
    def __init__(self, logger, config=None):
        config = config or {}
        self.logger = logger
        self.enabled = bool(config.get('enabled', True))
        self.gain = float(config.get('gain', .2))
        self.rate = math.radians(float(config.get('max_rate_deg_s', 1.)))
        self.step_limit = math.radians(float(config.get('max_step_deg', .25)))
        self.total_limit = math.radians(float(config.get('max_total_deg', 5.)))
        self.innovation_limit = math.radians(float(config.get('max_innovation_deg', 10.)))
        if not all(math.isfinite(x) for x in (self.gain,self.rate,self.step_limit,self.total_limit,self.innovation_limit)):
            raise ValueError('IMU nudge limits must be finite')
        if not (0 < self.gain <= 1 and 0 < self.rate <= math.radians(5)
                and 0 < self.step_limit <= math.radians(1) and 0 < self.total_limit <= math.radians(10)
                and 0 < self.innovation_limit <= math.radians(15)):
            raise ValueError('IMU nudge limits exceed bounded correction policy')
        self.reset()

    def reset(self):
        self.anchor = None
        self.total = 0.
        self.last_at = self.last_seq = None
        self.last = None
        self.state = 'waiting_for_tag_fix' if self.enabled else 'disabled'

    def snapshot(self):
        return dict(state=self.state,correction_total_deg=math.degrees(self.total),
                    last=None if self.last is None else dict(self.last))

    @staticmethod
    def _latest(receiver, now):
        getter = getattr(receiver,'latest_motion_observation',None)
        row = getter() if callable(getter) else None
        if not isinstance(row,dict) or row.get('flags') != 1 or row.get('motion_state') != 2:
            return None
        stamp = row.get('frame_monotonic')
        if not isinstance(stamp,(int,float)) or not 0 <= now-stamp <= .25:
            return None
        return row

    def bind(self, pose, state, receiver, captured_at, now=None, now_epoch=None):
        """Call only for an accepted stationary tag fix; reanchors each fix."""
        from time import time
        self.reset()
        if not self.enabled: return False
        now = monotonic() if now is None else now
        now_epoch = time() if now_epoch is None else now_epoch
        latest = self._latest(receiver,now)
        if latest is None or not isinstance(captured_at,(int,float)):
            self.state = 'motion_unavailable_at_tag'; return False
        getter = getattr(receiver,'motion_history',None)
        history = getter() if callable(getter) else None
        if not isinstance(history,list):
            self.state = 'capture_history_unavailable'; return False
        capture = now+captured_at-now_epoch
        identity = (latest['session'],latest['motion_generation'],state.get('odometry_epoch'))
        paired = [r for r in history if (r['session'],r['motion_generation']) == identity[:2]
                  and r.get('flags') == 1 and abs(r['frame_monotonic']-capture) <= .15]
        if len(paired)<2 or max(r['frame_monotonic'] for r in paired)-min(r['frame_monotonic'] for r in paired)<.08:
            self.state = 'capture_history_unavailable'; return False
        row = min(paired,key=lambda r:abs(r['frame_monotonic']-capture))
        if max(abs(r['integrated_yaw_rad']-row['integrated_yaw_rad']) for r in paired)>math.radians(1):
            self.state = 'moving_during_tag_capture'; return False
        self.anchor = dict(identity=identity,gyro=row['integrated_yaw_rad'],heading=pose['heading_rad'])
        self.last_at = now
        self.last_seq = None
        self.state = 'anchored'
        self.logger.info('IMU heading nudge anchored: session=%s generation=%s captured_at=%.6f pair_delta_s=%.4f',
            identity[0],identity[1],captured_at,row['frame_monotonic']-capture,extra=dict(speech_announce=False))
        return True

    def update(self, pose, state, receiver, now=None):
        now = monotonic() if now is None else now
        if not self.enabled or self.anchor is None or pose is None: return 0.
        row = self._latest(receiver,now)
        if row is None:
            self.state = 'motion_unavailable'; return 0.
        identity = (row['session'],row['motion_generation'],state.get('odometry_epoch'))
        if identity != self.anchor['identity']:
            self.anchor = None
            self.state = 'new_tag_fix_required'; return 0.
        stamp = state.get('sensor_monotonic_s')
        if (not state.get('ready') or state.get('age') is None or not 0 <= state['age'] <= .15
                or not isinstance(stamp,(int,float)) or abs(stamp-row['frame_monotonic'])>.15):
            self.state = 'wheel_pair_unavailable'; return 0.
        if row['seq']==self.last_seq: return 0.
        self.last_seq = row['seq']
        dt = max(0.,min(.25,now-self.last_at));self.last_at=now
        target = self.anchor['heading']+row['integrated_yaw_rad']-self.anchor['gyro']
        error = wrap(target-pose['heading_rad'])
        if abs(error)>self.innovation_limit:
            self.state = 'innovation_rejected'; return 0.
        cap = min(self.step_limit,self.rate*dt)
        step = max(-cap,min(cap,self.gain*error))
        total = max(-self.total_limit,min(self.total_limit,self.total+step))
        step = total-self.total
        self.total=total
        pose['heading_rad']=wrap(pose['heading_rad']+step)
        self.last=dict(session=str(row['session']),generation=row['motion_generation'],
            motion_sequence=row['seq'],innovation_deg=math.degrees(error),step_deg=math.degrees(step),
            total_deg=math.degrees(total),target_heading_rad=wrap(target))
        self.state='nudging' if abs(step)>1e-9 else 'bounded' if abs(total)>=self.total_limit else 'aligned'
        self.logger.info('IMU heading nudge: %s',json.dumps(self.last,sort_keys=True),
                         extra=dict(speech_announce=False))
        return step
