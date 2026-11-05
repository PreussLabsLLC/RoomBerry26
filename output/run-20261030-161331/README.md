<!-- @(#)README.md 2.3.analysis.4 2026/10/30 16:30:00 -->
# Run 30c: October 30, 16:13

The robot really returned toward the dock; this is visible in both the measured-offset-corrected iPhone trace and the wheel/tag trajectory. The key unnecessary maneuver was a route diversion triggered by a rejected detection, not a request to return home.

## Why it kept changing direction

| Local time | Mission decision |
| --- | --- |
| 16:14:16–16:14:32 | Dock departure: reverse, stop, scan and accept tag 1. |
| 16:14:54–16:15:13 | Two missed tag-2 scans cause stationary +0.5/−0.5 rad views; the third accepts tag 2. |
| 16:15:22–16:15:25 | Intentional tag-2 bumper contact followed by reverse release. Tag 16 parking point (3100, 1450) mm becomes the active goal. |
| 16:15:33–16:15:47 | Stop and turn back toward tag 1 for a localization scan; accept its fix and resume the tag-16 route. |
| 16:16:06 | Right-bumper contact during transit: reverse, turn and detour. |
| 16:16:21 | Another right-bumper contact during transit: another reverse/turn detour. |
| 16:16:30–16:16:43 | Stop and look back toward tag 1 again; scan accepts tag 1. |
| **16:16:43.903** | **Coordinator diverts from tag 16 to tag 2**, logging “Repositioning for rejected tag 2 using its surveyed face.” |
| 16:16:49 | Left-bumper contact while heading back toward tag 2: another detour. |
| 16:17:04–16:17:13 | Tag-2-directed scan during the diverted leg accepts tag 2, but the visit goal remains the temporary tag-2 parking point. |
| 16:17:24 | Right-bumper contact during the diverted leg: another detour. |
| 16:17:33–16:17:56 | Another stationary tag-1 search accepts a correction near the dock. |
| 16:17:59.823 | Footprint guard refuses travel and discovery ends in idle. |

At the highlighted diversion, tag 1 was accepted, while tag 2 was rejected with reprojection error **430.4** (configured acceptance limit 10). Tag 2 nevertheless had hamming=0 and margin≈29, which passed the coordinator's incomplete repositioning filter. The coordinator saved the tag-16 visit and temporarily replaced it with a visit to tag 2 at (500, 535) mm. It encountered repeated contacts before completing that detour and restoring the original visit. Thus tag 16 was attempted, interrupted and never reached; tag 15 stayed queued.

The back-ups following later bumper events were commanded recovery maneuvers, rather than spontaneous drive reversals. Four later-transit contacts are logged, separate from intentional contact at tag 2. From 16:15:25 to 16:17:59 the wheel log records about 3.49 m forward and 0.70 m reverse wheel-derived travel. These totals include small odometry motions/noise and are not independently surveyed physical distances. Stationary camera aiming also caused substantial left/right pivots and repeated departures from the transit heading.

Near the end there is a serial write timeout at 16:17:58.046, with the wheel ramp braking immediately. Commands were accepted afterward. The explicit mission-ending event is the footprint-blocked stop, followed about 0.15 s later by another bumper reading and a wheel drop at 16:18:09. The timeout does not explain the earlier route reversal.

## Local fix

`roomberry_mission.py` now preserves the active destination if a scan accepts any surveyed tag. A rejected candidate can trigger translational repositioning only when its reported rejection is a pose jump/relocation-confirmation issue, rather than bad image geometry. After the remaining-tag visit sequence begins, completed dock tags 1 and 2 cannot hijack that route through this fallback. Existing stationary localization searches and bumper recovery remain active.

Regression tests reproduce the accepted-tag-1 plus rejected-tag-2 frame, bad geometry without an accepted fix, a completed dock tag requiring relocation confirmation, and bad geometry on an unvisited tag. A fresh known fix also prevents an unrelated unvisited pose-jump candidate from replacing the current destination. The existing useful unvisited-tag recovery/resumption test remains covered. All 105 mission tests pass. The runtime fix is local and has not been deployed.

## Phone versus Roomba

See [trajectory.png](trajectory.png), [pose-comparison.csv](pose-comparison.csv), and preserved [map30c.png](map30c.png). Blue is the phone-derived robot center; red connects sparse logged robot poses including tag corrections. Both stay near the dock rather than reaching the tag-16 parking point.

The analysis removes the measured camera offset: 145 mm aft and 22 mm right. Camera-heading-to-robot-forward yaw is inferred at about +91.08° from 551 straight-motion windows. One fixed room transform is anchored to the accepted retreat tag-1 fix at 16:14:32. No scale or later trajectory fitting is performed. Capture uptime is aligned with an offline minimum receipt-minus-send offset; receipt queuing adds up to about 6.05 seconds, so raw receipt times are unsuitable for direct motion matching.

| Event | Position disagreement | Robot minus phone heading |
| --- | ---: | ---: |
| 16:14:54, first tag-2 scan | 39 mm | −6.2° |
| 16:15:13, accepted tag-2 correction | 237 mm | +4.9° |
| 16:15:37, tag-1 scan before further transit | 340 mm | −19.4° |
| 16:16:06, first later transit contact | 240 mm | +7.2° |
| 16:16:21, second later transit contact | 255 mm | −1.5° |
| 16:16:49, contact during the diverted return | 102 mm | +3.4° |
| 16:17:24, further contact | 178 mm | +19.1° |
| 16:17:59, final stop estimate | 170 mm | +2.3° |

The final robot center is reconstructed at approximately (1030, 245) mm, versus corrected phone center (887, 336) mm. There is no full robot pose print after the last accepted tag fix. The reconstruction uses the accepted tag-1 range, bearing and heading log at 16:17:56, then integrates the recorded wheel deltas to the stop. Range/bearing rounding and sample/mission timing introduce several millimetres of additional uncertainty; the result is consistent with the saved trail's nearby final point. It is not an exact logged pose.

All 2928 packets report normal tracking, valid pose/velocity/IMU/statistics, and one session. Median feature count remains 3, so this is not surveyed phone ground truth. The stronger conclusion is that both motion sources corroborate the physical loop. Position discrepancies and heading errors still influence mapped contact coordinates and routing, but cannot alone explain the explicit destination change.

## Battery and reproduction

The phone reports charging throughout 16:13:31–16:18:24 and rises **65%→75%**. No charging-state interruption is recorded in this run.

Run `.venv/bin/python output/run-20261030-161331/analyze.py` to regenerate the plot and CSV. It uses the timestamped NavLink/sensor files and preserved mission/map/image snapshots in this folder. The map was not cleared as part of this investigation.
