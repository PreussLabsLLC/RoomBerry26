"""Current service-run wheel and phone traces, independent of navigation fixes."""
# @(#)roomberry_run_trails.py 3.2.trails.1 2026/11/10 13:54:11
from math import cos, sin, radians, hypot, isfinite
from time import monotonic

from roomberry_trek_anchor import TrekTagAnchor


class RunTrails:
    def __init__(self, mapper, receiver, logger, config):
        self.mapper = mapper
        self.phone = None
        if receiver is not None and config.get('enabled', True):
            self.phone = TrekTagAnchor(receiver, logger, **{
                k: config[k] for k in ('mount_yaw_deg', 'mount_pitch_deg',
                    'heading_basis', 'lens_x_mm', 'lens_y_mm') if k in config})
        self.pose = self.odom = self.epoch = None
        self.wheel = []
        self.iphone = []
        self.phone_valid = False
        self.phone_sequence = None

    def anchor(self, pose, captured_at, state):
        """Use a stationary accepted tag16; never refit an existing trace."""
        if self.pose is None:
            self.pose = dict(pose)
            self.odom = (state['distance'], state['angle'])
            self.epoch = state.get('odometry_epoch')
        if self.phone is not None and self.phone.anchor is None:
            self.phone.bind(pose, captured_at, self.epoch, wheel_state=state)
        self.update(state)

    @staticmethod
    def append(trail, pose):
        point = (pose['x_mm'], pose['y_mm'])
        if not all(isfinite(v) for v in point):
            return
        if not trail or trail[-1] is None or hypot(point[0]-trail[-1][0], point[1]-trail[-1][1]) >= 20:
            trail.append(point)

    def update(self, state):
        if self.pose is None:
            return
        if state.get('odometry_epoch') != self.epoch:
            # Keep the earlier segment visible, but require a new tag16 anchor.
            self.wheel.append(None)
            self.iphone.append(None)
            self.pose = self.odom = None
            if self.phone is not None:
                self.phone.anchor = None
            self.phone_valid = False
            self.phone_sequence = None
            self.publish()
            return
        if state.get('ready') and state.get('age') is not None and state['age'] <= .5:
            distance, angle = state['distance'], state['angle']
            yaw = radians(angle-self.odom[1])
            middle = self.pose['heading_rad']+yaw/2
            self.pose['x_mm'] += (distance-self.odom[0])*cos(middle)
            self.pose['y_mm'] += (distance-self.odom[0])*sin(middle)
            self.pose['heading_rad'] += yaw
            self.odom = (distance, angle)
            self.append(self.wheel, self.pose)
        if self.phone is not None and self.phone.anchor is not None:
            row = self.phone.receiver.latest_trek_observation()
            a = self.phone.anchor
            valid = (row is not None and row['session'] == a['session']
                     and row['map_uuid'].hex() == a['map_uuid_hex']
                     and self.phone.usable(row, self.phone.heading_basis)
                     and 0 <= monotonic()-row['frame_monotonic'] <= .25)
            if not valid and self.phone_valid:
                self.iphone.append(None)
            if valid and row['seq'] != self.phone_sequence:
                self.append(self.iphone, self.phone.transform(row))
                self.phone_sequence = row['seq']
            self.phone_valid = valid
        self.publish()

    def publish(self):
        self.mapper.set_run_trails(self.wheel, self.iphone)
