<!-- @(#)README.md 2.3.analysis.5 2026/10/30 17:05:00 -->
# October 30, 16:53 reconciliation

This recording explains two separate events: a Pi reboot before recording began, and a later mission stop caused by inherited map obstacles. It also contains a clear phone-pose instability, so this run cannot establish the phone as reliable position ground truth.

## Reboot and mission timeline

The first NavLink receipt is at approximately 16:53:05 with Pi monotonic time 160.259 seconds, placing boot at about **16:50:25**. `rb.log` independently shows camera startup at uptime approximately 2 minutes 45 seconds. The Roomberry startup/reset sequence begins at 16:52:49. This supports the user's reported Pi reboot, but the supplied files do not establish its electrical cause or retain the preceding unrecorded motion.

The binary file then contains 2155 complete records through 16:56:41, with one phone session and continuous packet sequence. There is no reboot within this recorded interval. Discovery ends at 16:55:37.990, while recording and sensor polling continue afterward.

- 16:53:51: initial tag-1 fix accepted.
- 16:54:08: post-retreat tag-1 fix accepted.
- 16:54:32 and 16:54:41: tag-2 views miss; stationary yaw retries follow.
- 16:54:50: third view accepts tag 2.
- 16:54:59: intentional tag-2 bumper contact; reverse release follows. A simultaneous forward-command rejection is the controller refusing motion during the safety stop, not silent execution.
- 16:55:02: tag 16 at (3100, 1450) mm becomes the active parking goal.
- 16:55:10–16:55:23: stationary look-back scan accepts tag 1 and resumes transit. There is no “Repositioning for rejected tag” diversion in this run.
- **16:55:37.990: footprint-blocked stop ends discovery in idle.**
- 16:56:35: wheel-drop event occurs later, after the robot has already stopped.

## What blocked it

The saved occupancy is identical to the previous run's occupancy: four blocked cells, **(9, 0), (17, 0), (18, 0), (17, 3)**. The loaded trail is retained too: the new saved session starts after the previous 114 points. These are inherited learned obstacles, not four new contacts in this recording. The intentional tag-2 contact was logged near (−9, 345) mm, outside the map, and did not add a stored obstacle cell.

The closest obstacle to the stopped estimated center is cell (17, 3), the square x=1479–1566 and y=261–348 mm. The estimated robot center is (1283.469, 454.312) mm, about 222.6 mm from the square. Projecting its short forward motion toward tag 16 enters the guard's 204.875 mm footprint/padding clearance. Replaying the pose with a 59 mm/s, one-second straight command is rejected by the saved map and accepted by an empty map. Thus the inherited obstacle is sufficient to explain this stop.

The mission initially follows the raw discovery goal until obstacle detouring is active; no unexpected contact starts that detour in this run. Consequently it stops at the guard rather than planning around these inherited cells. Since their positions came from earlier uncertain localization, their continued use needs a map reset or explicit revalidation before the next trial. This investigation preserves the map and does not clear it or deploy navigation changes.

## iPhone correlation and important anomaly

[trajectory.png](trajectory.png) and [pose-comparison.csv](pose-comparison.csv) use the measured camera lever arm: 145 mm aft and 22 mm right. Mount yaw is inferred at +92.12° from 281 straight-motion windows. One fixed room transform is anchored at the accepted retreat fix at 16:54:08; no scale or later trajectory fitting is applied.

The phone becomes inconsistent with physical robot motion before it reports a tracking failure:

| Sample | First | Second |
| --- | --- | --- |
| Estimated local capture time | 16:54:19.573 | 16:54:19.673 |
| Camera X | 1372.20 mm | 854.66 mm |
| Camera Y | 985.68 mm | 1090.42 mm |
| Tracking | Normal | Normal |
| Flags | 111 | 111 |
| Feature count | 4 | 4 |

Those samples are separated by **0.099995 seconds**, yet camera translation changes **528 mm**; removing the mount offset still leaves **526 mm** of inferred axle motion. The corresponding interpolated wheel travel is **5.1 mm**, with about −0.77° wheel yaw. Wheel commands are around 60/30 mm/s at that time. The phone's inferred speed is approximately **5.3 m/s**, inconsistent with the recorded robot motion. This is not a Pi dequeue-time artifact: the interval comes from phone capture uptime.

Instability is visible already around 16:54:16–16:54:19, before the largest step. The phone reports limited tracking for insufficient features around 16:54:19–16:54:20, then returns to normal. The offline anomaly CSV records valid-flagged steps above 30 mm per sub-200-ms interval for diagnostic review; that threshold is not a proposed universal navigation setting. The plot marks the trajectory amber from the first such anomaly because the original alignment is no longer trustworthy. Invalid poses are omitted, and lines do not bridge the missing interval.

| Event | Robot/phone separation | Robot minus phone heading |
| --- | ---: | ---: |
| 16:54:25, tag-2 scan request after the glitch | 525 mm | +0.9° |
| 16:54:50, accepted tag-2 correction | 680 mm | +3.5° |
| 16:55:14, stationary tag-1 search | 787 mm | −0.8° |
| 16:55:37, stop | 651 mm | +7.1° |

At the stop, the aligned phone estimate is approximately (1352, 1102) mm versus the robot's (1283, 454) mm. These are **post-glitch disagreements**, not measurements proving 65–79 cm of Roomba error. The stop comparison pairs the robot's unchanged stationary pose printed about five seconds later with the phone at the stop time.

2035 of 2155 packets have pose validity set; 120 are invalid for insufficient features. There are two limited intervals: about one second during transit and about eleven seconds after the stop. Median feature count for usable packets is 3. The example demonstrates that normal tracking and validity bits alone are insufficient: a live navigation consumer also needs motion plausibility checks, discontinuity handling, and a fresh trusted alignment before reuse after an anomaly.

Pi receipt queuing still adds up to about 5.53 seconds. Offline matching uses capture uptime plus the minimum receipt-minus-send offset, retaining unknown minimum transport latency and clock uncertainty. This timing estimate is not a live clock synchronization implementation.

## Battery and artifacts

The phone reports **79%→73%**, unplugged in every packet, over approximately 3 minutes 35 seconds. This recording does not show charging support from the power bank.

`mission.log` and `map-state.json` preserve this run's fetched inputs. The original timestamped NavLink and sensor files remain in `roomberry/logs/`. Run `.venv/bin/python output/run-20261030-165305/analyze.py` to regenerate the CSV, summary and plot. [phone-motion-anomalies.csv](phone-motion-anomalies.csv) records the abnormal steps. No runtime code, power configuration or map was changed by this investigation.
