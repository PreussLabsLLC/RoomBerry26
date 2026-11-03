<!-- @(#)README.md 3.1 2026/10/31 14:20:00 -->
# Calibration run, 31 October 2026, 13:58–14:05 PDT

The robot approached the first 500 mm wheel target but did not complete it. No `reverse_1` checkpoint was recorded. The stop was the three-second encoder-progress watchdog, not a heading, obstacle, bumper, or tag rejection.

## Timeline

- 13:59:18–13:59:31: first attempt; no usable phone anchor before timeout; no movement.
- 14:00:24: second attempt starts. Starting tag captured at 14:00:26.029. Phone anchor acquired at 14:00:37.374; all three poses initialized to that tag pose.
- 14:00:37.610: reverse drive begins, initially 50 mm/s.
- 14:00:46.401: encoders reach −487.2 mm from the baseline. Final commands are approximately −9/−10 mm/s. Encoder progress then stops.
- 14:00:47.498: reverse-load monitor reports no encoder progress, with motor currents only about 1–2 mA. It is report-only and does not cause the stop. This suggests insufficient low-speed drive rather than a loaded collision; physical cause cannot be established from logs alone.
- 14:00:49.331: calibration aborts for no wheel progress for three seconds; idle. Target remains 12.8 mm away. No next reverse leg, return, or contact.
- 14:01:08.881: first post-stop tag capture, processed/localized at 14:01:10.778.
- 14:01:21–14:01:35: third attempt; phone-anchor timeout, no additional motion.

## Tracking comparison

| Candidate | Observation | Interpretation |
|---|---|---|
| Wheel encoders | 487.2 mm reverse path; final yaw −1.95°, transient yaw reaches −4.77° | Continuous record, but not ground truth for slip or wheel scale |
| Tag 15, first post-stop fix | 417.1 mm straight displacement; yaw change −3.87° | Independent camera position; wheel endpoint differs by 87.4 mm |
| Tag 15, median of 10 stationary fixes | 418.2 mm displacement; yaw change −2.15° | Wheel endpoint differs by 102.1 mm; static x span 8.1 mm, y span 38.1 mm, heading span 3.06° |
| GroundHog optical motion | Only two received motion packets during 11.957 s; seq 45 and 46, continuity 8 and 16. Baseline continuity was 0. Final packet contains −74.7 mm forward and −1.6 mm left within its latest segment | Cannot estimate complete travel. The 74.7 mm segment is not a total-distance measurement and cannot be compared directly with 487.2 mm |
| Phone gyro | Integrated gravity-projected rate gives −0.24° net yaw; 11.894 s coverage from 120 valid samples | Net change differs from wheels by about 1.71°. Useful independent rotational evidence, but not translation. It also supplies optical de-rotation, so optical/gyro agreement would not be independent |
| Compass | 12 packets; no navigation-valid bearings; reported accuracy 25.92–26.12° | Correctly excluded by the existing 20° quality limit; not usable to arbitrate this small turn |

The difference between wheel path length and tag straight displacement is about 69 mm (16.5% of tag displacement), but those are different quantities. The reconstructed wheel endpoint still disagrees with the tag endpoint by 87–102 mm, including a substantial lateral component. This is not proof of wheel slip: the configuration explicitly describes camera intrinsics and mount values as illustrative placeholders. Intrinsics are scaled correctly from the base resolution to 820×616 in code; this is not evidence of a missing resize adjustment. Camera calibration, mounting geometry, and wheel scale remain confounded. Starting equality is imposed by anchoring, not a successful accuracy check.

## Phone reliability and health

The two motion packets have consecutive sequence numbers despite a 6.74 s receipt gap. This indicates sparse emission, rather than intervening emitted packets lost over UDP. The tracker continues processing: accepted frame counters rise from 5018 to 5128 and rejected counters from 124 to 215 between these packets. Continuity increases eight times between the two observations; the baseline-to-first-packet change is another eight increments. The first packet reports reason 7 (texture/agreement rejection); the second is locally valid but belongs to a new segment.

The intended 100 ms motion timer runs on the same serial queue as camera processing (`FloorTracker.swift`). Timer starvation is a plausible implementation cause of sparse emissions; the logs do not prove scheduling behavior directly. Health packets continue at about 10 Hz, which argues against complete phone or network failure. Moving emission onto an independent queue must include a synchronized snapshot of tracker state.

Phone battery is 88%; app CPU 60.6–64.7%; app memory footprint 18.8–45.2 MB (decimal); thermal state nominal; bump count zero. Captured phone image dimensions are **480×640 pixels**. These are process-level resource figures, not total device CPU/memory. Pi AprilTag images are 820×616.

## Next work suggested by this run

1. Fix endpoint approach: maintain a demonstrated usable minimum drive speed and accept a small, explicit endpoint tolerance, while retaining the no-progress watchdog. Simply extending the timeout leaves the robot stalled.
2. Decouple GroundHog motion emission from camera processing, then investigate reason-7 tracking breaks. Keep discontinuities explicit; do not stitch lost motion into a false cumulative total.
3. Calibrate Pi camera intrinsics and confirm camera/phone mounting measurements before deciding whether the wheel/tag discrepancy is slip or scale error. Repeat the staged run once optical coverage is continuous.

No runtime code, deployment, or robot state was changed for this analysis.

## Reproduction

Run `.venv/bin/python output/calibration-20261031-1358/analyze.py` from the repository root. Inputs are the local `roomberry.log`, sensor CSV, and binary NavLink log from session 20261031-135830. Outputs are `summary.json` and `wheel_trajectory.csv`.

Phone source times use the minimum observed per-session receive-minus-send offset as an approximate alignment. Unknown one-way latency remains. Gyro integration rejects repeated timestamps and gaps ≥0.5 s; endpoint comparisons use stationary tag observations after motion. Wheel pose is independently integrated from the initial tag anchor and never reset to later tag fixes.
