"""Reproduce battery, phone-step and serial diagnostics for the 20:46 run."""
import contextlib
import csv
from datetime import datetime
import io
import json
from pathlib import Path
import runpy
import numpy as np

OUT = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    v = runpy.run_path(str(OUT/'analyze.py'))
rows = v['sensor']
summary = {}
for key in ('battery_voltage_v', 'battery_current_a', 'battery_percent',
            'temperature_c', 'left_motor_current_a', 'right_motor_current_a'):
    values = v['sf'](key)
    low, high = int(np.argmin(values)), int(np.argmax(values))
    summary[key] = dict(min=float(values[low]), min_time=rows[low]['timestamp'],
                        max=float(values[high]), max_time=rows[high]['timestamp'],
                        median=float(np.median(values)))
summary['sensor_poll_failures'] = sum('Roomba sensor poll failed.' in s for s in v['lines'])
summary['serial_write_timeout_tracebacks'] = sum(s.startswith('serial.serialutil.SerialTimeoutException:') for s in v['lines'])
summary['phone_valid_fraction'] = float(np.mean(v['valid']))
anomalies = []
for i in np.where(v['motion_ok'] & (v['step'] > 30))[0]:
    anomalies.append(dict(time=v['stamp'](v['nt'][i+1]),
        axle_step_mm=float(v['step'][i]),
        lens_step_mm=float(np.linalg.norm(v['xy'][i+1]-v['xy'][i])),
        interval_s=float(v['nt'][i+1]-v['nt'][i]),
        features=v['nav'][i+1]['feature_count']))
with (OUT/'phone-motion-anomalies.csv').open('w') as f:
    writer=csv.DictWriter(f, fieldnames=anomalies[0]);writer.writeheader();writer.writerows(anomalies)
(OUT/'diagnostics.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
