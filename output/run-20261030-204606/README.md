# Run 2026-10-30 20:46:06

Both tags were visited. Total Roomba-reported cumulative travel: 1512.6 cm. Comparison below fixes the iPhone room frame at the retreat tag fix and uses the deployed 93.6-degree mount yaw, measured camera lever arm and corrected frame times. Robot position includes AprilTag updates and phone aiding; it is not raw wheel odometry. Neither trace is surveyed ground truth.

| Point | Roomba travel (cm) | Position disagreement (cm) | % |
|---|---:|---:|---:|
| After tag 2 | 126.4 | 21.6 | 17.1% |
| 20:48:24 | 385.3 | 7.4 | 1.9% |
| Tag 1+2 fix | 563.8 | 41.7 | 7.4% |
| Tag 16 visit | 885.8 | 106.3 | 12.0% |
| First tag 15 fix | 1222.8 | 165.1 | 13.5% |
| Final tag 15 fix | 1349.8 | 162.1 | 12.0% |
| Before pickup | 1512.6 | 161.9 | 10.7% |

## Why the cabinet-crossing trace is unreliable

The iPhone lost normal tracking for approximately 0.3 seconds at 20:49:51 and 0.1 seconds at 20:51:46 during the mission. At 20:49:52–54 the corrected phone axle position moved 281 mm while Roomba center odometry changed 1.4 mm; wheels were turning in opposite directions. Several individual valid-pose packets stepped 99–144 mm in 100 ms, consistent with AR position adjustment rather than actual center travel. Thus the phone's later global trace cannot be treated as truth. Its fixed room trace even falls below the configured Y=0 boundary.

At 20:53:36–39, phone position moved less than 1 mm and Roomba center odometry did not change, but the accepted tag 15 fix relocated the map position by roughly 1.3 m. The mapper appends corrected positions to one continuous trail, so localization jumps are drawn as apparent travel. Other tag fixes also move the room estimate; the tag 16 visit correction was 269 mm. The map crossing cabinets is not evidence of physical traversal, nor can it be attributed exclusively to wheel slip. Repeated tag-consistent solves can still be inconsistent with the room frame or camera calibration.

The live phone-aid residual was only 4.37 cm near the end, but this uses the frame re-anchored to the latest tag 15 fix. It does not contradict the 1.62 m disagreement against the original anchor. Logged correction magnitudes accumulated to 71.94 cm; this is not a measured accuracy improvement.

## Why HOME stopped at the fridge

HOME indicated the discovery return stage, not arrival. Return began at 20:54:13, first via the tag 16 parking point (3100,1290) mm, then the dock retreat point (1060,760) mm. Right bumper contacts occurred at 20:54:30 and 20:54:54. A tag-view search started at 20:54:55 while the bumper remained held, preventing its turn. At 20:55:07 the localization viewpoint recovery timed out and set the mission to idle. The final estimated pose was (6216,1146) mm, far from the dock. Pickup occurred at 20:55:44.

The new regression fix preempts a targeted search blocked by contact during visit/return/dock approach, preserves the goal and enters contact retreat/bump-and-go. It retains mapped obstacles and hard safety checks. This is unit-tested, not yet physically validated.

## Battery, serial and iPhone health

Roomba voltage minimum was 15.752 V at 20:50:47, with roughly 0.7 A load. Initial on-dock voltage was 17.311 V; voltage at the final stationary stop was about 16.03 V. The final bumper-contact interval stayed within 15.864–16.031 V. Recorded charge fell from 100% to about 88%; reported temperature stayed 41 C. These readings show load sag, but no recorded voltage collapse explaining the final stop. Peak wheel currents were 0.781 A left and 0.750 A right; minimum voltage did not coincide with a logged sensor poll failure.

Eight sensor polls failed between 20:48:26 and 20:51:38; one short read returned 72/80 bytes, with write timeouts elsewhere. Polling recovered and later tag visits succeeded. No sensor-poll failure occurred during the final return leg.

Phone battery stayed at 100%, state 3 (full). There were 5953 recorded packets, 5908 valid poses (99.24%), one missing sequence number, one session and one alignment. Most invalid packets occurred after pickup; the two mission tracking gaps totaled about 0.4 seconds. Maximum excess receipt delay was 1.522 seconds. Validity does not exclude the AR jumps described above.

## Speed changes for next run

Normal discovery cruise: 60 -> 80 mm/s. Minimum pivot: 20 -> 30 mm/s. Steering is capped at 0.45 and ordinary transit bends keep the inner wheel at least 30 mm/s, addressing commands that previously crawled around 13–25 mm/s. Near-goal/proximity limits remain slower. Motion guards, ramping, watchdogs and live safety checks remain active. The mission suite passes 132 tests including the held-bumper return regression and bend-speed bounds.

Reproduction: analyze.py produces the fixed-reference trajectory and pose CSV; analyze-corrections.py extracts online residuals and tag anchors; diagnostics.py produces battery statistics and phone-motion anomaly CSV. Inputs mission.log/map-state.json are copied here; phone/sensor recordings remain in roomberry/logs.
