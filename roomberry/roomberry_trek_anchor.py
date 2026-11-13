"""One-time planar RoomTrek alignment at the stationary qualified tag16 anchor."""
# @(#)roomberry_trek_anchor.py 3.2 2026/11/09 18:14:49
from math import atan2, cos, sin, hypot, radians, isfinite, pi
import json
from time import monotonic, time


def wrap(angle):
    return (angle+pi)%(2*pi)-pi


class TrekTagAnchor:
    """Diagnostic only: never nudges wheel/localizer pose or commands motion.

    Mount yaw converts the selected camera-axis heading into robot heading.
    Dashboard mount uses optical forward,20deg left and15deg up; +Y basis is
    retained only for historical anchors with the older mount.
    """
    def __init__(self, receiver, logger, mount_yaw_deg=-20., lens_x_mm=10., lens_y_mm=180.,
                 heading_basis='optical_forward', mount_pitch_deg=15.):
        self.receiver, self.logger = receiver, logger
        if heading_basis not in ('optical_forward','camera_y'):
            raise ValueError('Unsupported RoomTrek heading basis')
        self.heading_basis = heading_basis
        self.mount_pitch = radians(mount_pitch_deg)
        self.mount_yaw = radians(mount_yaw_deg)
        self.lens = (float(lens_x_mm), float(lens_y_mm))
        if not all(isfinite(v) for v in (self.mount_yaw, self.mount_pitch, *self.lens)):
            raise ValueError('RoomTrek mount values must be finite')
        self.anchor = None
        self.state = 'waiting_for_tag16'
        self.last_sequence = None
        self.last_result = None
        self.wheel_pose = None
        self.wheel_odom = None

    def _state(self, state, detail):
        if state != self.state:
            self.logger.info('RoomTrek alignment status=%s detail=%s', state, detail,
                             extra=dict(speech_announce=False))
        self.state = state

    @staticmethod
    def axis_heading(row, basis):
        x,y,z,w = (row[k] for k in ('qx','qy','qz','qw'))
        norm = (x*x+y*y+z*z+w*w)**.5
        if not isfinite(norm) or not .95 <= norm <= 1.05:
            raise ValueError('Invalid camera quaternion')
        x,y,z,w = x/norm,y/norm,z/norm,w/norm
        # Quaternion rotates native camera axes into mapped AR world.
        if basis == 'optical_forward':
            forward_x,forward_y = -2*(x*z+y*w), -2*(y*z-x*w)  # camera -Z
        elif basis in ('camera_y','quaternion camera +Y plus mount yaw'):
            forward_x,forward_y = 2*(x*y-z*w),1-2*(x*x+z*z)
        else: raise ValueError('Unsupported recorded heading basis')
        if hypot(forward_x,forward_y) < .2:
            raise ValueError('Camera heading axis has insufficient horizontal projection')
        return atan2(forward_y,forward_x)

    @staticmethod
    def camera_y_heading(row):
        return TrekTagAnchor.axis_heading(row,'camera_y')

    @classmethod
    def usable(cls, row, basis='optical_forward'):
        if row['tracking'] != 2 or row['reason'] != 0 or row['frame_age_us'] > 250000:
            return False
        if row.get('map_uuid', bytes(16)) != bytes(16) and (
                row.get('relocalization') != 2 or not row.get('flags', 0) & 1):
            return False  # Loaded-map normal tracking alone is not relocalization.
        try: cls.axis_heading(row,basis)
        except (ValueError,KeyError): return False
        return True

    def bind(self, tag_pose, captured_at, epoch, now_epoch=None, now_monotonic=None, wheel_state=None):
        """Pair at actual capture time, not delayed tag-detection completion."""
        if self.anchor is not None:
            return False  # One tag16 binding per run; never refit drift away.
        now_epoch = time() if now_epoch is None else now_epoch
        now_monotonic = monotonic() if now_monotonic is None else now_monotonic
        capture_monotonic = now_monotonic+captured_at-now_epoch
        history = self.receiver.trek_history()
        candidates = [r for r in history if self.usable(r,self.heading_basis) and abs(r['frame_monotonic']-capture_monotonic)<=.25]
        if not candidates:
            self._state('unavailable','No normal phone frame within250ms of tag16 capture'); return False
        paired = min(candidates,key=lambda r:abs(r['frame_monotonic']-capture_monotonic))
        window = [r for r in candidates if r['session']==paired['session'] and r['map_uuid']==paired['map_uuid']]
        if len(window)<3 or max(r['frame_monotonic'] for r in window)-min(r['frame_monotonic'] for r in window)<.15:
            self._state('unavailable','Insufficient stationary phone history at tag16'); return False
        heading = self.axis_heading(paired,self.heading_basis)
        if any(hypot(r['x_m']-paired['x_m'],r['y_m']-paired['y_m'])>.02
               or abs(wrap(self.axis_heading(r,self.heading_basis)-heading))>radians(2) for r in window):
            self._state('unavailable','Phone moved during stationary tag16 capture'); return False
        rotation = wrap(tag_pose['heading_rad']-(heading+self.mount_yaw))
        lx,ly = self.lens; theta=tag_pose['heading_rad']
        camera_room=(tag_pose['x_mm']+cos(theta)*lx-sin(theta)*ly,
                     tag_pose['y_mm']+sin(theta)*lx+cos(theta)*ly)
        self.anchor=dict(session=paired['session'],map_uuid_hex=paired['map_uuid'].hex(),
                         odometry_epoch=epoch,rotation_rad=rotation,
                         phone_origin_m=[paired['x_m'],paired['y_m']],camera_room_mm=list(camera_room),
                         tag_robot_pose=dict(tag_pose),tag_captured_epoch=captured_at,
                         phone_frame_us=paired['frame_us'],phone_frame_monotonic=paired['frame_monotonic'],
                         frame_pair_delta_s=paired['frame_monotonic']-capture_monotonic,
                         mount_yaw_rad=self.mount_yaw,lens_offset_mm=list(self.lens),
                         heading_basis=self.heading_basis,mount_pitch_rad=self.mount_pitch,scale=1.0)
        self.wheel_pose=dict(tag_pose)
        self.wheel_odom=None if wheel_state is None else (wheel_state['distance'],wheel_state['angle'])
        self.anchor['wheel_odometry_at_anchor']=None if wheel_state is None else dict(
            distance_mm=wheel_state['distance'],angle_deg=wheel_state['angle'],
            sensor_monotonic=wheel_state.get('sensor_monotonic_s'))
        self.last_sequence=None
        self._state('anchored','Fixed alignment from qualified stationary tag16 capture')
        self.logger.info('RoomTrek tag16 alignment: %s',json.dumps(self.anchor,sort_keys=True),
                         extra=dict(speech_announce=False))
        return True

    def transform(self, row):
        a=self.anchor
        dx=(row['x_m']-a['phone_origin_m'][0])*1000
        dy=(row['y_m']-a['phone_origin_m'][1])*1000
        c,s=cos(a['rotation_rad']),sin(a['rotation_rad'])
        camera=(a['camera_room_mm'][0]+c*dx-s*dy,a['camera_room_mm'][1]+s*dx+c*dy)
        heading=wrap(self.axis_heading(row,a.get('heading_basis','camera_y'))+a['mount_yaw_rad']+a['rotation_rad'])
        lx,ly=a['lens_offset_mm']
        return dict(x_mm=camera[0]-cos(heading)*lx+sin(heading)*ly,
                    y_mm=camera[1]-sin(heading)*lx-cos(heading)*ly,heading_rad=heading)

    def compare(self, state, now=None):
        if self.anchor is None or self.state=='invalidated': return None
        a=self.anchor
        if state.get('odometry_epoch')!=a['odometry_epoch']:
            self._state('invalidated','Wheel epoch changed; new tag16 anchor required'); return None
        odom=(state['distance'],state['angle'])
        if self.wheel_odom is not None:
            delta=odom[0]-self.wheel_odom[0]
            yaw=radians(odom[1]-self.wheel_odom[1])
            middle=self.wheel_pose['heading_rad']+yaw/2
            self.wheel_pose['x_mm']+=delta*cos(middle)
            self.wheel_pose['y_mm']+=delta*sin(middle)
            self.wheel_pose['heading_rad']=wrap(self.wheel_pose['heading_rad']+yaw)
        self.wheel_odom=odom
        row=self.receiver.latest_trek_observation()
        if row is None: return None
        if row['session']!=a['session'] or row['map_uuid'].hex()!=a['map_uuid_hex']:
            self._state('invalidated','Phone session/map changed; new tag16 anchor required'); return None
        now=monotonic() if now is None else now
        if not self.usable(row,a.get('heading_basis','camera_y')) or not 0<=now-row['frame_monotonic']<=.25:
            self._state('unavailable','Phone tracking or sample freshness unavailable'); return None
        self._state('anchored','Same fixed tag16 alignment')
        if row['seq']==self.last_sequence: return None
        self.last_sequence=row['seq']
        phone=self.transform(row)
        wheel_pose=self.wheel_pose
        dx,dy=phone['x_mm']-wheel_pose['x_mm'],phone['y_mm']-wheel_pose['y_mm']
        self.last_result=dict(session=row['session'],seq=row['seq'],phone_frame_us=row['frame_us'],
                              phone_frame_monotonic=row['frame_monotonic'],
                              wheel_monotonic=state.get('sensor_monotonic_s'),
                              phone_pose=phone,wheel_pose=dict(wheel_pose),dx_mm=dx,dy_mm=dy,
                              separation_mm=hypot(dx,dy),heading_delta_rad=wrap(phone['heading_rad']-wheel_pose['heading_rad']))
        self.logger.info('RoomTrek anchored comparison: %s',json.dumps(self.last_result,sort_keys=True),
                         extra=dict(speech_announce=False))
        return self.last_result
