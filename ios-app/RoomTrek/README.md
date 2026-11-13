<!-- @(#)README.md 3.2.imu.1 2026/11/12 15:16:02 -->
# RoomTrek

For the phone-by-phone walkthrough, see [Room scan and transfer guide](ROOM-SCAN-GUIDE.md).

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
4. Enter a map name (optional note), **Save Map**. You can save while surveying
   or after tapping **Stop**, before starting another session. The button shows
   **Saving Map…** until capture and storage finish, then confirms success or error. The HUD never labels a
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

## Mothership

The **Mothership — report to (UDP 5010)** field selects the Raspberry Pi that
receives telemetry, heartbeats and control replies. It defaults to `pi3.local`.
Enter `pi3`, `pi3.local`, or an IPv4 address, then tap Done. The app remembers
this setting across launches and reconnects an existing link when it changes.
Stop the current AR session before editing this field. Enter a host only,
without `http://`, a path or a port; the UDP port stays 5010. The phone and Pi
must be on the same reachable network. A UDP-ready message does not confirm
that the Pi has received packets. Shared-key provisioning is unchanged.

## NavLink

Optional and off by default. Host defaults to `pi`, port 5010, 10 Hz latest-only UDP.
The approved experimental v1/type-6 extension is specified in [NAVLINK.md](NAVLINK.md).
It preserves full map UUID, camera quaternion and explicit relocalization state.
The Pi receiver records and exports type 6 without feeding it into robot
localization. Authenticated bidirectional commands share this socket; see
[NAVLINK.md](NAVLINK.md#bidirectional-control-32navlink1) for key provisioning,
wire format, operation status and Python CLI examples. UDP send completion is not receipt.
Fresh, normal, relocalized loaded-map poses (Navigator or resumed Surveyor) set
the validity bit; fresh Surveyor packets remain diagnostic only. Camera pose is always distinct from robot-center pose.

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
- Remote control requires a provisioned shared key and the upgraded Pi receiver.
- Host-side `tests/TrekChecks.swift` covers yaw/validity, map token,
  type-6 wire bytes and JSON round-trip. Feature-point overlay, File
  transfer, relocalization timing and the 30.48 cm error require the
  physical phones and kitchen route.

## Next steps

- Mount calibration (`T_B_C` from measured values) so NavLink can mark
  robot-axle pose.
- Validate bidirectional commands and type-6 telemetry on the Pi and phones before fusion.
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
must never carry the NavLink valid bit. Use the matching receiver and provision the shared key before remote-control
trials. For each trial record map UUID, phone/OS, camera height, start
orientation, lighting, time to candidate, tracking losses, checkpoint errors and
return displacement. Record failed attempts as well as successes; use physical
marks/tape measurements rather than encoder estimates as the reference.


## Spoken voice

Use the Australian voice menu and **Test Voice** to audition installed `en-AU`
options for the desired young female character. The chosen identifier, pitch
(initially 1.08) and rate (initially 0.52) persist. No voice name, age or gender
is assumed. Missing voices fall back to another installed Australian voice,
then the system default. Voice names, identifiers and quality levels are in
Export Log + Pose CSV's JSONL file. See [SPEAK settings and CLI](NAVLINK.md#speak-voice-settings).


## Pi-owned run surveys

Roomberry can now start Surveyor at mission start, save `kitchen-YYMMDD` when
returning to idle and stop the phone session after saving. See
[Pi-controlled survey setup](../../roomberry/docs/roomtrek-survey.md).
With a provisioned key, the app starts NavLink enabled unless explicitly turned
Off; that setting persists. Keep the app foreground. The headline now displays
its SCCS version and build timestamp so the installed build is identifiable.

## Audible tracking heartbeat

Enabled by default; the **10s tracking ping** switch persists its setting.
With RoomTrek foregrounded, a short high1100Hz tone means an active session,
valid normal tracking, a frame no more than1second old and NavLink enabled.
A lower440Hz double tone means the app is awake but tracking/session/NavLink
needs attention. Idle sessions also use the low double tone, so they do not
pretend to be tracking. Tone interval is10seconds; speech delays the next tone
without interrupting speech or replaying missed pings.

Tones stop when RoomTrek backgrounds or audio is interrupted. Silence can also
mean ping disabled, volume/routing problems, or speech in progress; it is not
a healthy signal. Set the iPhone media volume and check the speaker before
mounting it. Active sessions prevent automatic screen sleep as before.
The high tone confirms local tracking, not successful Pi delivery, map coverage
or saved-map quality. No UDP configuration or robot control changes.

## Kitchen map revisions

The Pi now resumes the newest saved kitchen map rather than starting fresh on
every mission. Authenticated SURVEY_START accepts map_id, loads initialWorldMap
and completes after relocalization; mapping continues in that same session.
SURVEY_SAVE writes a new UUID-backed revision with parent/lineage/revision and
feature-count metadata. Previous maps are preserved. Invalid/stale tracking,
failed relocalization or limited mapping prevents an automatic revision save.
The library shows revision number and feature count; old packages remain readable.
This extends one loaded map; it does not merge the independent maps from earlier
runs or guarantee coverage/accuracy improvement. See
[Pi lifecycle](../../roomberry/docs/roomtrek-survey.md) and
[command examples](NAVLINK.md#cumulative-kitchen-maps-32).

## Additional motion comparison

Build3.2.imu.1 adds a separate Core Motion stream alongside ARKit: attitude,
gyro, gravity, user acceleration and integrated vertical gyro rotation. The Pi
web console compares relative gyro, ARKit and wheel turns; it hides unavailable
or stale comparisons. This is diagnostic only and cannot steer or correct pose.
See [type7packet and comparison details](NAVLINK.md#type-7--independent-core-motion-diagnostics-32imu1).
The iPhone app and Pi receiver must both be updated; the existing key remains.
