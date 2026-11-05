# Run 2026-10-30 21:12:09

Analysis only; robot software unchanged. Discovery skipped the tag 2 visit as requested. Total travel in the available Roomba sensor CSV is 1356.5 cm; the last row is at 21:19:17.285. The last explicit robot pose is at 21:19:05.173, at 1335.3 cm travel. Do not substitute that pose for the subsequent moving robot's final position.

Comparison uses a fixed iPhone-to-room transform at the retreat tag fix (21:13:03), deployed mounting yaw 93.6 degrees and measured camera lever arm. Frame times are delay-corrected. Robot poses include AprilTag and phone corrections, rather than raw encoder integration alone. Neither trace is surveyed ground truth. Percentage means position separation divided by cumulative Roomba travel since recording began.

| Point | Roomba travel (cm) | Disagreement (cm) | % |
|---|---:|---:|---:|
| First bump-and-go scan, 21:13:45 | 293.3 | 31.9 | 10.9% |
| Tag 16 visit attempt, 21:14:52 | 496.3 | 4.3 | 0.9% |
| Accepted tag 16 fix, 21:15:17 | 612.6 | 54.5 | 8.9% |
| 21:16:02 | 879.4 | 70.6 | 8.0% |
| Before late tag 15 fix, 21:17:49 | 988.2 | 49.2 | 5.0% |
| Accepted tag 15 fix, 21:17:52 | 988.2 | 374.2 | 37.9% |
| Last explicit pose, 21:19:05 | 1335.3 | 325.3 | 24.4% |

## Main discrepancies

Initial agreement improved substantially: around 5 m travel, the fixed-frame disagreement was about 4 cm. At 21:15:17 a tag 16 fix moved the estimated robot from approximately (2841,996) mm to (2647,1505) mm, about 55 cm. At 21:17:52 a confirmed tag 15 fix moved it from approximately (4068,308) mm to (6063,3151) mm: about 3.47 m. The phone-to-room correction anchor was reset after both updates. The late fix also rotated the robot heading about 53 degrees. It was based on a tag detected at approximately 2.5 m range, margin about 92 and reprojection error about 5, passing current filters and repeated-scan confirmation. This does not independently prove its recovered room pose. Large room-pose changes while stationary dominate the late disagreement and alter subsequent navigation.

The live correction residual near 21:19:20 was only 6.02 cm, but it uses the latest tag anchor, and does not establish global agreement. Summed logged correction step magnitudes reached 55.65 cm, not a measured accuracy improvement.

Phone recording: 5597 packets, 5553 valid poses (99.21%), no sequence discontinuities, one session and one alignment. Median feature count 8; maximum excess receipt delay 1.763 s. A 0.3 s tracking limitation occurred at 21:13:18 during discovery; later tracking limitations were after the wheel-drop event. The largest valid corrected-axle step before the last explicit robot pose was about 14 cm in 0.1 s at 21:13:27. Thus valid phone tracking is not equivalent to surveyed position accuracy. Phone battery stayed 100%; state changed from full to unplugged at 21:19:59.

## Scan performance

25 full scans: mean 3.723 s, range 2.882–5.726 s. Mean tag detection 1.343 s, mean image saving 0.676 s. Twenty scans without overlapping sensor-poll failures averaged 3.655 s; five with failures averaged 3.995 s. Sixteen captures skipping detection averaged 0.448 s (0.326–0.749 s). The slowest full scan, ending 21:13:49, spent 2.226 s in the pause phase, 1.667 s detecting and 0.713 s saving; it had no overlapping poll failure. Scan duration is therefore not exclusively detector time or serial failure.

Ten sensor polls failed, all represented by serial write timeout traces in this log. Five full scans overlapped a failure. Polling otherwise recovered until the wheel-drop latch. Roomba voltage minimum in available samples was 15.919 V, maximum discharge 0.914 A, reported charge 100% to 90.8%, temperature 41–42 C. These do not include the later factory vacuum/turbo run.

## Why bump mode started

At 21:13:17 the mapped-footprint motion guard rejected the waypoint command. This automatically started bump-and-go. No new bumper contact was logged there; the first newly mapped bumper contact was at 21:14:28. Thus the initial trigger was the persisted map/estimated footprint, not a detected physical bump. The log does not identify the exact blocking cell, so it cannot establish that a physical object justified the rejection. Later restart at 21:17:53 followed the large tag 15 relocation and a no-route result.

## Was factory return-to-dock captured?

No Roomba sensor samples from that later trip are present. The CSV ends at 21:19:17.285, before the right-wheel-drop event at 21:19:23.603. At that event the controller sent OI STOP, latched the wheel-drop state, and changed the mission to idle. _poll_sensors returns immediately while this latch is set, so later factory movement/current/encoders are unavailable. The missing last few seconds before the event may also reflect buffered CSV output; the exact reason is not recorded. We cannot extract factory chair-leg maneuvers or vacuum/turbo current from this sensor file.

Phone recording continued until 21:21:29. It may provide a coarse subsequent path, subject to whether the phone remained mounted, tracking interruptions and the pre-existing room alignment error. It cannot supply the missing wheel/motor readings. For future factory runs, passive observation would need to continue separately from the motion-rearm latch.

## Reproduction

analyze.py generates the fixed-frame comparison, summary and trajectory. analyze-corrections.py also exports online correction residuals and tag anchors. scan-performance.py exports scan-timings.csv. diagnostics.py exports battery summaries and phone motion anomalies. Mission log and map state are copied into this folder; binary phone and sensor recordings remain under roomberry/logs.
