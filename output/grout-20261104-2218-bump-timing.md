# Speed and phone bump timing — 22:18 session

Plots: grout-20261104-2218-speed-bumps.png (overview) and
-speed-bumps-starts.png (six launch windows); SVG, event CSV and JSON accompany.
Reproduce with roomberry/plot_grout_bumps.py using the roomberry log, sensor CSV
and NavLink recording from the 22:18:35 session. No control changes.

## Timing against first accepted outbound wheel command

| Attempt | Bump after command | Classification |
|---|---:|---|
| 1 | 95 ms | immediate launch |
| 2 | 4888 ms | later during outbound travel |
| 3 | 83 ms | immediate launch |
| 4 | 83 ms | immediate launch |
| 5 | 95 ms | immediate launch |
| 6 | 101 ms | immediate launch |

Five consistent near-launch events strongly support acceleration/drivetrain or
mount jolt being counted as threshold contact. Attempt 2 needs another explanation
(steering transient, floor feature, handling or other motion). No physical contact
can be inferred solely from acceleration.

The shared iPhone detector uses gravity-removed CMDeviceMotion.userAcceleration.
Its low-amplitude branch triggers at >=0.25 g with jerk >=40 g/s. Thus an abrupt
launch transient can qualify. Raw 100 Hz IMU and jerk are not in this recording;
the graph shows interval peak acceleration from health packets, plus impact peaks.

Event times use receipt wall-clock minus the phone send-to-bump timestamp delta;
unknown network latency remains. Commands use actuator acceptance log timestamps,
not exact motor onset. Treat the millisecond numbers as approximate alignment.
The overview's measured speed is wheel-odometry distance delta divided by the
sensor interval; it is not independently measured floor speed.

Red dots are events that ended outbound; orange dots are other bump events.
The detector updates an episode's peak during the next 150 ms, so plotted dots
use the maximum subsequently reported episode peak. The earlier run review used
the first reported peak: those are not necessarily identical. Both first and
updated peak values are retained in the event CSV/JSON. Attempt 2's large orange
near-start event happened before its drive command and was included in its initial
bump baseline; the later red event actually caused its threshold classification.
