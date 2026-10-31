"""Asynchronous timestamped PNG map recording, one directory per service run."""
# @(#)roomberry_map_log.py 2.3.map-log.1 2026/10/30 18:30:00
import csv
from datetime import datetime
import logging
from pathlib import Path
from threading import Condition, Thread
from time import monotonic, time

from roomberry_map_image import render_map


class MapPngRecorder:
    """Keep only the latest pending snapshot if rendering falls behind.

    Capture the map under its own lock; PNG rendering and disk writes happen on
    this worker, never under the mission's coordination lock. Archives are not
    automatically pruned. Failures disable recording without stopping navigation.
    """
    def __init__(self, mapper, tags=(), directory='/var/log/roomberry-maps',
                 interval_s=30, logger=None):
        self.mapper = mapper
        self.tags = tuple(tags)
        self.directory = Path(directory)
        self.interval_s = max(1.0, float(interval_s))
        self.logger = logger or logging.getLogger('Roomberry')
        self.path = None
        self._condition = Condition()
        self._pending = None
        self._closing = False
        self._disabled = False
        self._last_request = float('-inf')
        self._sequence = 0
        self._thread = Thread(target=self._run, name='roomberry-map-log', daemon=True)

    @classmethod
    def from_config(cls, config, mapper, tags=(), logger=None):
        if config is None or not config.get('enabled', True):
            return None
        return cls(mapper, tags, config.get('directory', '/var/log/roomberry-maps'),
                   config.get('interval_s', 30), logger)

    def start(self):
        try:
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            self.path = self.directory / ('roomberry-maps-' + stamp)
            self.path.mkdir(parents=True, exist_ok=False)
        except OSError:
            self._disabled = True
            self.logger.exception('Map PNG recording disabled: cannot create %s.', self.directory)
            return
        self.logger.info('Map PNG session log: %s (interval %.0f s).', self.path, self.interval_s)
        self._thread.start()
        self.request('service startup', force=True)

    def request(self, reason='periodic', mode='', force=False):
        with self._condition:
            if self._disabled or self._closing or not self._thread.is_alive():
                return False
            now = monotonic()
            if not force and now-self._last_request < self.interval_s:
                return False
            self._last_request = now
            # Timestamp the snapshot, not its later rendering/write completion.
            epoch = time()
            try:
                snapshot = self.mapper.snapshot()
            except Exception:
                self._disabled = True
                self.logger.exception('Map PNG recording disabled: snapshot failed.')
                return False
            if self._pending is not None:
                self.logger.debug('Coalescing pending map PNG snapshot into %s.', reason)
            self._pending = (epoch, snapshot, reason, mode)
            self._condition.notify()
            return True

    def close(self):
        with self._condition:
            self._closing = True
            self._condition.notify()
        if self._thread.is_alive():
            self._thread.join()  # Drain the final pending snapshot.

    def _run(self):
        try:
            with (self.path / 'index.csv').open('w', newline='') as index:
                writer = csv.writer(index)
                writer.writerow(('timestamp', 'epoch_s', 'filename', 'mode', 'reason'))
                index.flush()
                while True:
                    with self._condition:
                        self._condition.wait_for(lambda: self._pending is not None or self._closing)
                        if self._pending is None:
                            return
                        epoch, state, reason, mode = self._pending
                        self._pending = None
                    timestamp = datetime.fromtimestamp(epoch).astimezone()
                    self._sequence += 1
                    filename = 'map-{}-{:06d}.png'.format(
                        timestamp.strftime('%Y%m%d-%H%M%S-%f'), self._sequence)
                    payload = render_map(state, self.tags,
                        caption='{} | {} | {}'.format(timestamp.isoformat(timespec='seconds'), mode, reason))
                    target = self.path / filename
                    temporary = target.with_suffix('.png.tmp')
                    temporary.write_bytes(payload)
                    temporary.replace(target)
                    writer.writerow((timestamp.isoformat(timespec='microseconds'),
                                     '{:.6f}'.format(epoch), filename, mode, reason))
                    index.flush()
                    self.logger.debug('Recorded map PNG: %s (%s).', target, reason)
        except Exception:
            with self._condition:
                self._disabled = True
            self.logger.exception('Map PNG recording disabled after archive write/render failure.')
