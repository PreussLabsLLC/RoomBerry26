"""Core Motion wire validation and diagnostic relative-heading comparison."""
# @(#)roomberry_motion.py 3.2.imu.1 2026/11/12 15:05:56
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
