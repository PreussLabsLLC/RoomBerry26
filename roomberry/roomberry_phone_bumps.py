"""Retain phone impact episodes while applying a separate robot reaction cutoff."""
# @(#)roomberry_phone_bumps.py 3.1.grout.17 2026/11/05
from math import isfinite

REACTION_MIN_MM_S2 = .6 * 9806.65


class PhoneBumpPolicy:
    def __init__(self):
        self.key = None
        self.pending = None
        self.events = []

    @staticmethod
    def identity(health):
        return health['session'], health['calibration'], health['bump_count']

    def baseline(self, health):
        self.key = self.identity(health)
        self.pending = None

    def observe(self, health, ignore_motion, minimum_mm_s2=REACTION_MIN_MM_S2):
        key = self.identity(health)
        if self.key is None or key[:2] != self.key[:2]:
            self.baseline(health)
            return None
        if key != self.key:
            self.key = key
            self.pending = dict(count=key[2], session=key[0], calibration=key[1],
                                peak_mm_s2=None, action='record-only')
            self.events.append(self.pending)
            if ignore_motion(health):
                self.pending['action'] = 'speed-change-ignore'
                result = dict(self.pending)
                self.pending = None
                return result
        elif self.pending is None:
            return None
        event = self.pending
        old_peak = event['peak_mm_s2']
        peak = health.get('last_bump_peak_mm_s2')
        known = isinstance(peak, (int, float)) and isfinite(peak) and peak > 0
        if known:
            event['peak_mm_s2'] = max(old_peak or 0, peak)
        # Missing strength cannot silently suppress an otherwise valid event.
        if not known or event['peak_mm_s2'] >= minimum_mm_s2:
            event['action'] = 'react'
            self.pending = None
            return dict(event)
        if old_peak != event['peak_mm_s2']:
            return dict(event)
        return None
