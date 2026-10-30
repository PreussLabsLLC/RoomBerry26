<!-- @(#)validation-plan.md 2.3.ios-plan.1 2026/10/29 -->
# Validation and rollout

## Prerequisites

Record iPhone model, iOS/Xcode versions, mount measurements, room/map revision, ceiling height/texture, lighting, Pi software revision, WLAN arrangement, and configured robot speed. These materially affect tracking. Keep `observe` mode until the measured checks pass. Bench tests use simulated or recorded poses; physical trials start with cleaning motors off and an operator able to stop the robot.

## Transform and protocol tests

- Known transforms: identity, arbitrary yaw, inverted camera mount, nonzero camera offset, +X/+Y translation, and heading wrap near +/-pi. A 90-degree left turn must increase heading and motion at heading zero must increase room X.
- Stationary axle rotation with an offset phone: camera position traces an arc, computed robot center remains fixed. Test the exact Swift SIMD storage convention against a Python reference.
- Round-trip a documented pose between Swift Codable and Python JSON. Verify required fields, units, enum handling, and maximum packet size.
- Reject malformed/truncated packets, duplicate JSON keys, NaN/infinity, enormous coordinates, wrong units represented by implausible values, wrong identities, duplicate/reordered sequences, and frozen frame times with increasing sequence.
- Simulate clock offset, asymmetric delay, old frames received just now, receiver backlog, sync expiry, session restart and sequence reset. No rejected message may refresh last-good age.
- Verify delayed pose plus wheel replay adds each odometry delta exactly once. Test odometry epoch changes and timestamp-history exhaustion.

## Room trials

| Trial | Procedure | Evidence |
| --- | --- | --- |
| Stationary drift | Dock fixture, 10 minutes, several lighting conditions | XY/heading drift versus time, tracking interruptions |
| Straight distance | Survey a 2 m path; forward/reverse repeats | Endpoint and cross-track errors against physical marks |
| Turns | Repeated 90/180/360-degree rotations | Heading error and axle-center wander |
| Loop closure | Surveyed rectangle; return to original fixture | Endpoint error, largest correction and any discontinuity |
| Ceiling robustness | Blank ceiling, textured ceiling, lamps and fan regions | Dropout duration and recoverability |
| Motion/load | Actual carpet/hard floor, speed ramps and cleaning motors | Vibration impact, packet age and power/thermal behavior |
| Long run | At least 30 minutes | Battery/temperature state, timing stability, drift and WLAN loss |

Use a repeatable fixture or surveyed marks and an independent angle reference. Wheel odometry is a comparison stream, not ground truth. A loop returning to the start can hide intermediate error, so also measure intermediate checkpoints. Record phone capture/send times, Pi receive/application times, raw projected pose, odometry, tracking state, rejection reason, and final mission pose.

Provisional engineering targets: 95th-percentile capture-to-Pi age below 150 ms; no pose older than 250 ms accepted; endpoint error below 100 mm over a 2 m leg; heading error below 3 degrees; stationary axle wander below 50 mm over 10 minutes. These are acceptance proposals to validate, not ARKit accuracy promises. Navigation clearance must account for measured worst-case error, robot radius, and surveyed obstacle uncertainty; revise targets before enabling tight routes.

## Failure injection and stopping behavior

1. Kill the app, lock/background the phone, cover the camera, disable Wi-Fi, deny local-network permission, stop the receiver, and unplug phone power in separate tests. Check immediate invalidation on explicit bad status, or watchdog invalidation no later than 500 ms after the last accepted capture plus one mission period.
2. Measure actual command dispatch and physical stopping distance as well as logical invalidation; a timeout does not mean the wheels have already stopped. Set maximum speed/clearance from the complete stopping budget.
3. Inject tracking relocalization, room-origin jumps, repeated old frames, delayed normal frames after a fault, and reconnect with a new session/calibration. The robot must stop and must not silently resume or change room origin.
4. Lift/carry the robot or loosen the phone mount. Confirm tilt/height/odometry checks detect tested cases, but do not claim they detect all carrying. A moved mount requires recalibration.
5. Trigger cliff, wheel-drop and stale-sensor conditions while good ARKit poses continue. Existing hardware safety must still win. Confirm remote control remains available under its existing safety rules after autonomy stops.
6. Send wrong-room, wrong-robot and retired-session traffic. It must neither alter pose nor refresh localization. Flood malformed packets at a bounded test rate and verify mission timing remains acceptable.

Require at least one second of stable normal tracking before recovery eligibility. After a fault, explicitly restart autonomy while stationary; reconnection alone is insufficient.

## Delivery review

First deliver the foreground app, calibration flow, logging-only receiver and replay fixtures. Next deliver the pose-provider adapter and watchdog tests. Enable only short low-speed waypoints after room trials meet agreed targets. Tag-based discovery remains on its current provider until its scan-driven states are deliberately redesigned.

Archive a short run report with configuration, measured errors, failure-stop timings, unresolved issues and the decision to proceed or remain in observe mode. If ceiling tracking is unreliable, try stable ceiling features or a different camera orientation and repeat the same tests before extending implementation.
