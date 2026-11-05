<!-- @(#)README.md 2.3.analysis.2 2026/10/30 15:25:00 -->
# October 30, 15:10 ride-along

## Why tags 16 and 15 were not visited

Discovery accepted tag 1 after retreat at 15:11:58. After two missed stationary tag-2 views, the third view accepted tag 2 at 15:12:40. Intentional contact and reverse release finished at 15:12:51, and the mission selected tag 16's parking point, (3100, 1450) mm. Tag 15 was still queued behind tag 16.

There were real right-bumper events during tag-16 transit at 15:13:46 and 15:13:56, followed by reverse/turn detours and map replanning. At 15:14:21 the footprint guard refused to move and explicitly ended discovery in idle. The later wheel drop at 15:15:54 was not what originally ended the mission. The last accepted localization correction was tag 1 at 15:13:12, approximately 69 seconds before the stop.

The saved blocked cells were (26, 1) and (27, 6). At the stop, the logged robot center was (2491.738, 803.436) mm. Its distance to the blocked square (27, 6), spanning x=2349–2436 and y=522–609 mm, was approximately 202.27 mm. The guard required 174 mm body radius + 10.875 mm sampling allowance + 20 mm additional padding = 204.875 mm. Thus it rejected the starting pose by about 2.6 mm of extra padding even though the requested forward arc led away from that obstacle. The grid planner and the conservative motion guard did not impose identical clearance rules.

This was an unnecessary stop introduced by the additional guard, separate from the larger localization disagreement. The local fix allows motion that preserves starting clearance when already inside only the extra obstacle padding. The body footprint and sampling allowance must still remain clear. Motion toward the obstacle, entry into padding from outside, actual footprint overlap, and room-boundary violations remain blocked. Regression tests replay this exact pose and obstacle, its reverse heading, and actual footprint overlap. All 110 mission/mapper tests pass. The broader suite passes 217/218, with the unchanged camera annotation/font-rendering failure remaining. The fix in `roomberry_mapper.py` has not been deployed.

## Phone correlation with the measured mount

The camera lens is 145 mm aft and 22 mm right of robot center. With robot X forward and Y left, its lever arm is `(-145, -22)` mm. The analysis subtracts the rotated lever arm from each valid camera pose to estimate robot center. This matters during pivots: the lens moves through an arc while the center may stay still.

The packet heading projects camera +Y, not calibrated robot forward. Straight-motion intervals suggest a mount yaw of about +93.2° for this mount (527 qualifying half-second windows); that remains inferred rather than surveyed. The analysis uses one fixed room rotation and translation at the accepted retreat tag fix at 15:11:58, with no scale or later trajectory fitting. The old mount's approximately 180° convention was not reused.

Pi dequeue timestamps contain bursts delayed by up to approximately 5.52 seconds. As in the earlier analysis, capture uptime is aligned offline using the minimum receipt-minus-send offset, retaining unknown minimum transport latency and possible clock drift. Invalid pose packets are omitted. This is not navigation-grade clock synchronization or room calibration.

| Event | Robot/phone center separation | Robot heading minus phone heading |
| --- | ---: | ---: |
| 15:12:21, first tag-2 scan | 53 mm | −8.6° |
| 15:12:40, accepted tag-2 correction | 245 mm | −1.1° |
| 15:13:33, scan while approaching tag 16 | 489 mm | +1.8° |
| 15:13:46, first transit right-bumper contact | 517 mm | −1.3° |
| 15:13:56, second transit right-bumper contact | 569 mm | +1.3° |
| 15:14:21, discovery stop | 717 mm | −1.8° |

For the stop comparison, the full robot pose printed 0.87 seconds after the stop is paired with the phone pose at the stop; the robot remained stationary. [Trajectory plot](trajectory.png) shows the corrected phone center and sparse logged robot poses. Red connecting lines are not a full motor replay and include tag corrections. See [pose-comparison.csv](pose-comparison.csv) for the observations.

The bumper activations are genuine hardware observations; their assigned world coordinates can be wrong when localization drifts. The phone is not independent surveyed ground truth either: median feature count is 3 among usable packets, and 803 of 3101 packets (25.9%) have pose validity clear for insufficient features. The first long loss begins about 15:14:22, just after the mission stops; another lasts roughly 15:15:13–15:15:49. Valid observations just before the stop have very few features. The comparison establishes a substantial position disagreement, not which entire trajectory is correct. A second alignment at a reconstructed last tag-1 fix still gives about 0.77 m separation at the stop, so later disagreement is not removed by simply re-anchoring after that correction; that auxiliary anchor is recovered by reversing wheel integration from the next logged stationary pose and has additional timing uncertainty.

## Battery

NavLink covers 15:10:54–15:16:04, approximately 5 minutes 10 seconds. Reported battery begins at 82%, briefly reads 81%, then rises to 83% and remains there through the final packet.

| Estimated local time | Charge | State |
| --- | ---: | --- |
| 15:10:54 | 82% | Unplugged |
| 15:10:59 | 81% | Charging |
| 15:11:40 | 82% | Charging |
| 15:13:03 | 83% | Charging |
| 15:14:05 | 83% | Unplugged |
| Final packet, received 15:16:04 | 83% | Unplugged |

See [battery plot](battery.png). The charging interval replenished the phone during this recording, unlike the earlier unsupported run's rapid decline. The change to unplugged at 15:14:05 is observed; its cause is not recorded. No battery behavior after phone shutdown is available.

## Reset and reproducibility

Roomberry was not running when the active Pi map was backed up and cleared. Two blocked cells, the trail and coverage were reset; grid dimensions and tag survey were preserved. Backup on Pi: `roomberry/map-state-reset-20261030-01.json.before-clear-1793399186659347493`, relative to the deployed Roomberry directory. The active filename remains unchanged. The original fetched map and mission log are preserved alongside this report as `map-state.json` and `mission.log`.

Run `.venv/bin/python output/run-20261030-151054/analyze.py` to regenerate the CSV, plots and summary. It reads the exact timestamped NavLink and sensor files and the saved mission/map snapshots. The measured mount is also documented in `navlink/navlink.md`; it does not enable live phone navigation or change validity flags.
