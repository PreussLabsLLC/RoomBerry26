<!-- @(#)README.md 2.3.analysis.3 2026/10/30 16:10:00 -->
# Run 30b: October 30, 15:51

The original [map30b.png](map30b.png), mission log and saved map state are preserved in this folder. The image shows tag 15 facing +Y and tag 16 facing −X, matching the configuration used for the run. The user's latest correction is the reverse: **tag 16 faces +Y like tag 1; tag 15 faces −X**. Local configuration, map-direction tests and parking tests now agree with that correction. Parking points are (3100, 1450) mm for tag 16, viewing −Y, and (7230, 1520) mm for tag 15, viewing +X. Neither tag's surveyed position changed.

The blue robot marker in the saved PNG is approximately (1.27, 0.33) m. This differs from the final logged stopped pose, approximately (1.75, 0.20) m, so the screenshot depicts an earlier point than the final stop. The full-run correlation below uses the logs.

## Mission outcome and boundary-routing fix

Tag 1 was accepted after retreat at 15:52:28. The third stationary tag-2 view succeeded at 15:53:10; intentional tag contact and release completed at 15:53:22. The mission then headed toward the old tag-16 parking goal, (2600, 950) mm. A further tag-1 correction was accepted at 15:53:44. Tag 16 was never accepted, and tag 15 was not visited.

At 15:54:01 a real right-bumper event was mapped near (1497, 46) mm. After the detour, the grid planner selected (1783.5, 130.5) mm at 15:54:19. That waypoint's Y is less than the robot's 174 mm physical radius. The planner had considered free edge cells traversable without accounting for the body extending outside the room. The footprint guard rejected travel, and discovery ended in idle at 15:54:27.783. The later wheel-drop event was not the original cause of this stop.

The local mapper fix excludes route-cell centers inside the same boundary inset used by the motion guard: radius + sampling allowance + extra padding (204.875 mm for the present grid). If the initial pose is inside only the extra boundary padding, a command may preserve or increase clearance, but it cannot move closer to the edge or violate the body/sampling footprint. This mirrors the existing obstacle-padding escape rule. Tests cover an impossible edge waypoint, a reachable route around the recorded obstacle, escape from the logged stopped pose, and rejection of motion toward or physically across the boundary.

All 138 focused mapper/mission/server/rendering tests pass. The broader suite passes 229/230, with the same existing camera annotation/font-rendering failure. The boundary fix in `roomberry_mapper.py` and corrected `autonomy.json` remain local and need syncing to the Pi.

## iPhone correlation

[Trajectory plot](trajectory.png) and [pose-comparison.csv](pose-comparison.csv) compare the logged robot positions with the phone-derived axle center. The measured lens offset is removed: 145 mm aft and 22 mm right, or (−145, −22) mm in robot-forward/left coordinates. Mount yaw is inferred from 366 straight-motion windows as approximately +92.52° from the packet's camera +Y heading to robot forward. One fixed room rotation and translation is anchored to the accepted retreat tag fix at 15:52:28; scale and later trajectory shape are not fitted.

| Event | Robot vs phone center separation | Robot minus phone heading |
| --- | ---: | ---: |
| 15:52:52, first tag-2 scan | 211 mm | −9.3° |
| 15:53:10, accepted tag-2 correction | 329 mm | +1.4° |
| 15:53:34, stationary tag-1 search | 394 mm | −11.6° |
| 15:54:01, right-bumper contact | 287 mm | +0.5° |
| 15:54:27, discovery stop | 356 mm | −11.2° |

At the stop the robot estimate is (1750.823, 202.858) mm versus corrected phone estimate (1804.428, 555.272) mm. The disagreement is mainly in Y, about 352 mm. The phone trace therefore places the robot considerably farther inside the room than wheel/tag localization does. This supports concern about mapped obstacle coordinates and room-edge decisions; it does not prove that either entire trajectory is correct. Hardware bumper events establish physical contact, while their world coordinates depend on localization.

All 2551 phone packets report normal tracking and usable pose/velocity/IMU/statistics. There are no tracking-state losses in this recording. Median feature count is still only 3 and is 1 near the stop, so normal status alone does not establish positional accuracy. Clock alignment uses capture uptime plus the minimum receipt-minus-send offset, retaining unknown minimum transport latency and possible clock drift. Maximum excess application-receipt delay is 5.54 seconds. The stopped robot pose printed about three seconds later is paired with the phone at the stop, since the robot remained stationary. Red plot lines connect sparse logged poses and tag corrections; they are not every motor sample.

## Battery

Recording covers 15:51:26–15:55:41. Battery begins at 74% and charging, rises to 75% at approximately 15:51:38, then reports unplugged from approximately 15:52:38 onward. It subsequently falls to 68% by the final packet. The loss of reported charging is consistent with the user's power-bank shutdown observation, but the log cannot distinguish bank shutdown from disconnection or another charging interruption.

## Map reset

Roomberry was confirmed stopped. The Pi's active map was backed up as `roomberry/map-state-reset-20261030-01.json.before-clear-1793401612183909698`, relative to the deployed Roomberry directory. Two blocked cells, coverage, trail and the trail-session marker were cleared. The active filename, room geometry and surveyed positions were preserved. This reset is already applied on the Pi; the Python/configuration corrections described above are not deployed.

Run `.venv/bin/python output/run-20261030-155126/analyze.py` to regenerate the correlation from the exact timestamped NavLink/sensor recordings and preserved mission/map snapshots. `summary.json` records battery changes and analysis metadata.
