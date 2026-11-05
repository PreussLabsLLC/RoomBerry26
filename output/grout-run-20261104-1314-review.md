# Grout run, November 4, 13:14–13:19 — 30 mm/s slowdown trial

Analysis only. Sources: roomberry/logs/roomberry.log, sensors/roomberry-sensors-20261104-131405.csv and navlink/roomberry-navlink-20261104-131405-0000.bin under roomberry/logs.

Outbound ran from 13:14:16.577 to threshold event 13:15:39.304 without a mission stop. Five slow-mode episodes totaled 26.692 seconds by controller sample transitions, about 32% of the 82.727-second outbound. The first two episodes lasted 6.051 and 15.926 seconds. Impact-time wheel travel was 4623.430 mm, settled 4632.627 mm. The threshold phone peak was 0.384 g. Settled distance was 3.365 mm farther than the previous 12:53 run, using the same wheel scale. Average magnitude of executed wheel-command steering imbalance was 8.85%, with 6.20% of moving time near the 25% limit. These are command statistics, not observed turning accuracy.

Automatic return began 13:15:40.372 at 30 mm/s in line-loss mode. Reacquisition was intermittent, including large changes of estimated offset sign (for example +13.6 to −52.7 to +18.1 mm within several seconds). These could reflect genuine motion, user nudges, or inconsistent stripe selection; no saved phone images establish which. Thirty millimetres per second did not yield robust tracking.

At the 2000 mm checkpoint, processing completed at 13:17:00.643. The tag solver returned a tag-15 pose at heading −28.41 degrees, position (6129.0,1756.2) mm. The mission rejected it because its heading exceeded the ±0.35 rad (±20.05 degree) straight-approach envelope. Wheel heading was about +1.75 degrees at that scan, a roughly 30-degree disagreement. Detection and scan processing succeeded; no stale-sensor/phone scan abort occurred. The pose was not applied. At 13:17:05.473, the return stopped on the 30-second lost-line allowance, with settled signed distance about −1627 mm. Return travel to this first stop was about 3.006 m.

User-requested resumptions:

- 13:17:48.607: return button. Left cliff sensor asserted at 13:17:56.561 (signal 50), followed by mission abort at 13:17:57.467. Logs cannot determine the physical cause of the cliff reading.
- 13:18:16.014: return button. The retained 1500 mm checkpoint scan completed at 13:18:21.248. Tag solver heading −20.39 degrees, position (6452.4,1123.3) mm, again exceeded the 20.05-degree envelope, by about 0.33 degree. This pose also was not applied.
- 13:18:25.346: phone impact count advanced 2→3, peak 0.466 g. Return aborted at 13:18:25.354. Settled distance was about −1151.7 mm.
- Subsequently, with both applied wheel commands zero, signed wheel distance advanced about 435.7 mm and wheel heading changed about 11.8 degrees. Manual movement is consistent with the user's reported interventions. At 13:18:41.555 and 13:18:55.798, return requests were rejected for wheel-odometry discontinuity: the saved trace had not integrated this idle movement, and its 150 mm per-update limit was exceeded. No new driven return was begun by these requests.
- At 13:19:10, the left wheel-drop sensor asserted and the independent OI-stop latch engaged. Further phone impacts appeared during subsequent handling; these occurred after the failed return sequence.

During stable slow forward commands requesting a left turn, aggregate encoder yaw still moved right (about 0.72 degrees/s over those samples). This run includes manual interventions, so that result cannot isolate low-speed drivetrain response from external movement. It does not establish that the 30 mm/s trial fixed the earlier wheel-response mismatch.

Interpretation: tag processing isolation and checkpoint retention now work, but neither measured return pose was accepted. Recovery still relies on uncorrected wheel pose when line observations are absent. External nudges can move the chassis differently from wheel odometry, making that estimate unreliable. Detector consistency, measured low-speed response, and a stopped relocalization path after manual movement need investigation. Simply widening the heading gate would not resolve the large first-scan disagreement.
