<!-- @(#)tag-bearing-approach.md 3.2.rollup.1 2026/11/13 19:43:59 -->
# Visible tag 15 bearing approach

When a stationary homing scan cannot supply a position fix, a clearly decoded
mapped tag 15 at camera range greater than 2.5 m and at most 4 m can supply a
direction. This does not relax the localization distance limit or create a
room position. Camera translation is transformed into robot coordinates using
the calibrated camera mount. The recorded heading is relative to current wheel
yaw; logs retain the bearing, capture time and wheel distance.

Eligibility requires zero Hamming corrections, at least twice the localization
minimum decision margin, pose error at most half its configured maximum, finite
values, and a target within 35 degrees of robot forward. Two consecutive
stationary scans must agree within 3 degrees. Unstable bearings stop after three
attempts. Weak, near or unknown detections cannot trigger this approach.

Rosie uses existing 42 mm/s, 100 ms pivot/forward pulses and measured settling.
After at most 150 mm of measured centre travel she stops and rescans. A bearing
expires after 20 seconds. Total bearing-guided travel is limited to 1.2 m per
homing task. Losing the target stops the task instead of searching while moving.
A confirmed position fix resumes ordinary mapped navigation and arrival checks.

Existing fresh-sensor, odometry continuity, bumper, cliff/wheel-drop, phone impact,
battery and motion-lease checks remain active. Available room poses also retain
mapped motion checks. A direction alone cannot establish a clear mapped route
when room position is unknown; the short moves rely on the existing live safety
sensors. This feature does not provide camera-based obstacle avoidance.


## November13 homing rollup

Bearing-only guidance now accepts strong tag15 reads at corrected camera ranges
above2.5m and through5m, retaining the quality and forward-facing bearing checks.
The total bearing budget is3000mm with stopped rescans every150mm and a20s
per-view freshness bound. Full pose gates remain at2.5m. This covers the prior
4.07m target that caused a search despite a clear decode.

Optional homeward grout guidance qualifies three fresh frames with confidence
≥80%, line angle≤5° and lateral camera-line error≤30mm on a direct mapped route.
The Tag15Return controller remains active:400mm stopped re-localization,
near-tag final confirmation, slow pulses and two-scan≤300mm validation. Bumper
contact stops homing rather than reporting a successful contact arrival.
GridRunner build10 supplies type7 attitude for the guarded IMU heading nudge.
See [current range/navigation settings](tag-range-correction.md).
