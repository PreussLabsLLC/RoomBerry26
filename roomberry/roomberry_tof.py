"""Own the forward ToF helper and cache its latest measurement."""
# @(#) roomberry_tof.py 3.2.retrace.1 2026/11/19 12:18:44

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from selectors import DefaultSelector, EVENT_READ
import signal
from subprocess import PIPE, Popen, TimeoutExpired
import sys
from threading import Event, Lock, Thread
from time import monotonic, sleep


TOF_HELPER = Path(__file__).resolve()
MAX_SAMPLE_AGE_SECONDS = 0.25
STARTUP_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 2.0
RETRY_SECONDS = 5.0


@dataclass(frozen=True)
class RangeSample:
    distance_mm: int
    started_at: float
    completed_at: float


class ForwardTofReader:
    def __init__(self, logger):
        self.logger = logger
        self._shutdown = Event()
        self._lock = Lock()
        self._samples = deque(maxlen=4)
        self._worker = None

    def start(self):
        if self._worker is None:
            self._shutdown.clear()
            self._worker = Thread(target=self._run, name='forward-tof', daemon=True)
            self._worker.start()

    def close(self):
        self._shutdown.set()
        if self._worker is not None:
            self._worker.join()
            self._worker = None

    def sample_at(self, captured_at, paused_at, latest_at=None):
        if latest_at is None:
            latest_at = captured_at
        with self._lock:
            sample = next((row for row in reversed(self._samples)
                           if row.completed_at <= latest_at), None)
        if (sample is not None and 0 < sample.distance_mm <= 4000
                and paused_at <= sample.started_at <= sample.completed_at
                and sample.completed_at >= captured_at - MAX_SAMPLE_AGE_SECONDS):
            return sample
        return None

    def _run(self):
        while not self._shutdown.is_set():
            try:
                self._read_stream()
            except (OSError, RuntimeError, TimeoutExpired) as error:
                if not self._shutdown.is_set():
                    self.logger.warning('Forward ToF reader unavailable: %s', error)
            self._shutdown.wait(RETRY_SECONDS)

    def _read_stream(self):
        started = monotonic()
        process = Popen([sys.executable, str(TOF_HELPER)], stdout=PIPE)
        try:
            with DefaultSelector() as selector:
                selector.register(process.stdout, EVENT_READ)
                pending = b''
                deadline = started + STARTUP_TIMEOUT_SECONDS
                receiving = False
                while not self._shutdown.is_set():
                    if monotonic() >= deadline:
                        phase = 'measurement' if receiving else 'initialization'
                        raise RuntimeError(f'{phase} timed out')
                    if not selector.select(timeout=0.1):
                        continue
                    chunk = process.stdout.read1(4096)
                    if not chunk:
                        raise RuntimeError(f'helper exited with status {process.wait(timeout=0.5)}')
                    *lines, pending = (pending + chunk).split(b'\n')
                    for line in lines:
                        if self._handle_line(line, started):
                            receiving = True
                            deadline = monotonic() + READ_TIMEOUT_SECONDS
        finally:
            with self._lock:
                self._samples.clear()
            process.terminate()
            try:
                process.wait(timeout=0.5)
            except TimeoutExpired:
                process.kill()
                process.wait()
            finally:
                process.stdout.close()

    def _handle_line(self, line, started):
        if line == b'TOF_READY':
            self.logger.info('Forward ToF initialized in %.1f ms', (monotonic() - started) * 1000)
            return True
        if not line.startswith(b'TOF_SAMPLE '):
            return False
        try:
            _, distance, begin, end = line.split()
            sample = RangeSample(int(distance), float(begin), float(end))
        except ValueError:
            return False
        with self._lock:
            self._samples.append(sample)
        duration = sample.completed_at - sample.started_at
        if duration >= MAX_SAMPLE_AGE_SECONDS:
            self.logger.debug('Slow forward ToF sample: distance_mm=%s read_ms=%.1f',
                              sample.distance_mm, duration * 1000)
        return True


def _stop_on_signal(signum, frame):
    raise SystemExit(0)


def _stream_forward_tof():
    import VL53L1X

    signal.signal(signal.SIGTERM, _stop_on_signal)
    sensor = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x29)
    sensor.open()
    try:
        sensor.start_ranging(3)
        try:
            print('TOF_READY', flush=True)
            while True:
                started = monotonic()
                distance_mm = sensor.get_distance()
                completed = monotonic()
                print(f'TOF_SAMPLE {distance_mm} {started} {completed}', flush=True)
                sleep(max(0.0, 0.1 - (completed - started)))
        finally:
            sensor.stop_ranging()
    finally:
        sensor.close()


if __name__ == '__main__':
    _stream_forward_tof()
