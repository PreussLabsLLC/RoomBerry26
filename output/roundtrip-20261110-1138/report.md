<!-- @(#)report.md 3.2.analysis.1 2026/11/10 11:54:49 -->
# Tag15 and back to tag16: heading and position disagreement

Heading changes agreed closely outbound, but the phone reported substantially
less translation than the wheel odometry. Heading agreement also deteriorated
on the return. Healthy tracking tones did not guarantee accurate metric position.

## Relative phone versus wheel comparison

Both estimates start from the same stationary position and heading at11:39:10,
before the first move. Scale is fixed at1. Wheel position is integrated directly
from the sensor CSV, without subsequent tag corrections. The phone camera pose
is converted to robot centre using the configured dashboard mount/lens offset.
No trajectory, scale or endpoint fitting is applied.

| Checkpoint | Wheel-recorded travel | Phone–wheel position separation | Phone minus wheel heading |
| --- | ---: | ---: | ---: |
| First confirmed tag15 capture,11:41:11 |3.067m|0.811m|−0.20°|
| Last tag15 validation capture,11:42:35 |4.377m|1.073m, unqualified phone|unqualified phone|
| Tag16 return capture,11:45:07 |9.111m|0.442m|−5.19°|

Among usable outbound samples, absolute heading disagreement is0.27°median,
0.72°at95th percentile, and1.97°maximum. Position separation grows to1.112m
before tracking becomes limited. In the usable return portion, absolute heading
disagreement reaches8.64° (median6.26°); it ends around5.2° at the tag16 capture.
After48seconds stationary, phone heading changes another~0.7° and separation
is0.445m. A stationary normal-tracking status does not imply zero pose drift.

Two early nominal500mm steps illustrate the translation difference: wheel
measurements501/513mm versus phone robot-centre displacement299/321mm. Those
phone endpoint windows report usable tracking. These are disagreements between
estimates, not proof of true robot travel, wheel slip or a specific AR scale fault.

## Tracking quality and the door

One fresh phone session9257763700918216142 spans11:38:43–11:45:55.4320packets
have no sequence gaps;3986report normal and334report limited/insufficientFeatures.
The insufficient-features interval is11:42:30.498–11:43:03.794, about33seconds,
near tag15 and the start of the turn back. The user confirms a featureless door
there and plans to add a poster. This fits the reported feature-loss location;
the poster's effect has not yet been measured. The earlier0.81m discrepancy
predates that limited interval and needs separate assessment.

Four repeated camera-frame timestamps were de-duplicated for interpolation,
leaving4316unique frames. Limited/stale frames are excluded from qualified
summary maxima and heading percentiles; orange plot bands flag the feature-loss
interval. The phone's feature-count median is5 across the recording.

## Independent tag checks, with a separate offline alignment

No live qualified starting tag16 anchor was recorded. For an additional room
check, each estimate is independently aligned once to the first confirmed tag15
capture at11:41:11.240. This is an explicitly offline single-pose alignment,
not the live tag16 calibration and not a fit to the later path. Its position
errors are therefore distinct from the common-start relative separation above.

| Later confirmed tag | Phone–tag position difference | Wheel–tag position difference |
| --- | ---: | ---: |
| Tag15,11:41:33 |96mm|71mm|
| Tag15,11:42:00 |131mm|122mm|
| Tag15,11:42:13 |138mm|153mm|
| Tag15,11:42:35 |206mm, phone limited|246mm|
| Tag16,11:45:07 |764mm|783mm|

At the last tag16 fix, corresponding heading differences from the tag pose are
phone+7.78° and wheel+12.78°. Tag-derived room pose, surveyed geometry, camera
calibration and mount values have their own uncertainty. These results do not
establish either wheels or phone as ground truth; the endpoint is near tag16
but is not assumed to be the exact starting pose or heading.

Actual detector capture times, rather than delayed log completion times, are
used. The selected offline tag15 anchor pairs with a normal phone frame within
34ms; five nearby frames vary by<0.04mm and<0.01°, with stationary wheel readings.
The initial relative reference pairs within12ms, with stationary wheels and
<0.3mm/<0.03°phone variation. Pi epoch-minus-monotonic span is2.51ms over the run.
Sensor recording/polling and network clock-offset estimation still introduce
timing uncertainty; they cannot be treated as precise hardware synchronization.

## Why tag15 approach stopped

The final confirmed robot-centre range was356mm, exceeding the300mm validation
limit by56mm. The controller stopped with `tag15 validation outside 300mm`.
The camera-to-tag range was~250mm, which is a different measurement from robot
centre range. This run reached the tag15 area but did not pass its completion
criterion. The return to tag16 was manually steered.

## Artifacts and reproduction

[Comparison plot](comparison.png), [PDF](comparison.pdf), [metrics](metrics.json),
[sampled comparison](comparison.csv), [tag checks](tag-checks.csv).
Run `.venv/bin/python output/roundtrip-20261110-1138/analyze.py` from the repository
root. Source files are the supplied113843NavLink binary, sensor CSV, roomberry.log
and local autonomy.json. Script asserts single phone session/odometry epoch,
monotonic sample times and stationary qualified comparison anchors.
Read-only analysis: no source/control/configuration changes or deployment,
and no new robot movement or phone/AR/map commands.
