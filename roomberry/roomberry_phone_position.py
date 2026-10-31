"""Rate-limited phone position aiding, anchored only by stationary tag fixes."""
from math import cos, sin, hypot, exp, radians, isfinite


class PhonePositionCorrection:
    def __init__(self, receiver, logger, max_speed_mm_s=5.0, time_constant_s=20.0,
                 mount_yaw_deg=93.6, lens_x_mm=-145.0, lens_y_mm=-22.0):
        self.receiver, self.logger = receiver, logger
        self.max_speed = float(max_speed_mm_s)
        self.tau = float(time_constant_s)
        if (not all(isfinite(float(v)) for v in (self.max_speed, self.tau, mount_yaw_deg,
                                                 lens_x_mm, lens_y_mm)) or
                not 0 < self.max_speed <= 10 or self.tau < 1):
            raise ValueError('Phone correction requires speed in (0,10] mm/s and time constant >=1 s')
        self.mount_yaw = radians(mount_yaw_deg)
        self.lens = (lens_x_mm, lens_y_mm)
        self.anchor = None
        self.last_time = None
        self.last_phone = None
        self.last_log = None
        self.total_mm = 0.0

    def reset(self):
        self.anchor = self.last_time = self.last_phone = None

    def apply(self, localizer, pose, now, odometry_epoch=None, enabled=True):
        row = self.receiver.latest_observation()
        dt = 0.0 if self.last_time is None else max(0.0, min(now-self.last_time, 0.25))
        self.last_time = now
        if (not pose or not pose.get('localized') or row is None or
                not row['flags'] & 1 or row['tracking'] != 2 or
                not 0 <= now-row['frame_monotonic'] <= .25 or row['frame_age_us'] > 250000):
            self.reset()
            return pose
        identity = (row['session'], row['alignment'], odometry_epoch)
        heading = row['heading_rad'] + self.mount_yaw
        lx, ly = self.lens
        phone = (row['x_mm']-cos(heading)*lx+sin(heading)*ly,
                 row['y_mm']-sin(heading)*lx-cos(heading)*ly)
        if self.last_phone is not None:
            old, old_t = self.last_phone
            elapsed = row['frame_monotonic']-old_t
            if elapsed < 0 or hypot(phone[0]-old[0], phone[1]-old[1]) > 100+500*max(0, elapsed):
                self.reset()
                return pose
        self.last_phone = (phone, row['frame_monotonic'])
        if self.anchor is not None and self.anchor['identity'] != identity:
            self.reset()
        if pose.get('accepted_tag_ids'):
            # Scan fixes are stationary; require phone velocity evidence too.
            if (row['flags'] & 2 and hypot(row['forward_mm_s'], row['left_mm_s']) < 20
                    and abs(row['yaw_rad_s']) < .1):
                self.anchor = dict(identity=identity, phone=phone,
                                   room=(pose['x_mm'], pose['y_mm']),
                                   rotation=pose['heading_rad']-heading)
                self.logger.info('Phone position anchored: session=%s alignment=%s room_mm=(%.1f, %.1f).',
                                 row['session'], row['alignment'], pose['x_mm'], pose['y_mm'])
            else:
                self.anchor = None
            return pose
        if self.anchor is None or not enabled or dt <= 0:
            return pose
        a = self.anchor
        x, y = phone[0]-a['phone'][0], phone[1]-a['phone'][1]
        c, s = cos(a['rotation']), sin(a['rotation'])
        target = (a['room'][0]+c*x-s*y, a['room'][1]+s*x+c*y)
        dx, dy = target[0]-pose['x_mm'], target[1]-pose['y_mm']
        error = hypot(dx, dy)
        if error > 750:
            self.logger.warning('Phone position disagreement %.0f mm; awaiting another tag anchor.', error)
            self.reset()
            return pose
        fraction = min(1-exp(-dt/self.tau), self.max_speed*dt/max(error, 1e-9))
        dx, dy = dx*fraction, dy*fraction
        if localizer.nudge_position(dx, dy):
            pose = dict(pose, x_mm=pose['x_mm']+dx, y_mm=pose['y_mm']+dy)
            self.total_mm += hypot(dx, dy)
            if self.last_log is None or now-self.last_log >= 10:
                self.logger.info('Phone position correction: error_mm=%.1f step_mm=%.3f '
                                 'total_correction_mm=%.1f target_mm=(%.1f, %.1f).',
                                 error, hypot(dx, dy), self.total_mm, *target)
                self.last_log = now
        return pose
