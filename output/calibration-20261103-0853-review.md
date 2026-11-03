<!-- @(#)calibration-20261103-0853-review.md 3.1.review.1 2026/11/03 09:00:00 -->
# November 3 short-run review

Four starts at 08:53:32, 08:53:41, 08:53:52 and 08:54:20 all aborted on
GroundHog continuity changes after 1.008, 1.407, 1.204 and 1.403 seconds from
the local baseline. Stop commands completed and Passive mode was restored.
Wheel displacement, using sensor samples nearest the baseline and half a second
past abort, was approximately -33, -71, -47 and -66 mm respectively. Sampling
is asynchronous; these are wheel estimates, not overhead measurements.

The first abort already showed valid tracking again but a different continuity
segment. The second reported reason 4 (stale/missing frame or frame gap); the
last two reported reason 7 (insufficient texture/agreement). Raw packets confirm
rejected-frame increments and continuity breaks, including short recoveries.
The packet does not identify the detailed fit/coverage failure; phone-side
failure diagnostics are needed for that. Lighting/torch status is not logged,
so this evidence cannot establish whether the LED was on or why this session
tracked less reliably than yesterday. Higher speed is active but is not proven
to be the cause. Do not stitch across lost continuity to keep driving.

All starts report distance_target_mm=1850, although the new reverse-until-bump
startup text and 75 mm/s motion commands are present. The current code reads an
environment override before its 5000 mm default, so the deployed process still
appears to have ROOMBERRY_CALIBRATION_DISTANCE_MM=1850. Remove/update that setting
and restart before the full run. It did not cause these early aborts.

No threshold turnaround occurred. No physical bumper or hard hazard was present
in the inspected post-abort sensor samples. Overall valid motion packets were
810/823, but continuity during movement, rather than the overall percentage,
determines whether the calibration can continue.

Sources: roomberry/logs/roomberry.log,
roomberry/logs/sensors/roomberry-sensors-20261103-085308.csv,
roomberry/logs/navlink/roomberry-navlink-20261103-085308-0000.bin.
