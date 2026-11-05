<!-- @(#)README.md 2.3.steering.2 2026/10/30 15:00:00 -->
# Short-run investigation, October 30 at 14:47

This run loaded the fresh map. The stop was preceded by a new physical right-bumper event, not an inherited obstacle.

| Local time | Evidence |
| --- | --- |
| 14:47:34 | Last accepted tag fix: tag 1, approximately (1096, 232) mm, heading −106.1°. |
| 14:47:48 | Initial scan accepts no tags; still uses the earlier idle dock fix. |
| 14:48:05 | Retreat scan accepts no tags. Position is then dead-reckoned at (1360, 697) mm; last fix is 30.8 seconds old. |
| 14:48:21 | Estimated arrival near (505, 518) mm; aligns and scans toward tag 2. |
| 14:48:28 | Tag 2 is not detected/accepted. Last fix is 53.6 seconds old. Retry selects a 100 mm lateral waypoint, causing another substantial heading change. |
| 14:48:31 | Right bumper triggers braking; obstacle is mapped near (483, 298) mm. |
| 14:48:38 | Reverse/turn/forward detour completes; returns toward retry waypoint (500, 435) mm. |
| 14:48:42 onward | Footprint check repeatedly refuses forward travel. |
| 14:50:04 | Wheel drop sends OI STOP and changes mission to idle. |

The saved map contains one blocked cell, (5, 3), spanning x=435–522 and y=261–348 mm. The resumed goal at (500, 435) mm is only 87 mm above that blocked square, which cannot accommodate the 174 mm robot radius. At the later reported pose (651, 467) mm, the blocked square is approximately 176 mm from the robot center—inside the footprint guard's padded radius. Resetting this newly recorded obstacle is not a navigation fix.

## Archived camera evidence

- [Retreat capture at 14:47:57](20261030-144757-496970.jpg): dock/scale/door area; the expected tag is not visible.
- [Tag-2 approach capture at 14:48:22](20261030-144822-636480.jpg): door area; no visible tag 2.

These photos were retrieved from the Pi's vision archive. They support an aiming/localization problem rather than a detector simply failing to decode a clearly visible tag. The files alone do not establish the correct camera mount yaw or whether the surveyed tag/dock orientation matches the physical arrangement. No speculative angle correction was applied.

## Local corrections

- A post-retreat scan must accept a surveyed tag before tag-2 transit. Two additional stationary captures are allowed, then discovery ends in idle with a specific reason.
- Missing tag 2 now requests stationary yaw views at +0.5 and −0.5 radians. The old lateral waypoint moves were removed. The retry yaw offset had previously been stored but not used by the alignment calculation; it is now applied.
- Three unsuccessful tag-2 views end discovery rather than permitting a blind contact approach. A successful retry restores the surveyed normal before intentional contact.
- After an unexpected obstacle, tag-2 transit now uses mapped routing, as the other transit stages do. An unreachable approach point produces an explicit idle stop.
- A footprint-blocked discovery waypoint ends discovery explicitly instead of retrying the same blocked move every 200 ms.

Regression tests cover the missed-scan sequence, yaw direction and completion, successful retry, refusal of blind transit/contact, routing after a tag-2 detour, and the actual recorded obstacle/pose geometry. All 108 mission/mapper tests pass. The broader Roomberry suite passes 215 of 216 tests; the same existing camera annotation/font-rendering test fails independently of these changes.

Changes are local and have not been deployed to the Pi. This follow-up changes runtime behavior in `roomberry_mission.py`; it does not change the map or tag survey. The remaining physical calibration question is why the camera is not viewing the expected tags at these stops. The initial tag-based dock heading is approximately 16° from the configured dock heading; camera mount yaw, tag orientation and actual parking alignment need verification before treating that difference as a calibration correction.
