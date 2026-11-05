<!-- @(#)README.md 3.1.cal.2 2026/10/31 13:00:00 -->
# Stationary calibration attempt, October 31, 2026

Sources: `roomberry/logs/roomberry.log`, `roomberry/logs/sensors/roomberry-sensors-20261031-125106.csv`, and `roomberry/logs/navlink/roomberry-navlink-20261031-125106-0000.bin` supplied after the run. Times below are the Pi log's local times.

| Time | Evidence |
| --- | --- |
| 12:51:48.239 | Clock press detected; calibration entered Safe mode. |
| 12:51:48.326–12:51:51.332 | Unnecessary `wake` command blocked the serial owner for 3002 ms. |
| 12:51:51.422 | Stationary scan requested for tag 15. |
| 12:51:53.093 | Calibration aborted because snapshot age was 0.582905694 s, exceeding the unconditional 0.5 s guard. No motion command had been issued. |
| 12:51:53.160 | Tag 15 was detected successfully: hamming 0, decision margin 108.1, pose error 0.3532, depth 172.3 mm. |
| 12:51:53.959 | Idle localization accepted tag 15 at (7445.35, 1208.35) mm, heading −0.223909 rad (−12.83°). |
| 12:55:22 / 12:56:04 | Web `op=calibrate` / `op=cal` were incorrectly forwarded to the serial driver, which rejected the unknown operations. |

The sensor CSV confirms requested left/right wheel speeds remained zero throughout. Integrated distance ranged only from 0 to 0.7 mm and angle from 0 to 0.11°, consistent with no commanded travel.

The NavLink log contains 1206 GroundHog type-2 snapshots, all with valid flags 7/state 2/reason 0, height 85 mm, one session and continuous segment 35. Accepted frame counts increased from 5074 to 15311. Reported last-frame processing times were 26.992–29.228 ms. Health packets report delivered image dimensions 480×640. The phone was supplying valid tracking; it was not the reason for the actual abort.

There is a separate alignment gate to address on retry. The accepted pose is about 284.7 mm before the surveyed tag plane and 28.4 mm laterally from it: both within the start limits. Its reported heading −12.83° is outside ±8.6°. It is a reported tag-based orientation, not independent proof of physical robot angle; alignment or camera/mount calibration should be checked before retry. The fix preserves this limit and reports numerical failures clearly.

Changes: remove the calibration wake delay; pause briefly on stale polls only while already stopped; retain completed scan results until fresh sensors return; leave moving-sensor freshness and hard hazards unchanged; route calibration HTTP aliases to the mission; expose read-only run status. No logs/map data were modified, no run was triggered, and no Pi process was restarted by this analysis.
