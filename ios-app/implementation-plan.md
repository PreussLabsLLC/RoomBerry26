<!-- @(#)implementation-plan.md 2.3.ios-plan.1 2026/10/29 -->
# Implementation and calibration

## Scope and architecture

Use SwiftUI for setup/status, ARKit for six degree-of-freedom tracking, and Network framework for UDP unicast. Use the rear camera and `ARWorldTrackingConfiguration` with `.gravity` alignment. Check `isSupported` before starting. Compass heading is unnecessary because calibration supplies room orientation. ARKit combines camera and motion observations; its world and camera coordinates are right-handed. See Apple's [Understanding World Tracking](https://developer.apple.com/documentation/arkit/understanding-world-tracking).

```text
Rear camera + IMU -> ARSession -> mount/room transforms -> pose snapshot
                                                       -> UDP sender, 20 Hz
Pi UDP socket -> validation/latest sample -> pose provider -> mission/map
Wheel odometry ------------------------------^               |
Roomba hazard sensors -> existing command arbiter <-----------+
```

The phone sends estimates and health only. It never sends motor commands. Keep Pi hardware and safety paths independent of phone availability.

## Physical arrangement and app lifecycle

Mount the phone so the rear camera sees the ceiling with no bracket obstruction. Specify the camera direction explicitly: “upside down” alone does not define the mount. Measure camera offset from the wheel axle midpoint, yaw relative to robot forward, and height. Use a rigid repeatable bracket, ventilation, adequate power, and restraint that does not press buttons. Test reflections, ceiling fans, lamps, repetitive textures, and vibration. LiDAR is optional and is not assumed to reach the ceiling.

Use these proposed components:

| Component | Responsibility |
| --- | --- |
| `TrackingSession` | Own ARSession; copy transform, frame timestamp, tracking state/reason and mapping status in delegate callbacks |
| `CalibrationStore` | Persist mount transform and room/map identity; hold session-specific room alignment |
| `PoseProjector` | Compose transforms; extract axle-center planar pose; detect tilt and discontinuities |
| `UDPTelemetryClient` | Own NWConnection, session/sequence numbers, clock probes, and latest-only transmission |
| `RunRecorder` | Bounded local pose/status logging; export diagnostics without retaining camera video by default |
| `TrackingViewModel` | Publish status and controls on the main actor |

Keep matrix work and networking off the main thread. A sender timer publishes the newest ARFrame at 20 Hz rather than every camera frame. Drop intermediate samples when busy; bound outstanding sends to avoid a stale backlog. Repeated frame timestamps never refresh freshness on the Pi.

Setup UI: Pi host/port, robot ID, room ID, mount profile, camera/local-network permission status, tracking state/reason, calibration state, packet rate, Pi acknowledgement age, and robot pose. Controls: start/stop tracking, calibrate while stationary, and explicitly reset session. Disable reset/calibration while the Pi reports an active mission. Network-framework readiness alone does not prove that the Pi receives packets.

Add `NSCameraUsageDescription` and `NSLocalNetworkUsageDescription`. Trigger permissions during setup and display denial/recovery guidance. Use manual host entry or a DHCP reservation initially. Add Bonjour discovery and `NSBonjourServices` only in a later phase. Apple's [local network privacy guidance](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy) covers UDP and Network framework.

Keep the app foreground and disable idle sleep only while tracking; restore normal behavior on stop. Backgrounding, screen locking, interruptions, and session errors must invalidate tracking immediately where possible. Delivery of a final status packet is best effort; Pi timeout is authoritative. Do not assume camera tracking continues in the background.

## Coordinate contract

Use `T_A_B` to mean a homogeneous transform mapping coordinates in frame B into frame A; multiply column vectors on the right. All transform translations are meters.

- A: ARKit session world, gravity aligned, +Y up. Do not assume its horizontal axes match the room.
- C: ARKit camera frame from `frame.camera.transform` (`T_A_C`). Do not use screen/display transforms for telemetry.
- B: robot base at the axle midpoint on the floor; +X forward, +Y left, +Z up.
- R: existing room map; X/Y are its configured horizontal axes, +Z up. Heading is counterclockwise from room +X, matching `x += distance*cos(heading)` and `y += distance*sin(heading)` in `roomberry_localization.py`.

Measure a rigid camera mount transform `T_B_C`; store its inverse `T_C_B`. Compose:

```text
T_R_B = T_R_A * T_A_C * T_C_B
x_mm = 1000 * T_R_B[0,3]
y_mm = 1000 * T_R_B[1,3]
heading_rad = atan2(T_R_B[1,0], T_R_B[0,0])
```

Heading uses the projected robot forward axis, not the camera viewing direction: an upward-facing camera's optical axis cannot supply planar heading directly. Reject a near-zero horizontal forward projection. Export radians wrapped to [-pi, pi). Swift SIMD matrices use column storage; unit-test access and composition explicitly.

## Room alignment procedure

1. Stop the robot at a repeatable surveyed fixture, preferably the dock, and verify tracking is normal. Confirm actual axle position and heading; do not infer the axle pose from the visible dock plastic.
2. Load the mount profile. Record several stationary frames, rejecting unstable samples and averaging translation and rotation appropriately.
3. Supply surveyed `T_R_B0`, including robot height/orientation. Compute `T_R_A = T_R_B0 * inverse(T_A_C0 * T_C_B)`.
4. Validate with a measured forward move, left turn, and lateral room displacement. Rotation in place should keep the estimated axle center stationary; an arc indicates a mount-offset error.
5. Bind alignment to room ID, map revision, mount profile, session ID and calibration ID. Pi and phone must agree before `localized=true` is possible.

The repository documents a dock pose near (1060, 260) mm facing room -Y; verify it physically before using it as a calibration reference. Gravity reduces alignment to horizontal translation and yaw once floor height is known, but preserve full transforms so an inverted mount is handled correctly.

Persist mount geometry and room survey across launches. In v1, each new AR session requires explicit stationary alignment. Reuse a saved ARWorldMap only as a later enhancement with demonstrated relocalization and a surveyed checkpoint; loading a file alone does not establish a trustworthy room pose. A carried robot, moved phone, world-origin reset or discontinuity invalidates alignment. Recalibration changes calibration ID and requires the Pi to stop and rebind.

## Pi integration

Current `roomberry.py` constructs `AprilTagLocalizer`; `MissionCoordinator` calls its `update(...)` in `roomberry_mission.py`, then feeds `x_mm`, `y_mm`, `heading_rad`, and `localized` to the mapper. Existing discovery states also depend on tag detections and camera-scan completion. Changing a pose provider alone will not make that tag-survey mission ARKit compatible.

Proposed additions, implemented later:

- `roomberry_external_pose.py`: small standard-library UDP receiver, strict decoder, locked immutable latest sample, counters, startup/shutdown hooks. Receive thread never touches motors or mapper directly.
- `roomberry_pose_provider.py`: explicit source selection and wheel-odometry propagation, with an adapter preserving the mission-facing pose fields.
- Configuration under `external_pose`: enabled flag, bind address/port, expected robot/room/map/calibration identity, allowed phone, timing thresholds and mode (`observe` initially).
- `roomberry.py`: wire receiver/provider lifecycle; publish diagnostics through existing status/log facilities.
- `roomberry_mission.py`: use provider freshness and invalidation; add an ARKit-compatible navigation mode without mandatory tag scans. Keep existing tag discovery as a separate mode.

Rollout modes: `observe` records ARKit alongside existing localization; `arkit_primary` uses qualified ARKit updates with short wheel-odometry bridging; `apriltag` preserves current behavior. Avoid averaging both global sources without a defined estimator and measured uncertainty. Tag disagreement should first be logged, not silently move the ARKit room origin.

For v1, keep a short timestamped wheel-odometry history. Apply an accepted phone pose at its estimated capture time, then replay only subsequent deltas to the mission tick. Never add already-integrated motion twice. If capture-time uncertainty exceeds the configured bound, reject the sample. Start with zero extrapolation in logging mode before implementing this propagation.

Do not apply the existing 900-second tag localization allowance to UDP tracking. Proposed defaults: reject frames older than 250 ms; allow wheel-only bridging for at most 500 ms since the last accepted normal frame, then mark unlocalized and stop autonomous motion. Explicit limited/unavailable/interrupted status invalidates immediately. Recovery needs one second of normal, consistent, fresh tracking and valid alignment. A stopped mission requires explicit restart; remote control remains subject to existing controls and safety rules.

Keep cliff, wheel-drop, bumper, stale-sensor and command watchdog behavior intact. Pose loss must not initiate a blind return-to-dock. Large pose jumps stop motion and require stationary review/recalibration rather than automatic map correction. Distinguish relocalization from robot motion, break map trails across invalid intervals, and do not mark cleaning coverage there.

## Delivery phases

1. Build the Xcode project and foreground tracking/status UI; validate actual ceiling performance by hand.
2. Implement transforms/calibration and a logging-only UDP receiver. Capture synchronized phone/Pi logs during manual driving.
3. Implement timing, strict validation, diagnostics, lifecycle invalidation and fault-injection tests.
4. Add source adapter and delayed-pose odometry replay; compare against measured paths with autonomy disabled.
5. Enable low-speed bounded waypoints with safety stop tests, then ARKit-compatible cleaning/return routing.
6. Consider saved-map relocalization, Bonjour, multiple-room selection and more sophisticated fusion only after baseline acceptance.
