<!-- @(#)calibration-20261102-2115-review.md 3.1.review.1 2026/11/02 23:00:00 -->
# Calibration review: November 2, 21:15

The full 1850 mm target out-and-back completed successfully, from 21:15:22.278
to 21:16:27.280 (65.00 seconds). The run had one turnaround stop and a roughly
one-second hold. It finished normally and restored Passive mode for Clock input.
No tag scan, calibration abort, application warning, or application error is
logged in this session. No robot code was changed for this review.

## Tracking and steering

All 650 GroundHog motion reports during the run were valid, on the same session,
calibration and continuity segment (10). There were zero rejected-frame counter
increments, 1634 accepted-frame increments, and no missing UDP sequence numbers.
This is a substantial improvement over the earlier short runs. The current
recording does not include torch state, so it cannot independently verify the
LED setting or isolate illumination from the revised coverage logic.

GroundHog measured at most 3.35 degrees of heading deviation on the outbound leg
and 3.20 degrees on return. Median absolute deviations were 1.74 and 0.71 degrees,
respectively. Steering peaked at 0.234 outbound / 0.224 return, below the 0.35
limit, with no saturation. These are bounded tracking results consistent with
successful correction, not a controlled comparison against an uncorrected run.

GroundHog lateral displacement ranged from -3.7 to +17.0 mm outbound and +16.3
to +37.4 mm on return. Heading control did not remove all lateral displacement,
as expected from the heading-only controller.

## Endpoint estimates

Coordinates are millimetres in the local start frame (+X initially forward,
+Y left). These are stop-command checkpoints, not independently measured truth.

| Checkpoint | Wheel X / Y | GroundHog X / Y | Wheel / GroundHog heading |
|---|---:|---:|---:|
| Start | 0 / 0 | 0 / 0 | 0 / 0 degrees |
| Turnaround | -1837.5 / +58.2 | -1742.6 / +16.4 | -0.87 / -0.17 degrees |
| Finish | -9.8 / +37.3 | -21.0 / +34.5 | -1.52 / -0.74 degrees |

At turnaround the signed wheel distance was -1838.7 mm: 11.3 mm short of the
1850 mm target, inside the configured 15 mm tolerance. GroundHog X was about
95 mm (5.2%) shorter than wheel X. During the turnaround hold, the wheel reading
settled around -1841.2 mm and GroundHog around -1750 mm, so the discrepancy is
not simply the latest phone frame arriving behind the stop command.

At finish, GroundHog's estimated distance from the start was 40.4 mm and the
wheel pose estimate was 38.6 mm. The estimates were only 11.6 mm apart. A wheel
sample about one second after completion had signed distance -6.4 mm, showing a
few millimetres of settling beyond the finish checkpoint. Small round-trip error
does not establish correct scale: a consistent scale bias can cancel on return.

The discrepancy could be GroundHog scale (including the configured 85 mm camera
height), wheel scale/slip, or a combination. Do not apply a scale correction from
these estimates alone. Use the measured grout-inclusive tile span and overhead
trajectory to determine actual travel first.

## Data quality and hardware

- Fit support: 130–427 inliers, median 261; median 298 candidate points.
- Fit RMS: median 0.082 mm, maximum 0.302 mm. This is internal fit consistency,
  not millimetre-level absolute accuracy.
- Vision processing: median 35.2 ms, 95th percentile 40.0 ms, maximum 45.6 ms.
- Phone frame age at send: median 113 ms, maximum 160 ms; valid throughout.
- Effective accepted-frame rate: approximately 25 fps over this run.
- Delivered images: 480x640; requested camera height: 85 mm throughout.
- Phone CPU: median 61.8%, maximum 66.0%; footprint roughly 39–40 MiB.
- Thermal state: fair throughout, without a recorded serious/critical state.
- Phone tilt: at most 5.32 degrees, below the 10-degree rejection limit.
- Phone impact count stayed at 5: five older events, no new event in this run.
- All 471 Roomba sensor records were ready. No physical bumper, wheel drop,
  hard hazard, safety latch or wheel overcurrent was recorded during the run.
- Wheel motor currents: median absolute 0.106 / 0.105 A (left/right), peaks
  0.307 / 0.251 A. Robot battery estimate changed from 96.9% to 96.6%.

The main next measurement is overhead ground truth for distance scale and the
roughly 35 mm lateral return displacement. Current steering has margin; this
recording supplies no reason to increase its gain further.

## Sources

- roomberry/logs/roomberry.log (current session beginning 21:14:54).
- roomberry/logs/sensors/roomberry-sensors-20261102-211511.csv.
- roomberry/logs/navlink/roomberry-navlink-20261102-211511-0000.bin.

Phone and Pi clocks are unsynchronized. Phone records were selected by Pi
receipt timestamps; pose checkpoints use arrival freshness, not synchronized
sensor capture times. Endpoint differences include that timing limitation.
