<!-- @(#)README.md 3.1.roomtrek.2 2026/11/08 12:00:00 -->
# RoomTrek

RoomTrek is a standalone iOS app for ARKit map surveying and cross-device
relocalization. It does not modify StarLock, GroundHog or GridRunner.

- **Surveyor** (iPhone 11 Pro, Sputnik, iOS 18.7): surveys a room and
  saves a persistent ARWorldMap to a local library.
- **Navigator** (iPhone X, Peters 10, iOS 16.7.16): loads that map via
  `ARWorldTrackingConfiguration.initialWorldMap` and reports a
  map-relative camera pose. The long-term goal is a room-relative
  position stream for Rosie to fuse with wheel odometry; the first
  version only proves transferable maps and cross-device localization.

Target: iPhone 11 Pro (Surveyor) + iPhone X (Navigator), `IPHONEOS_DEPLOYMENT_TARGET = 15.0`,
Xcode 14.2 (SDK 16.2), Swift 5.0, landscape only. No LiDAR, RoomPlan,
scene-reconstruction meshes, depth APIs, cloud services or external SLAM.
Only `ARWorldTrackingConfiguration`, SceneKit (`ARSCNView`), `Network`
(UDP), and standard Apple frameworks are used.

## Build and install

Build in Xcode as you would GridRunner/GroundHog:

```
xcodebuild -project ios-app/RoomTrek/RoomTrek.xcodeproj -scheme RoomTrek \
  -sdk iphoneos -configuration Release CODE_SIGNING_ALLOWED=NO build
```

Signed builds use the repository's automatic signing
(`DEVELOPMENT_TEAM` is already in the project, `com.preusslabs.RoomTrek`).
Install the Release build on **both** phones (Sputnik for surveying,
Peters 10 for navigating). The unsigned command above only proves compilation; device installation requires signing.

> Note: Xcode 14.2's bundled SDK is 16.2. Deploying to an iOS 18.7 device
> (Sputnik) may need a newer Xcode or DeviceSupport image for the install
> step; compilation is unaffected. Deployment target 15.0 is a floor, not
> a ceiling.

## Operation

Landscape UI. Select the mode, then **Start**. Stopping on background or
Stop is explicit; a new Start generates a new session identity. All
statuses are text, not colour alone.

### Surveyor

1. Mount the iPhone 11 Pro on a small wheeled dolly at Rosie's camera
   height, rear camera outward.
2. **Start Survey**. Live camera + feature-point overlay advance in
   `ARSCNView`; HUD shows tracking state, mapping status
   (`notAvailable / limited / extending / mapped`), feature-point count,
   camera position/yaw and NavLink status.
3. Slowly traverse the kitchen, observing walls, cabinets, doorframes and
   furniture; make overlapping loops and return to the start (Phase A).
4. Enter a map name (optional note), **Save Map**. The HUD never labels a
   map "complete" from ARKit's `mapped` state alone — the operator's Save
   is the commit. `ARSession.getCurrentWorldMap` is archived with
   `NSKeyedArchiver (secure coding)` into
   `Documents/RoomTrekMaps/<uuid>.roomtrek`.

Library: tap to select, Rename, Delete. Metadata preserved per map:
name, UUID, creation timestamp, source device model/OS, tracking and
mapping status at capture, coordinate notes, optional description.

### Navigator

1. Select the map in the library. **Start Navigator** runs
   `ARWorldTrackingConfiguration` with `initialWorldMap = selectedMap`.
2. HUD distinguishes `RELOCALIZING` (limited + relocalizing),
   `NORMAL`, `LIMITED — …`, `UNAVAILABLE`, `INTERRUPTED`. The retained
   pose is the **camera pose in the map coordinate system** (numeric
   position/orientation shown; the robot-center pose is `PoseCamera *
   inverse(T_B_C)`, identity until mount calibration exists).
3. **Reset / Retry** creates a new session identity with the same stored
   map; **Stop** pauses the session. Never treat a valid camera
   transform as proof of relocalization: only sustained normal tracking
   (≥ 1 s) after relocalizing counts as a `localized (candidate)`, and
   validity additionally requires fresh capture age + a usable heading
   projection. Record time-to-relocalization, move the phone along a
   known path, return to the physical start, and record the final pose +
   tracking state (Phase B). The initial error target is 30.48 cm (one
   kitchen tile), an investigation gate, not an ARKit claim.
   Return-to-start error alone does not establish absolute accuracy
   along the path — include a mid-path checkpoint.

Phase C is repeatability from different starts/orientations.

## Map transfer

Offline only; no iCloud, server or account. **Export Selected Map**
opens the Files export picker for the single `.roomtrek` file; move it
via Files (AirDrop/manual) to the other phone. **Import Map (Files)**
uses `UIDocumentPickerViewController` and validates before loading:
JSON shape, `version == 1`, `format == roomtrek-map`, non-empty
`mapData`, and that the payload really unarchives to an `ARWorldMap`.
Corrupted/incompatible files are rejected with an alert and a session-log
entry; the library is untouched. Metadata is preserved across the
transfer. **Do not assume portability** — the 11 Pro → X experiment is
the validation.

## Pose and coordinates

`TrekPose` holds position (m), orientation quaternion, yaw, timestamp
(`ARFrame.timestamp`, phone uptime), tracking/reason codes,
world-mapping status, relocalization state, map ID, feature count and a
validity flag. ARKit is right-handed with +Y up; the app stores metres
in the mapped convention `(AR.x, -AR.z, AR.y)` so Z is up, matching
StarLock's NavLink mapping. Yaw is `atan2(mappedForward.y, mappedForward.x)`
where `mappedForward` is StarLock-mapped optical forward (`-column2`):
0 rad faces mapped +X. The quaternion rotates native camera axes into mapped world axes: `R_M_C = B * R_A_C`, where `B` implements `(x,-z,y)`. The quaternion is authoritative; yaw/roll/pitch
are derived. Camera pose is the source; robot pose is
`T_M_B = T_M_C * inverse(T_B_C)` with `T_B_C` describing the camera mount
in robot body axes (identity in v1, configurable in `MountTransform`). The three frames — ARKit world, camera, robot
body — are never silently reinterpreted: only an explicit Reset changes
the session identity.

## NavLink

Optional and off by default. Host defaults to `pi`, port 5010, 10 Hz latest-only UDP.
The approved experimental v1/type-6 extension is specified in [NAVLINK.md](NAVLINK.md).
It preserves full map UUID, camera quaternion and explicit relocalization state.
Existing Pi receivers **reject type 6**; receiver support is a follow-up, and this
implementation does not change robot behavior. UDP send completion is not receipt.
Only fresh, normal, relocalized Navigator poses set the validity bit; Surveyor
packets are diagnostic only. Camera pose is always distinct from robot-center pose.

## Logging

`Documents/RoomTrekLogs/trek-<timestamp>.jsonl` (event log) +
`.csv` (pose log). Session events (start/stop, tracking/mapping
transitions, map save/load/export/import, relocalization attempts and
outcomes, NavLink errors) are JSONL. Poses are CSV at a configurable
throttle (default 2 Hz; the session enforces it — never per frame).

CSV columns:
`iso_ts, frame_ts_s, session, map_id, tracking, reason, reloc, valid,
mapping, x_m, y_m, z_m, qx, qy, qz, qw, yaw_deg, features`.
**Export Log + Pose CSV** shares both files.

## Two-phone test procedure

**Phase A — Survey (Sputnik, 11 Pro).** Dolly at Rosie camera height,
Start Survey, slow overlapping loops of the kitchen, return to start,
Save, Export via Files.

**Phase B — Relocalization (Peters 10, X).** Import the `.roomtrek`,
Start Navigator with it. Observe `RELOCALIZING → NORMAL`, record
time-to-relocalization. Move along a known path with a mid-path
checkpoint, return to the physical start, record estimated final pose +
tracking state. Compare the start and final estimates against the
30.48 cm target.

**Phase C — Repeatability.** Restart Navigator from at least three
different starts/orientations (Reset / Retry between attempts), record
each time-to-relocalization and return error.

A successful demonstration shows: transfer success, cross-device
relocalization, stable map-relative reporting, and repeatable
return-to-start measurements.

## Known limitations

- Relocalization success is `limited(relocalizing) → normal` sustained
  ≥ 1 s — a heuristic, not a measurement of absolute accuracy.
- Map portability across devices is unproven until Phases A–C run.
- Mount transform is identity: NavLink reports camera pose, and every HUD labels it "CAMERA, not robot center".
- `worldMappingStatus == mapped` means ARKit is satisfied, not that the
  kitchen coverage is good.
- NavLink type 6 needs Pi receiver and exporter support; current receivers reject it.
- Host-side `tests/TrekChecks.swift` covers yaw/validity, map token,
  type-6 wire bytes and JSON round-trip. Feature-point overlay, File
  transfer, relocalization timing and the 30.48 cm error require the
  physical phones and kitchen route.

## Next steps

- Mount calibration (`T_B_C` from measured values) so NavLink can mark
  robot-axle pose.
- Add and test the specified NavLink type 6 receiver on the Pi before fusion.
- Investigate relocalization sensitivity to camera height, lighting and
  mount before attempting fusion with wheel odometry.

## Out of scope (v1)

Meshes, RoomPlan, semantic classification, map merging, path planning,
obstacle avoidance, cleaning, multi-room maps, sensor fusion and cloud
sync are future work.

## Host checks

```
swiftc -module-cache-path /tmp/roomtrek-swift-cache \
  ios-app/RoomTrek/RoomTrek/{TrekPose,TrekPacket,MapPackage}.swift \
  ios-app/RoomTrek/tests/TrekChecks.swift -o /tmp/roomtrek-checks
/tmp/roomtrek-checks
```

The localization gate requires observing ARKit's relocalizing state and then
one second of normal tracking. If the initial limited state is never delivered,
the app conservatively remains unreliable: use Reset / Retry. This follows
[Apple's documented world-map lifecycle](https://developer.apple.com/documentation/arkit/managing-session-life-cycle-and-tracking-quality).
A normal state is an ARKit candidate match, not an independent accuracy test.
Logs are capped at 16 MiB per file; logging stops at the cap (no rotation).
Export before starting a long new trial. Map operations are synchronous and can
briefly pause the UI on large maps. No camera video is recorded.

## Build verification and device status (2026-11-08)

Xcode 14.2 signed Release build and host checks pass. USB detects the 11 Pro
as Sputnik, iOS 18.7.7. Developer Mode is enabled. Installation fails with
`0xe8008015` because the selected profile excludes Sputnik; Xcode 14.2 cannot
prepare it because iOS 18 device support is missing. Automatic provisioning
refresh still lists only the two older phones.

This is a free Personal Team account: manual device/profile management in the
paid developer portal is not the solution. Open this project on the newer Mac,
select the Personal Team with automatic signing, connect Sputnik and Run so
Xcode can provision it. Xcode 27.2 lists device support for iOS 17 and later;
retain the older Xcode setup for the iPhone X on iOS 16. Keep the iOS 15 target
and Swift 5 language mode. See [Apple's compatibility table](https://developer.apple.com/xcode/system-requirements)
and [automatic signing workflow](https://help.apple.com/xcode/mac/current/en.lproj/dev60b6fbbc7.html).
No ARKit runtime or cross-device accuracy result is claimed from build checks.

Before kitchen trials, verify Stop/Start logging, Reset/Retry, camera permission
denial, background interruption, feature-poor/covered camera, malformed import,
map rename/delete, and Files export/import. Invalid/limited/stale observations
must never carry the NavLink valid bit. Keep telemetry disabled until a matching
receiver exists. For each trial record map UUID, phone/OS, camera height, start
orientation, lighting, time to candidate, tracking losses, checkpoint errors and
return displacement. Record failed attempts as well as successes; use physical
marks/tape measurements rather than encoder estimates as the reference.
