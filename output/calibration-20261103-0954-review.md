<!-- @(#)calibration-20261103-0954-review.md 3.1.review.1 2026/11/03 10:00:00 -->
# iPhone X threshold run: November 3, 09:54

The reverse leg reached the physical threshold reported by the user and stopped
on a new iPhone bump. GroundHog remained valid throughout the outbound leg,
turnaround, and partial return. A distinct phone impact stopped the return;
tracking loss did not cause this abort. No control code was changed.

## Timeline and stop cause

| Event | Time | Wheel distance from local start |
|---|---|---:|
| Local baseline | 09:54:34.514 | 0 mm |
| Threshold turnaround checkpoint | 09:55:50.034 | -4564 mm |
| Last return motion sample | 09:56:25.959 | -2490 mm |
| Return impact / abort | 09:56:26.164 / .182 | no final pose checkpoint |
| Stationary sensor observation | 09:56:27.108 | -2462 mm |

The outbound leg took 75.52 seconds. Abort occurred 111.67 seconds after the
baseline, 36.15 seconds after the turnaround checkpoint (including the hold).
The robot recovered about 2.10 m of signed wheel distance before stopping,
roughly 46% of the outbound distance. Its remaining distance to the starting
wheel coordinate was about 2.46 m. These are odometry values, not surveyed truth.

The threshold event increased bump count 7→8 and peaked at 4813 mm/s²
(0.49 g). Any new reverse bump triggers turnaround, so it correctly stopped
even though this peak is just below the return-leg 0.5 g threshold.
The return event increased count 8→9, peaking at 6223 mm/s² (0.63 g), above
the 4903 mm/s² return-stop threshold. It was a new event about 36 seconds after
the threshold contact, not a late refinement of the threshold event.

The stop operation completed at 09:56:26.227, followed by restoration of
Passive mode at .262. Sensor CSV shows both applied wheel commands zero and
stationary distance by 09:56:27.108. The older applied command in the .205
snapshot is not evidence of continued motion after the completed stop.
No physical bumper, wheel drop, hard hazard or wheel overcurrent was recorded
in the active-run sensor samples. The logs cannot distinguish a rear-phone
contact, mount/cable vibration, floor jolt or handling as the cause of the
return acceleration. The phone impact monitor was the decisive stop source.

## iPhone X tracking and processing

For the baseline-to-abort interval:

- 1117/1117 motion reports valid; same session, calibration and continuity 17.
- Zero rejected-frame increments and zero missing motion packet sequences.
- 3348 accepted-frame increments, approximately 30.0 accepted frames/second.
- Processing median 27.39 ms, maximum 35.42 ms. Recent SE recordings were
  roughly 45–48 ms median; yesterday's successful SE recording was 35.21 ms.
- Frame age at send median 87 ms, maximum 110 ms; phone/Pi clocks are not
  synchronized, so these are phone-local ages, not end-to-end latency.
- Median CPU 56.5%; battery 94→93%; thermal nominal/fair, no serious state.
- 480×640 images; at least 107 candidate/inlier samples in every transmitted
  motion snapshot, median candidates 258 and median inliers 256.
- Fit RMS median 0.086 mm, maximum 0.811 mm; this is internal consistency,
  not independently measured position accuracy.

This is strong evidence that the X supplies more processing margin with this
workload. It does not establish that computation was the sole cause of the SE
failures: phone optics, mount, battery, and lighting also differ. No processing
or tracking failure occurred at the return abort.

## Heading and distance estimates

Maximum absolute GroundHog heading was 3.18° outbound and 3.60° returning.
Wheel heading reached 3.14° and 4.99° respectively. Steering peaked at 0.222
outbound and 0.251 returning, below the 0.35 cap, with no saturated samples.
There is no evidence here requiring higher steering gains.

At threshold, local poses were:

| Estimate | X mm | Y mm | Heading |
|---|---:|---:|---:|
| Wheels | -4563 | +64 | -0.65° |
| GroundHog | -4349 | -63 | -0.26° |

Their separation was 249 mm, including 213 mm longitudinal and 127 mm lateral
disagreement. This repeats the roughly 5% shorter phone distance seen before;
healthy tracking does not establish correct distance scale or lateral accuracy.
The last return motion sample was wheels (-2491, -40) and phone (-2379, -80).

If the exact robot-reference-point displacement to contact were independently
verified as 4799 mm, wheel travel at the stop-command checkpoint would be
about 235 mm short (4.9%) and phone longitudinal displacement about 450 mm short
(9.4%). Those are conditional comparisons, not calibration results: check the
initial robot placement, phone overhang/contact geometry, actual surveyed span,
and stop settling against overhead video. GroundHog reports 85 mm camera
height; verify that measurement for the X mount rather than inheriting the SE
value. No wheel or camera scale should be changed from this run alone.

## Next measurement

Keep 50 mm/s and the existing heading gains while checking the return-impact
location on overhead video. If the path was clear, inspect the phone mount and
power cable for a jolt before considering an impact-policy change. Preserve
reverse threshold stopping. The video can also resolve distance scale and the
opposite-sign lateral estimates. Confirm the X's measured mount parameters.

Sources: roomberry/logs/roomberry.log;
roomberry/logs/sensors/roomberry-sensors-20261103-095424.csv;
roomberry/logs/navlink/roomberry-navlink-20261103-095424-0000.bin.
Machine-readable metrics: calibration-20261103-0954-metrics.json.
