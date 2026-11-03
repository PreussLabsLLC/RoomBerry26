<!-- @(#)README.md 3.1 2026/10/31 15:10:00 -->
# Latest calibration: straighter wheel path, less continuous optical tracking

Reviewed the refreshed application log and sensor/NavLink session 20261031-144728, covering the 14:48–14:50 PDT attempts. All four reverse milestones completed on the second attempt. The full out-and-back/contact sequence did not complete: the return stopped after about 471 mm because the phone reported the carpet-to-hard-floor transition identified by the user.

## Timeline and hiccups

- 14:48:06.132: first anchor, heading −6.41°. Reverse checkpoints at 499 and 996 mm. At 14:48:32.974, sensor polling failed with a serial write timeout while reading dedicated buttons; calibration aborted at 14:48:33.126 because Roomba sensors were not ready. The log also reports a failed attempt to brake with stale sensor data and additional serial write timeouts. This was a communications fault, not a distance or drift limit. Later polls recovered. The logs do not establish that HTTP load caused the serial fault.
- 14:48:48.587: second anchor, heading −16.25°, from the new location after the first attempt. This is a new baseline, not continuation of the first baseline.
- 14:49:01.663 / 14:49:14.766 / 14:49:27.741 / 14:49:40.721: reverse 1–4 recorded.
- 14:49:48.432: impact abort during return. The stop command completed at 14:49:48.444. No return checkpoint, verified approach, or final physical bumper contact was recorded.
- 14:50:03.673: another calibration start rejected because the remaining pose was too far and too lateral to tag 15 (estimated gap 2223 mm, lateral 705 mm). That is consistent with not having returned to the starting position.

Stationary scans repeatedly caused sensor-age warnings around 0.92–1.08 s. The stopped-wait logic recovered in about 0.20–0.23 s and preserved the scans. Phone sender cadence remained regular; Pi receipt gaps reached 1.09 s during the outbound sequence. These delays differ from the serial write-timeout fault.

## Did the starting angle merely make it look better?

The initial angle changed, but cross-track error relative to the initial heading also improved in wheel odometry. This calculation removes the initial orientation from the comparison.

| Second-attempt checkpoint | Wheel reverse distance | Wheel cross-track from initial reverse line | Wheel heading change from start |
|---|---:|---:|---:|
| 1 | 496.4 mm | 18.2 mm left | −4.66° |
| 2 | 995.8 mm | 44.1 mm left | −2.60° |
| 3 | 1500.2 mm | 55.0 mm left | −0.54° |
| 4 | 1992.8 mm | 70.7 mm left | −5.96° |

The previous successful three-leg attempt started at −14.35°, only 1.90° different from this second attempt. At 1.5 m it had 234.5 mm wheel cross-track and −11.49° wheel heading change. This attempt had 55.0 mm and −0.54° at the same distance: approximately 77% less cross-track. Thus wheel odometry indicates a straighter run even after accounting for initial alignment. Surface, wheel loading, route and traction also changed, so this is not proof of an improved controller or a repeatable mechanical change. No steering gains were changed between these runs.

The first attempt began closer to world +X (−6.41°). The second baseline was set after its abort, so the displayed history combines two experiments. Its world +Y change at checkpoint 4 was 625.1 mm, but only 70.7 mm was cross-track relative to its original reverse axis; most world +Y displacement comes from its angled starting direction.

## GroundHog: reporting remains good, tracking continuity worsened

The previous good run maintained a single continuity segment with 1185 accepted and zero rejected frames. This run did not:

- Attempt 1: continuity 52→82, 675 accepted / 132 rejected frame-count increase; 84.4% of received motion packets locally valid. Reported rejection reasons included texture/agreement and stale frames.
- Attempt 2 outbound: continuity 82→91, 1522 accepted / 14 rejected frame-count increase. 518/521 packets were locally valid (99.4%), but even brief lost intervals break the full cumulative path. The calibration correctly marks phone position unavailable from checkpoint 1 onward.
- Attempt 2 return: continuity stayed 91, 218 accepted / zero rejected frames. The phone measured approximately 435.7 mm of path versus approximately 471.1 mm wheels over the stationary-checkpoint-to-abort bracket (about 7.5% lower). Endpoint timestamp alignment is approximate; this is a local continuous interval, not recovery of outbound motion.

Maximum outbound phone emission gap was 102.2 ms, so the independent 10 Hz reporting change continues to work. Sparse invalid reports can miss additional tracking breaks between emissions; continuity counters reveal those breaks. Segments must not be stitched together as complete motion. The starting angle alone cannot explain the optical failures from these logs; floor texture, illumination, vibration and motion remain candidates.

Approximate integration of the gravity-projected gyro from 10 Hz health samples gives −1.28° net yaw over 52.10 s of the 52.13 s outbound bracket, compared with −5.96° encoder yaw. This differs more than in the previous run and warrants further comparison. It is a downsampled diagnostic with approximate phone/Pi clock alignment, not the exact 100 Hz yaw integral used by the phone. Do not infer a precise wheel-slip angle from the difference. The compass supplied no usable bearings during this attempt; reported accuracy was roughly 26–55°.

## Distant scans

Tag identity remained strong: margin roughly 110–127 and hamming 0 on the second attempt. Pose quality did not remain reliable:

- Checkpoint 1: accepted pose at reported 1.394 m camera range, but already 336.5 mm from independent wheel pose.
- Checkpoint 2: reported 1.757 m range; pose rejected for 1535 mm / 0.78 rad jump.
- Checkpoint 3: reported 2.291 m range; rejected for 589 mm / 0.16 rad jump.
- Checkpoint 4: implausibly shortened reported range 1.589 m; rejected for reprojection error 27.9.

Identification confidence and low single-image reprojection error do not establish correct room pose. These distances are the detector's estimates, not surveyed ranges. Existing placeholder camera intrinsics/mount and small tag image size remain limitations; this run provides no basis to loosen the pose gates. Pi captures remain 820×616.

## Carpet-exit bump

The new event (count 14) first arrived at 14:49:48.250 with a 4345 mm/s² peak (0.443 g). By 14:49:48.303 its refined peak was 7285 mm/s² (0.743 g). Calibration observed the above-threshold event and stopped at 14:49:48.432, as configured by the 0.5 g policy. The user identifies this as leaving the runner; it is therefore a demonstrated floor-transition false positive for the stop policy, while remaining a useful recorded event. No threshold was changed during this review. Later bump counts 15 and 16 occurred after the run had stopped.

## Web requests and change

The refreshed log contains 92 status requests, 91 GroundHog requests, and 12 scan-index requests: **195 background JSON requests** from the former polling behavior, plus images and explicit commands. Automatic refresh has now been removed. Initial page load fetches four JSON snapshots; **Refresh all** fetches four on demand, and the existing scan **Refresh** fetches only its index. Filter changes and explicit control clicks retain their related user-requested fetches. Snapshot age labels remain static until refreshed and the page explicitly states this.

Validation: 26 web/server route tests pass. A real headless-browser check observed exactly four initial fetches, no further fetches during 20 seconds idle, four additional fetches after Refresh all, and one after scan Refresh. No robot commands were used in the browser check.

Reload existing browser tabs once after deployment to replace the old JavaScript polling loop. These static assets can be loaded without restarting Roomberry. No robot movement, runtime restart, steering or impact-threshold adjustment was performed for this review.

## Reproduction

Run `.venv/bin/python output/calibration-20261031-1447/analyze.py` from the repository root to generate `summary.json` and `checkpoints.json`. Inputs are the refreshed application log, sensor CSV and NavLink binary from session 20261031-144728. Comparing with `output/calibration-20261031-1421/` provides the previous three-leg baseline. Starting-pose equality is imposed by anchoring and is not an accuracy test.
