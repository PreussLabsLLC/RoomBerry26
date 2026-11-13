<!-- @(#)report.md 3.1.wall.1 2026/11/08 18:30:00 -->
# WALL sensor measurements, 2026-11-08

The uploaded measurements do not demonstrate usable 100 mm wall tracking.
The final position is identified as at the wall by the operator, not by a
recorded distance measurement. Neither signal can establish cabinet-overhang
clearance from these measurements.

Sources: roomberry/logs/roomberry.log and the sensor CSV sessions ending
180818 and 181052. The latter contains 998 samples, 18:10:52.311–18:13:13.658;
the application log extends to18:13:20.977. Times below are logged timestamps.

## Observations

Stationary encoder plateaus in the 181052 sensor session:

| Logged interval | Encoder distance, mm | Samples | Old wall signal min/median/max |
| --- | ---: | ---: | --- |
| 18:10:52.311–18:11:28.114 | 0.0 | 241 | 0 / 0 / 1 |
| 18:11:31.022–18:12:24.473 | 191.8 | 388 | 2 / 3 / 4 |
| 18:12:29.628–18:13:13.658 | 293.4 | 312 | 29 / 30 / 32 |

These encoder distances are not perpendicular wall gaps. Requested and applied
wheel velocities were zero throughout; recorded encoder changes are consistent
with external repositioning, not an autonomous wall-following run. Encoders
alone do not establish the direction or geometry of uncommanded movement.

In the last10seconds of the sensor recording, right light-bumper signal was
117/123/128 min/median/max, versus wall signal29/30/32. Right-front light-bumper
signal was0–2. No physical bumpers, wheel drops or binary wall detections asserted
in either uploaded sensor session. Side proximity need not press a front bumper.

All593 application WALL samples were in clearance stage with null target.
Capture requests failed at18:11:12 and18:11:38, with simultaneous raw wall
signals0 and2–3 respectively, below the code's minimum10. There was no successful
reference capture. First mission timed out after90seconds at18:12:32; a second
start at18:12:51 was still waiting at the end. No tag anchoring, departure,
acquisition or autonomous wall following occurred in this recording.

## Sensor resolution and input selection

The iRobot-authored2018 Create2/Roomba600 Open Interface specification documents:

| Input | Packet | Documented range | Meaning |
| --- | ---: | ---: | --- |
| Wall signal | 27 | 0–1023 | Raw intensity, ten-bit numeric range in a two-byte field |
| Right light-bumper signal | 51 | 0–4095 | Raw intensity, twelve-bit numeric range in a two-byte field |

The specification deprecates packet27 and recommends packet51 for its higher
resolution. This is numeric intensity resolution, not a specified distance
resolution or fourfold range/accuracy improvement. Both are already recorded.

Source: [iRobot specification, printed pages28 and32](https://cdn.hackaday.io/files/1785657639724960/iRobot_Roomba_600_Open_Interface_Spec.pdf).

## Software findings and recommended changes

- WALL currently controls from the deprecated packet27. Evaluate packet51
  as the primary right-wall feedback, using its own measured baseline and
  thresholds; the old thresholds cannot simply be reused.
- A close-wall reference must not be labelled100mm. Current capture trusts
  the operator-supplied position and checks signal stability, not distance.
  Here neither capture succeeded; no false reference was actually installed.
- Capture checks every100ms and rejects repeated sensor timestamps, while
  this recording's median sensor interval is140ms. A separate sampling flaw
  can reject an otherwise stable signal. Wait for five distinct samples within
  a bounded timeout rather than requiring each100ms read to be new. The generic
  error presently hides which condition failed.
- Establish actual clearance capability with stationary measurements at known
  gaps, using both raw signals. This recording contains no ruler-labelled gaps,
  so it cannot establish a maximum sensing distance or mm/count conversion.
  If there is no useful signal at100mm, preserving that clearance needs another
  source of wall geometry/range rather than lowering the threshold and moving
  closer beneath the overhang.

Analysis only. No control changes, deployment or robot commands were made.
