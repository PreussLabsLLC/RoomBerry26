<!-- @(#)report.md 3.2.analysis.3 2026/11/10 13:45:00 -->
# Round trip with scan cool-offs, 2026-11-10 13:33–13:42

The run completed the physical round trip with continuous normal phone tracking.
The tag15 approach stopped safely but did not satisfy its final distance check.

- One phone session, 5,130 packets, all normal tracking, no limited interval;
  one sequence gap. Median visible features 10 (prior poster run 18).
- Wheel travel between initial/final tag16 captures: 9.377 m.
- All 12 scans delivered spoken results and logged speech completion. Each
  announced a clear tag15 or tag16 read. Spurious weak tag4/tag9 detections
  were excluded from the announcements and rejected as unknown landmarks.
- Three new cool-offs executed per scan, approximately one second each.
  Initial scan 17.535 s; subsequent scans 7.364–8.531 s, median 7.924 s.
- No sensor poll failures during scans, including initial detector startup.
  One later poll failed at 13:41:33.196 with a short read (64/80 bytes),
  before the final scan started at 13:41:47.851. At 13:41:31.461 a left15
  command was refused because fresh ready sensors/safety conditions were
  unavailable. Logs do not establish a specific physical hazard or fault cause.
- Roomba battery 92.2% to 90.1%; voltage 14.834–15.669 V. No sudden charge
  collapse. A STATUS speech completed at 13:40:55.983, after 30 seconds quiet
  from the 13:40:20.418 completion, consistent with the idle battery reminder;
  the delivery log does not contain its words or iPhone percentage.

## Independent heading and position checks

Reused the previous analysis with this run's recordings. One initial tag16
alignment, fixed mount/lens correction, unit scale, no fitted path or later
corrections. These are offline free-running tracks, not the live tag-corrected
mission pose. Stationary capture pairing checks passed. See metrics.json and
comparison.png/PDF for values and plot.

| Final tag16 check | Position error against tag | Heading error against tag |
|---|---:|---:|
| iPhone | 705 mm | -1.37 degrees |
| Free wheel integration | 124 mm | +20.88 degrees |

Final tag16 pose was 38 mm from the initial pose, with -3.95 degrees heading
change. Phone displacement from its aligned start was 740 mm; wheel displacement
149 mm. Thus good phone tracking status still does not imply accurate metric
position. Heading returned much closer to the tag reference on the phone than
on wheels. Compared with the prior run, phone endpoint position error increased
from 520 to 705 mm; wheel heading error decreased from 32.52 to 20.88 degrees.

At tag15 scans, phone position error was approximately 0.96–1.30 m and heading
error -12 to -19 degrees; wheel errors were 0.41–0.70 m and -2 to -10 degrees.
Phone/wheel separation peaked at 1.103 m; heading disagreement peaked at 22.38
degrees. Outbound heading disagreement p95 10.72 degrees, return p95 20.55.

## Tag15 stopping result

At 13:39:12.014 the final validation pair agreed closely and was accepted.
The resulting robot-centre-to-tag distance was 351 mm, outside the 300 mm
completion threshold. The mission stopped with the explicit validation warning.
The spoken camera range was 244.6 mm; that measures from the camera, whereas
navigation checks robot-centre range, including the mount offset. The roughly
83 mm validation innovation also explains why a predicted near-300 mm stop
can validate farther away. This is a safely rejected arrival, not a completed
homing result; no controller changes were made during this analysis.
