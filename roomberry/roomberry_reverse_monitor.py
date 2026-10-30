"""Report-only reverse load monitoring; this module cannot issue robot commands."""
# @(#)roomberry_reverse_monitor.py 2.3.10 2026/10/28 17:00:00
from math import isfinite


class ReverseCurrentMonitor:
    """Observe validated samples and applied wheel speeds, without control actions."""

    def __init__(self, logger, config=None):
        self.logger = logger
        cfg = config or {}
        if cfg.get('mode', 'report_only') != 'report_only':
            raise ValueError('Reverse current monitoring supports report_only mode only')
        self.enabled = bool(cfg.get('enabled', True))
        self.floor = float(cfg.get('sustained_current_a', .40))
        self.margin = float(cfg.get('baseline_margin_a', .20))
        self.fast = float(cfg.get('immediate_current_a', .65))
        self.persistence = float(cfg.get('persistence_s', .25))
        self.no_progress = float(cfg.get('no_progress_s', 1.0))
        if not all(isfinite(x) and x > 0 for x in
                   (self.floor, self.margin, self.fast, self.persistence, self.no_progress)):
            raise ValueError('Reverse monitor thresholds must be finite and positive')
        if self.fast <= self.floor:
            raise ValueError('Immediate current threshold must exceed sustained threshold')
        self.baseline = [.15, .15]
        self.last_event = None
        self.event_count = 0
        self.reset_episode()

    def reset_episode(self):
        self.wheels = None
        self.changed_at = None
        self.last_at = None
        self.progress_at = None
        self.progress_mm = 0.0
        self.high_since = [None, None]
        self.high_count = [0, 0]
        self.reported = set()
        self.reversing = False
        self.currents = [0.0, 0.0]
        self.thresholds = [self.floor, self.floor]

    def status(self):
        return dict(enabled=self.enabled, mode='report_only', reversing=self.reversing,
                    candidate=bool(self.reported), reasons=sorted(self.reported),
                    baseline_a=list(self.baseline), current_a=list(self.currents),
                    threshold_a=list(self.thresholds), event_count=self.event_count,
                    last_event=None if self.last_event is None else dict(self.last_event))

    def update(self, sensors, wheels, distance_delta_mm, now):
        if not self.enabled or wheels is None or not all(v < 0 for v in wheels):
            self.reset_episode()
            return self.status()
        if self.last_at is not None and now - self.last_at > .5:
            # Missing samples cannot satisfy a persistence or stall interval.
            self.reset_episode()
        if self.wheels != tuple(wheels):
            self.changed_at = now
            self.high_since = [None, None]
            self.high_count = [0, 0]
            self.progress_at = now
            self.progress_mm = 0.0
        self.wheels = tuple(wheels)
        self.reversing = True
        dt = 0 if self.last_at is None else max(0, now - self.last_at)
        self.last_at = now
        self.currents = [abs(float(getattr(sensors, name, 0))) / 1000
                         for name in ('left_motor_current', 'right_motor_current')]
        stable = now - self.changed_at >= .15
        over = getattr(sensors, 'wheel_overcurrents', None)
        reasons = []
        for i, side in enumerate(('left', 'right')):
            current = self.currents[i]
            threshold = max(self.floor, self.baseline[i] + self.margin)
            self.thresholds[i] = threshold
            if current >= self.fast or bool(getattr(over, side + '_wheel_overcurrent', False)):
                reasons.append(side + '_high_current')
            if stable and current >= threshold:
                if self.high_since[i] is None:
                    self.high_since[i] = now
                self.high_count[i] += 1
                if self.high_count[i] >= 3 and now - self.high_since[i] >= self.persistence:
                    reasons.append(side + '_sustained_current')
            else:
                self.high_since[i], self.high_count[i] = None, 0
        self.progress_mm += abs(float(distance_delta_mm))
        progressing = self.progress_mm >= 2.0
        if progressing:
            self.progress_at, self.progress_mm = now, 0.0
        elif stable and now - self.progress_at >= self.no_progress:
            reasons.append('no_encoder_progress')
        # Freeze learning on rising/high load, during ramps, or without motion.
        if stable and progressing and not reasons:
            for i, current in enumerate(self.currents):
                if current <= self.baseline[i] + .05:
                    weight = min(.02, dt / 10.0)
                    self.baseline[i] = min(.25, self.baseline[i] + weight * (current - self.baseline[i]))
        new = set(reasons) - self.reported
        if new:
            self.reported.update(new)
            self.event_count += 1
            self.last_event = dict(reasons=sorted(new), current_a=list(self.currents),
                                   applied_wheels_mm_s=list(wheels), baseline_a=list(self.baseline),
                                   threshold_a=list(self.thresholds), monotonic_s=now)
            self.logger.warning('[REPORT ONLY] Reverse load candidate: %s; motion unchanged.', self.last_event)
        return self.status()
