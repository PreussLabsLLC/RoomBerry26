<!-- @(#)report.md 3.1.grout.19 2026/11/05 -->
# Three trips in the 11:59 session

Sources: uploaded roomberry.log, roomberry-sensors-20261105-115925.csv and final
map snapshot map-20261105-121228-253896-000051.png. Script analyze.py and
metrics.json/distances.csv preserve calculations. No control changes made.

## Distances

| Run/start | Outbound to confirmed line end | Net encoder return to final stop | Return minus outbound | Threshold clearance |
| --- | ---: | ---: | ---: | ---: |
|1 /11:59:50, phone LED off|3103.4mm|3155.0mm|+51.6mm|152.8mm|
|2 /12:06:27|4530.6mm|4563.7mm|+33.1mm|152.1mm|
|3 /12:10:00|4570.0mm|4600.7mm|+30.7mm|152.5mm|

Outbound uses the settled line-end record; return uses sensor distance at the
threshold and nearest sample0.3s after the final stop, including coast. Net
return includes the clearance move, later recoveries and manual pad moves.
It is signed encoder displacement, not an independently measured floor distance
or sum of all forward/backward motion. Absolute return-path readings were
3163.1,4566.1,4601.2mm respectively. First trip required several separate homing
attempts; its table entry aggregates the whole return to12:06:12.520.

Runs2/3 differ39.48mm outbound(.87% of their4550.30mm mean). Their starts were
at session distance+90.7 and+143.1mm, while endpoints were-4439.9 and-4426.9mm.
Thus start positions differed52.5mm, and endpoint positions only13.0mm in the
continuous encoder coordinate. This is encouraging endpoint consistency, but
wheel odometry cannot independently establish physical repeatability or slip.
Previous11:36 settled distance4537.3mm lies between these two full-length runs.
All clearance moves reached~152mm, consistent with a150mm target and polling coast.

Run1 was1427–1467mm shorter than the other runs. User confirms the iPhone LED
was off for run1, so it should be excluded from full-threshold repeatability.
That is a plausible explanation rather than a proven illumination measurement:
line-end checks at3013.9 and3036.4mm regained the line; a third at3094.9mm stayed
lost and confirmed at3103.4mm. The algorithm intentionally treats sustained
fresh no-line reports as endpoint, so insufficient illumination can cause early
return. In continuous session encoder position, its endpoint was~1.35m short
of the later endpoints; small start-pose changes do not explain that difference.

## Return outcome and scans

All three trips ended on physical front bumper contact: run1 left bumper,
runs2/3 both. They were logged as safety stops rather than mission completion.
Arrival classification remains a separate issue; physically returning does not
mean the software declared success. Earlier run1 return attempts also encountered
stale phone/sensor data, inconsistent stationary fixes and manual repositioning.

Scan counts/time:18/94.84s,15/69.63s,7/35.75s for trips1/2/3. Later trips required
less recovery. Runs2/3 recorded217/217 and219/219 outbound cruising samples locked;
stationary endpoint-check states are not included in those sample counts.

## Why the map looks odd

The final uploaded snapshot contains accumulated green coverage and zigzag red
traces near tag15. It is not independent evidence of those physical robot paths.
It combines wheel integration, provisional manual tag15 starts and accepted
camera-pose corrections, and leaves earlier trace/coverage in place after fixes.

Tag estimates still disagree with physical line heading and with each other:
- Run2 accepted a293.5mm/19.6degree relocation at12:08:25, despite two agreeing
  stationary frames. Its tag-derived heading was-18.2degrees and lateral world
  coordinate1454.8mm versus nominal camera-centered robot lane1211mm.
- Run3's two rejected2m checkpoint poses differ~500.5mm and17.3degrees while
  stationary. Rejected poses do not directly move the trace; they show that
  solving the tag image still produces uncertain world pose.
- Run3 accepted a125.7mm/13.6degree correction at the1m checkpoint; final tag fix
  still reported-14.1degrees heading. Such pose rotations bend the subsequently
  integrated wheel trace even with good visible-stripe control.
- The map update calls coverage interpolation between successive displayed poses.
  In paths where a relocation does not reset that previous pose, a localization
  jump can paint a fictitious connecting sweep. Existing coverage is also not
  rebuilt into a consistent frame when a later fix changes the anchor.

Therefore the full-length distance measurements are more repeatable than the
world-map trace. Likely follow-up: distinguish localization jumps from physical
travel in map rendering/coverage, and investigate tag yaw/pose calibration or
solver ambiguity before loosening acceptance. Two consistent frames can share
systematic bias; agreement alone does not validate absolute pose. No calibration
root cause or physical veering magnitude can be proved from the map alone.

No robot motion, deployment, control edits or acceptance changes made in this review.
