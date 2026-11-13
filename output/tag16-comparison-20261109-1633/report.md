<!-- @(#)report.md 3.2 2026/11/09 16:41:15 -->
# 16:33 WALL run — stop reason and fixed-anchor disagreement

The robot stopped at **16:35:37.046 Pacific** with
`left obstacle bypass exceeded 1500 mm/90 second bound`.
The bypass began at16:34:59.610, only37.436 seconds earlier, so the accumulated
**1500mm bypass-distance limit** triggered. Total wheel-derived path was3545.58mm.
There were three bumper-contact recoveries and two ordinary wall-loss searches.
Wall signal was reacquired, but no `obstacle_bypass_heading_resumed` success was
recorded. Final follow heading91.88° was47.69° from bypass entry44.19°, outside
the20° handoff window; final averaged IR signal10 was also below20. The bypass
therefore remained active. This was an abort, not arrival at tag15.

At the last synchronized sample before the abort, wheel-derived distance to
tag15 was1532mm; phone-derived distance was2244mm. Neither reached the300mm
validation goal, and this run provides no final tag15 fix to resolve accuracy.
No controller limits or steering behavior were changed for this analysis.

## Tag16 anchoring worked

The initial robot anchor was approximately room(3123.65,1137.10)mm, heading
−102.28°. The phone-frame pairing differed from the tag capture by25.36ms.
The logged mount matches the dashboard configuration: lens(+10,+180)mm,
optical-forward heading with−20° camera-to-body correction and15° upward pitch.
Scale stayed1 and the transform stayed fixed; there is no trajectory-based fit.
The first live comparison was only0.50mm /0.053° apart at the stationary anchor.

The binary contains990 consecutive type6 packets (983 normal,7 initializing),
with no sequence gaps. The plot uses828 normal frames after the recorded anchor.

| Measurement | Result |
| --- | ---: |
| Separation at last phone frame before stop |760.43mm|
| Heading difference at that sample |−11.91° (phone minus wheel)|
| Separation at final recorded phone frame |767.19mm|
| Maximum separation |769.00mm|
| Final heading difference |−11.84°|
| Maximum absolute heading difference |13.61°|

At the stop sample the phone estimate was722.10mm behind the wheel estimate in
room X and238.38mm lower in room Y. Much of the position discrepancy accumulated
during the initial outbound stretch, reaching roughly600mm before the fridge
bypass. Most heading discrepancy appeared during the initial turn. This pattern
helps target the next validation but does not establish which sensor is correct.
AR scale/drift, wheel/body slip, mount-angle uncertainty and tag calibration may
contribute. Encoder movement is not an independent body-position measurement.
The old clip-mount plot is not directly comparable to this fixed dashboard-anchor
result, so these numbers are not evidence of an improvement from the old1.31m.

## Speed response

For commands stable for at least0.5seconds, duration-weighted encoder speeds were:

| Command | Left | Right |
| --- | ---: | ---: |
|50mm/s|69.25mm/s|65.23mm/s|
|80mm/s|91.20mm/s|92.13mm/s|

Both still exceeded their commands in this data. This supports continuing to
measure actual response; it does not prove a specific firmware mechanism or
body speed. No new speed correction was inferred from the phone positions.

The Pi verified another **kitchen-261109** map save at16:35:38.349 and then stopped
the phone session. Existing same-named maps remain separate UUID-backed entries.

[PNG plot](disagreement.png) · [PDF](disagreement.pdf) · [CSV](disagreement.csv)
· [metadata/metrics](metrics.json). Generated with `roomberry/tools/plot-trek-anchor.py`
from the supplied16:33 Roomberry log, NavLink binary and sensor CSV. Raw archives
were not changed; no robot/phone commands or deployment were performed.
