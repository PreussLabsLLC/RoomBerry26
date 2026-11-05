<!-- @(#)README.md 2.3.analysis.6 2026/10/30 17:25:00 -->
# October 30, 17:10 run: recovery and track offsets

The uploaded [map.png](map.png) and [trajectory comparison](trajectory.png) agree that travel remained near the dock side of the room. Tag 16's goal was correct at (3100, 1450) mm. The route was not diverted back to tag 2 in this run.

## Why it stopped and changed direction

The map began with a fresh trail (saved session-history boundary zero), following the preceding reset. This time the problem is not four inherited obstacles. Five blocked cells were learned during this run, after repeated physical bumper events: (17, 0), (20, 2), (16, 3), (18, 4), and (24, 4).

After completing the tag-2 contact/release sequence at 17:11:59, discovery selected tag 16. A stationary tag-1 look-back search refreshed localization at 17:12:20. Subsequent bumper-triggered detours occurred at approximately 17:12:36, 17:12:52, 17:13:21, 17:13:32, 17:13:45 and 17:13:50. A second stationary tag-1 search accepted a fix at 17:13:16. The map and wheel-derived locations of contacts remain uncertain because of localization errors, but the bumper readings themselves are real observations.

At 17:14:02 the mapper selected another step toward tag 16. At **17:14:05.806**, the motion-footprint check rejected it and the existing coordinator immediately ended discovery in idle. The wheel-drop event at 17:14:19 came later. No tag-16 visit finished, and tag 15 remained queued.

## Local behavior changes

Blocked waypoint travel now stops motion while retaining discovery, the current visit and its original goal. It invalidates the cached step and forces mapped replanning. A usable alternative route resumes automatically. If no usable command exists, the robot can make up to two bounded stationary tag-view searches; after that it stays paused in discovery and retries stationary scans/replanning every ten seconds. A fresh accepted fix can trigger an earlier retry. Reaching the preserved goal resumes the normal tag-alignment stage.

Search timeouts during blocked recovery no longer put the mission in idle. Automatic periodic scans cannot silently restart unlimited aimed searches after the two-search budget. Physical contact preempts a search and uses the normal bumper-recovery behavior. Manual takeover cancels recovery. Cliff, wheel-drop and stale-sensor handling continue to brake; hard hazards still end the active mission.

The grid planner previously inflated obstacle *centers* using body radius, while the motion guard checked the entire blocked square plus sampling and steering padding. The planner, motion guard and renderer now share whole-square clearance geometry. This removes another source of “planner says yes, motion guard says no” commands without weakening the actual footprint check.

All 138 focused mission/mapper/map-image tests pass, including actual rerouting, pause/retry without repeated turns, fresh-fix resumption, goal arrival, search timeout, bumper priority, manual takeover, hard-hazard abortion and planner/guard agreement. The broader suite was run after the runtime edits: 240/241 passed, retaining the same existing camera annotation/font-rendering failure; two additional regression tests subsequently passed in the focused run. Changes are local: sync `roomberry_mission.py`, `roomberry_mapper.py` and `roomberry_map_image.py` before testing them on the Pi. No map reset or Pi deployment was performed in this turn.

## iPhone versus Roomba

The comparison removes the measured camera lever arm (145 mm aft, 22 mm right). Mount yaw is estimated at about +93.82° from 540 straight-motion windows. One fixed room transform is anchored at the accepted retreat tag-1 fix at 17:11:07. No scale or later trajectory fitting is applied. Offline matching uses phone capture uptime plus the minimum receipt-minus-send offset; the Pi's maximum excess receipt/dequeue delay is about 5.54 seconds.

| Event | Position disagreement | Robot minus phone heading |
| --- | ---: | ---: |
| 17:11:29, first tag-2 scan | 119 mm | −4.8° |
| 17:11:47, accepted tag-2 fix | 238 mm | +1.3° |
| 17:12:11, tag-1 search | 330 mm | −18.4° |
| 17:12:36, later transit contact | 236 mm | +3.3° |
| 17:12:52, contact | 254 mm | −1.7° |
| 17:13:21, contact | 214 mm | +3.6° |
| 17:13:32, contact | 282 mm | +3.1° |
| 17:13:45, contact | 329 mm | −2.9° |
| 17:13:50, contact | 320 mm | −5.3° |
| 17:14:05, stop estimate | 410 mm | +3.6° |

At the stop, the reconstructed robot center is approximately (2059, 526) mm, while the phone-derived center is approximately (1650, 534) mm. The discrepancy is almost entirely in X, about 410 mm. The stop pose is reconstructed from the last accepted tag-1 range/bearing/heading record at 17:13:16 and subsequent wheel integration, since no full pose is printed at the stop. It is within the saved trail's point-spacing envelope; sample/mission timing, integration and rounded log values add uncertainty. Red plot lines connect sparse logged poses and corrections, not a complete motor replay.

2588 of 2600 packets have usable pose flags. One approximately 1.2-second insufficient-features interval occurs around 17:13:03–17:13:04; invalid points are omitted and the plot does not connect across the gap. Median feature count is 4. The largest consecutive usable axle displacement during the compared motion is about 15.4 mm per 0.1 seconds, versus 5.6 mm wheel travel at that sample. This is much smaller than the preceding run's 53 cm discontinuity and does not show that catastrophic failure pattern. AR accuracy and the inferred room alignment remain uncertain; the phone is not surveyed ground truth.

The user's possible camera covering is consistent with a feature-loss mechanism, but the recordings cannot identify the physical cause. Future iPhone-led navigation must handle table/chair occlusion as a state change: briefly bridge using bounded wheel odometry, pause if confidence cannot be maintained, retain the mission, and revalidate or re-anchor the phone before resuming. This is a future NavLink consumer requirement. NavLink remains observation-only; it did not directly cause this run's idle transition. The implemented recovery changes above apply to current Roomba/AprilTag navigation.

## Battery and reproduction

Phone charge is **89%→90%**, reported charging throughout 17:10:06–17:14:26. There is no recorded charging interruption in this run.

Run `.venv/bin/python output/run-20261030-171006/analyze.py` to regenerate the CSV, summary and trajectory from the timestamped sensor/NavLink files and preserved mission/map snapshots. [pose-comparison.csv](pose-comparison.csv) contains the sampled offsets.
