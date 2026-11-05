<!-- @(#)report.md 3.1.grout.19 2026/11/05 -->
# 11:36 run review and recent bump comparison

## Threshold distance and clearance

First line-end brake11:37:20.822 at4528.1mm; confirmed11:37:21.830 after1.012s
and6 missing-line frames. Settled distance **4537.291mm**, unchanged during the
confirmation/settled measurements. About9.2mm coast after the initial brake.
This is robot-center wheel travel, not camera/tag distance or surveyed floor
travel. The log contains no evidence of the old continued reverse wheel spin.

Return began at30mm/s. After about19mm advance, the one-second missing-line timer
invoked tag recovery11:37:23.061, too soon to clear the scan bands. The first
scan found no reliable mapped fix; later route execution stopped for no wheel
progress11:37:46.309. A manual pad move/retry eventually resumed the line.

Implemented .19: 150mm straight forward clearance at30mm/s, without pivots or
premature line-loss tag handoff, then brake and qualify3 distinct good stripe
frames. If absent, allow1s stopped before recovery. Hard hazards, fresh telemetry,
phone impacts, wrong travel,3s no progress and12s total bound remain enforced.
The distance may be inaccurate if wheels spin; it is not a guarantee of traction.

## Tracking versus map position

Logged outbound driving samples224/224 locked, medianconfidence.987 (these exclude
stationary missing-line confirmation entries). Return168/179 locked(93.9%),
approach90/93(96.8%). Thus the phone's visible-stripe tracking was mostly good.
This app measures a line, not independent absolute robot position.

Tag-derived world position was NOT consistently trustworthy. For example,
stationary recovery scans11:39:17/22/28 produced consecutive position differences
about506mm and295mm, with large yaw differences. These cannot be explained by
wheel travel while stationary. The2m checkpoint also produced a291mm/14degree
innovation and a subsequent heading outside the straight-approach envelope.
Confirmation correctly rejected unstable fixes. Re-anchoring the wheel trace
with later accepted poses can make the map jump; confident stripe tracking does
not validate an absolute map anchor. This evidence points to tag pose estimation
instability as well as prediction drift; root cause (image geometry/pose solution,
calibration or mount) is not established by these logs alone.

The500mm checkpoint later accepted a repeated pose correction of388mm. At the
approach bound11:41:44.665 recovery re-scanned and obtained nearly identical poses
(x7503.9,y1251.3,yaw-.215rad). Returning again, BOTH front bumpers pressed at
11:41:56.736. Last preceding estimated tag range162.6mm and line error+.8mm.
The mission classified it unsafe contact instead of arrival. The tight arrival
heading envelope is a plausible blocker: accepted yaw was about12.3degrees,
while arrival allows.2rad(11.46degrees). No arrival guard relaxed in this patch.

## Scanning time and display

22 actual Vision scans,117.86s total, median4.724s, range3.752–17.039s. Most time
lost to scanning was repeated confirmation/recovery, not just a single slow
capture. First scan was17s; subsequent attempts generally4–6s. Display `SCAN`
now overrides the mode during actual scan gating and restores it afterward.
Native detector time is only part of the full stop/settle/capture/save time.

## Bump strength and locations

Phone Health archives preserve event counts and final refined episode maxima,
including events ignored by speed suppression. Event time is approximated by
Pi receipt minus the phone's reported event age. Nearest sensor row supplies
position. Below, position means **reverse wheel displacement from session zero**;
it is NOT a surveyed grout coordinate. Manual moves, restarts and slip limit
cross-run agreement. Largest peaks may be taps or contact; logs cannot identify
physical cause. Pre-recording stale event counters are excluded.

| Session | Selected outbound events: peak g @ encoder position | Strongest forward event |
| --- | --- | --- |
|09:16|.535 @.72m (short/restarted leg)|.948 @.71m|
|10:17|.338 @1.66m; .385 @2.80m; .315 @3.09m; .264 @4.61m; .544 @4.67m;1.466 @4.97m|.814 @.31m (front contact)|
|11:06|.393 @2.35m; .392 @3.56m; no recorded event at ramp|.734 @4.79m during manual forward movement|
|11:36|.403 @2.68m; .503 @2.76m; .433 @3.39m; .366 @4.19m; no event at endpoint|.419 @2.31m; other event.371 @1.54m|

The new endpoint was quiet: no bump event at4.54m. This supports using stripe end
rather than bump strength as the endpoint. Smaller mid-route events around2.7–2.8m
recur, but sparse events and wheel position uncertainty do not establish one fixed
floor obstacle. The old1.466g event may have been the reported phone tap.

Artifacts: [comparison plot](bump-comparison.png), [all events CSV](bumps.csv),
[metrics](metrics.txt), [reproducible analysis](analyze.py). CSV also includes08:41;
its large early events were near the session origin, not proof of threshold contact.

## Verification

129 grid-drive/control/tag-return/bump tests passed after changes, including full
simulated out-and-back with real tag geometry,150mm clearance, delayed line
qualification, no-line recovery, no progress and stale phone. Wire/Swift checks
passed in the broader run before the final fixture-only correction. Display tests
cover SCAN override, refresh and mode restoration. No physical commands or Pi/iOS
deployment; sync grid/control and restart3.1.grout.19.
