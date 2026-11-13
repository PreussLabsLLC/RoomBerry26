"""Shared encoder turn qualification, with measured settling between directions."""
# @(#)roomberry_turn_guard.py 3.2 2026/11/09 18:53:01
import math


class SettledTurn:
    def __init__(self, mission, clock, max_pulse_s=None):
        self.mission, self.clock = mission, clock
        self.max_pulse_s = max_pulse_s
        self.reset()

    def reset(self):
        self.phase = 'idle'
        self.sign = None
        self.error = None
        self.anchor = None
        self.last_sample = None
        self.quiet_since = None
        self.wrong_samples = 0
        self.issued_at = None
        self.stopped_at = None

    def _brake(self):
        self.mission._send_stop('pivot brake before measured settling', force=True)
        self.phase = 'settling'
        self.stopped_at = self.clock()
        self.last_sample = self.quiet_since = self.anchor = None
        self.wrong_samples = 0
        self.mission.logger.info('Pivot settling: previous_direction=%s', self.sign)

    def prepare(self, state, requested_sign, error_rad=None):
        """True permits dispatch; False holds zero or exposes a bounded fault."""
        now = self.clock()
        # A snapshot can be recent yet still precede the new serial command.
        stamp = state.get('sensor_monotonic_s')
        if not isinstance(stamp, (int, float)):
            stamp = now-float(state.get('age') or 0.)
        sample = (stamp, float(state['angle']), float(state['distance']))
        if (self.phase == 'turning' and self.max_pulse_s is not None
                and now-self.issued_at >= self.max_pulse_s):
            self._brake()
            return False
        if self.phase == 'turning' and requested_sign != self.sign:
            self._brake()
            return False
        if self.phase == 'idle' and requested_sign is not None:
            self._brake()  # Also settle translation before starting any pivot.
            return False
        if self.phase == 'settling':
            if now-self.stopped_at > 1.5:
                self.error = 'pivot wheels did not settle within 1.5 seconds'
                return False
            if stamp <= self.stopped_at or (self.last_sample and stamp <= self.last_sample[0]):
                return False
            previous = self.last_sample
            self.last_sample = sample
            if previous is None:
                return False
            dt = stamp-previous[0]
            quiet = (0 < dt <= .5 and abs(sample[1]-previous[1])/dt <= 2.
                     and abs(sample[2]-previous[2])/dt <= 5.)
            if not quiet:
                self.quiet_since = None
                return False
            if self.quiet_since is None:
                self.quiet_since = previous[0]
            if stamp-self.quiet_since < .15:
                return False
            self.phase = 'ready'
            self.sign = None
            self.mission.logger.info('Pivot settled: heading_deg=%.3f elapsed_s=%.3f',
                                     sample[1], now-self.stopped_at)
        if self.phase == 'ready':
            if requested_sign is None:
                self.reset()
            return True
        if self.phase == 'turning':
            if stamp <= self.issued_at or (self.last_sample and stamp <= self.last_sample[0]):
                return True  # Never judge a reversal using a pre-command poll.
            previous = self.last_sample
            self.last_sample = sample
            if self.anchor is None:
                self.anchor = sample[1]
                self.mission.logger.info('Pivot encoder reference: heading_deg=%.3f sample_monotonic_s=%.6f issued_monotonic_s=%.6f',
                                         self.anchor, stamp, self.issued_at)
                return True
            progress = self.sign*(sample[1]-self.anchor)
            # Allow finite startup/quantization error; sustained or large wrong
            # direction still stops. The reference is now post-dispatch.
            if now-self.issued_at >= .2 and progress < -3.:
                self.wrong_samples += 1
            else:
                self.wrong_samples = 0
            if progress < -8. or self.wrong_samples >= 2:
                self.error = ('pivot wheel heading moved opposite the commanded turn after settling '
                              f'(progress_deg={progress:.2f}, wrong_samples={self.wrong_samples})')
                return False
            if previous is not None and error_rad is not None:
                dt = stamp-previous[0]
                closing_rate = self.sign*(sample[1]-previous[1])/dt if 0 < dt <= .5 else 0.
                # Brake before the next coarse mission tick carries us across
                # the target. Reassess the error after the encoders settle.
                if closing_rate > 0 and abs(math.degrees(error_rad)) <= max(2., closing_rate*.25):
                    self._brake()
                    return False
        return True

    def dispatched(self, sign):
        if sign is not None and self.phase == 'ready':
            self.phase, self.sign = 'turning', sign
            self.issued_at = self.clock()
            self.last_sample = self.anchor = None
            self.wrong_samples = 0
            self.mission.logger.info('Pivot direction verification armed after dispatch: direction=%d', sign)
