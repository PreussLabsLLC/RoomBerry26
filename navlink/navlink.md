<!-- @(#)navlink.md 2.3.navlink.5 2026/10/30 10:16:06 -->
# NavLink design review

NavLink v1 recording milestone, October 30, 2026. StarLock emits the binary format below; Roomberry receives and records it without using it for navigation. This replaces the earlier [JSON wire proposal](../ios-app/udp-protocol.md). Room alignment, mount calibration, clock exchange and navigation qualification remain future work.

NavLink connects StarLock on the iPhone to Roomberry on the Raspberry Pi Zero. StarLock should produce robot-ready measurements and deliver small, fixed binary records that the Pi can unpack directly. Keep every application datagram below 1 KB. A regular motion packet can fit in 128 bytes.

Separate frequent motion samples from occasional diagnostics and map updates.

## Useful measurements

| Data | Value to Roomberry | Processing on iPhone |
| --- | --- | --- |
| Room X/Y and heading | Primary localization | Apply room alignment and camera-to-axle offset |
| Forward/lateral velocity | Compare actual motion with wheel odometry; detect slip or stalled movement | Derive and filter AR pose changes |
| Yaw rate | Compare commanded turns with actual turns | Project gyro onto robot vertical axis |
| Forward/lateral/vertical acceleration | Detect impacts, vibration and unusual movement | Remove gravity, rotate into robot axes, summarize |
| Roll, pitch and height change | Detect lifting, tipping or mount movement | Apply mount compensation |
| Tracking state and reason | Decide whether pose is usable | Encode as small numeric enums |
| Capture timestamp, sequence and alignment identity | Reject stale, reordered or wrong-session measurements | Attach to every packet |
| Measurement-validity flags | Distinguish unavailable values from legitimate zero | Set separately for pose, velocity and IMU |

Core Motion exposes attitude, rotation rate, gravity and gravity-separated acceleration. StarLock can convert those into robot coordinates before transmission. See [Apple: CMDeviceMotion](https://developer.apple.com/documentation/coremotion/cmdevicemotion).

ARKit pose already incorporates motion sensing. Its pose and the phone's IMU are related observations; do not fuse them as independent evidence. Accelerometer integration is a poor long-term position source. Gyro yaw rate, tilt, impact detection and wheel/visual-motion disagreement are more useful initial applications.

Keep high-rate IMU recordings on the phone and send filtered values plus interval peaks to the Pi. This preserves short impacts without requiring the Pi to consume hundreds of samples per second.

## Implemented 128-byte observation packet

All multi-byte values are little-endian. Physical measurements use IEEE 754 `float32`; integers are unsigned. Datagram length is exactly 128 bytes. Destination is UDP `pi:5010`, with `pi.local:5010` as the Avahi fallback after an unsuccessful connection attempt. Connection attempts retry every five seconds while unresolved or stalled. UDP readiness/send completion does not acknowledge receipt.

| Block | Bytes | Contents |
| --- | ---: | --- |
| Header | 8 | Magic, version, message type, byte length |
| Identity | 16 | Session token and alignment token, each 64 bits |
| Sequence and health | 8 | Sequence, validity bits, tracking/reason enums |
| Timing | 24 | Capture time, send time, associated IMU time |
| Pose | 24 | X/Y/Z, heading, roll, pitch; currently session-relative camera pose |
| Motion | 24 | Forward/lateral velocity, yaw rate, three-axis acceleration; validity/axis flags apply |
| Interval diagnostics | 16 | Acceleration magnitude peak and RMS, feature count, IMU sample count, frame age |
| Phone battery | 2 | Charge percentage and charging-state enum, one byte each |
| Reserved | 6 | Explicitly zero for this version |
| **Total** | **128** | |

Exact Python format: `struct.Struct('<4sBBHQQIHBBQQQ14fHHIBB6s')`.

| Byte offset | Type | Field |
| ---: | --- | --- |
| 0 | 4 bytes | ASCII `NVLK` |
| 4 | u8 | Version = 1 |
| 5 | u8 | Type = 1 (observation, including unhealthy status) |
| 6 | u16 | Length = 128 |
| 8 | u64 | Nonzero random session token |
| 16 | u64 | Alignment token; zero until surveyed alignment is implemented |
| 24 | u32 | Sequence; increasing per emission tick, gaps allowed |
| 28 | u16 | Flags, defined below |
| 30 | u8 | Tracking state |
| 31 | u8 | Tracking reason |
| 32 | u64 | AR frame capture uptime, microseconds; zero if absent |
| 40 | u64 | Packet assembly uptime, microseconds (send time) |
| 48 | u64 | Latest valid IMU uptime, microseconds; zero if absent |
| 56 | 6 × f32 | X/Y/Z in mm, heading/roll/pitch in radians |
| 80 | 3 × f32 | Forward/lateral velocity in mm/s, gravity-projected yaw rate in rad/s |
| 92 | 3 × f32 | Gravity-separated acceleration X/Y/Z in mm/s² |
| 104 | 2 × f32 | Peak and RMS acceleration magnitude over IMU samples since last tick, mm/s² |
| 112 | u16 | Raw feature count, saturating at 65535 |
| 114 | u16 | IMU samples contributing to the interval statistics |
| 116 | u32 | Frame age at assembly in microseconds; 0xffffffff if absent/invalid |
| 120 | u8 | Battery percentage |
| 121 | u8 | Battery state |
| 122 | 6 bytes | Reserved; zero |

Flags:

- Bit 0: pose usable for observation: normal tracking, capture age 0–250 ms, valid heading projection, no interruption/error.
- Bit 1: velocity valid: differentiated successive usable poses with positive capture-time spacing no greater than 500 ms. No filtering is applied yet.
- Bit 2: IMU valid: latest Core Motion measurement is no more than 100 ms old.
- Bit 3: interval acceleration statistics valid.
- Bit 4: surveyed robot-axle/room calibration valid. Always clear in this milestone.
- Bit 5: session-relative camera pose. Always set in this milestone.
- Bit 6: acceleration uses native Core Motion device axes. Set alongside valid IMU in this milestone.
- Bits 7–15: reserved, zero.

Tracking: 0 unavailable, 1 limited, 2 normal, 3 interrupted. Reasons: 0 none, 1 initializing, 2 excessive motion, 3 insufficient features, 4 relocalizing, 5 interrupted, 6 session error, 7 other. Values whose validity bits are clear must not be interpreted as measurements; they may be zero or diagnostic remnants of an unhealthy frame.

The current coordinate system is gravity-aligned session space: X = ARKit X, Y = negative ARKit Z, Z = ARKit Y. The origin is the AR session origin, not the dock or floor. Translation describes the camera center. Heading uses the horizontal projection of AR camera +Y, appropriate for investigating an upward-facing mount; a near-vertical projection clears pose validity. For orientation calculations the candidate base axes are camera (+Y, +X, -Z). This is an explicit diagnostic convention, not a measured camera-to-robot mount. Roll and pitch use a Z-Y-X decomposition of that basis.

Velocity is calculated in the projected forward/left directions. Acceleration remains in Core Motion's native device axes, flagged explicitly; yaw rate is projected onto gravity-opposed up. IMU and pose have separate timestamps because they are not sampled simultaneously. The app requests 50 Hz device-motion samples and transmits the latest IMU value plus interval peak/RMS at 10 Hz. It does not yet retain a high-rate on-phone recording.

Foreground tracking disables automatic idle sleep; leaving the foreground stops transmission and pauses ARKit. Resuming starts a new AR epoch/token. An AR interruption clears pose validity; interruption recovery also changes the token. Session errors remain invalid until tracking is restarted. A new token is generated before sequence overflow. Repeated frames keep their original capture time; recording does not imply freshness or navigation validity.

The packet assembly clock is `ProcessInfo.systemUptime`. Capture and motion timestamps come from ARKit/Core Motion; the sender checks their ordering and ages against uptime. On-device logs should confirm this time-base relationship. No synchronized Pi capture time is claimed.

Use fixed-width integers for the header/timing and IEEE 754 `float32` for physical values, with an explicitly specified byte order. Millimeters and radians match the existing Pi code. Float precision is ample here; sensor accuracy will dominate.

Python can decode the record with one precompiled `struct.Struct`. Swift should serialize fields explicitly rather than transmitting a Swift struct's memory layout, which may contain padding.

Room names, mount descriptions and other strings belong in future setup. Before navigation, the Pi must explicitly bind numeric session/alignment tokens to that configuration.

The recording receiver checks length/version/type, nonzero session, supported flags/enums, timestamp ordering, finite measurements, battery encoding and reserved bytes. It deliberately retains duplicates, out-of-order samples, limited tracking and new sessions for offline analysis. It does not qualify freshness, bind an alignment or validate motion for navigation. These additional checks are required before any future navigation consumer. Matrix calculations, coordinate conversion, filtering and feature analysis belong on StarLock.

Clock synchronization remains necessary: arrival time alone cannot reveal a delayed packet. The phone can calculate the clock offset, leaving the Pi a subtraction and age check. The exchange, uncertainty bounds and expiry behavior still need specification; do not subtract unrelated monotonic clocks directly.

Start at 10 Hz (one sample every 100 ms), matching the intended serial pace. At 128 bytes per sample, this means 1.28 KB/s of application payload. There is no need to approach the 1 KB packet limit. Publish the newest available observation at each send tick; do not queue intermediate frames or make a repeated frame appear fresh.

## Phone battery telemetry

Enable `UIDevice.current.isBatteryMonitoringEnabled` to read `batteryLevel` and `batteryState`. iOS also provides notifications when these change. See [Apple: battery monitoring](https://developer.apple.com/documentation/uikit/uidevice/isbatterymonitoringenabled).

Proposed NavLink encoding:

- `battery_pct`: `uint8`, 0–100; 255 means unavailable. Check for an unavailable reading before converting to a percentage.
- `battery_state`: `uint8`, 0 unknown, 1 unplugged, 2 charging, 3 full. Map explicitly from the UIKit enum.

The current sender caches and polls these values once per second, repeating them in each 10 Hz packet. Notification-based refresh remains an option. They are slowly changing telemetry, not measurements taken at the pose capture timestamp. Two previously reserved bytes keep the total at 128 bytes.

This lets Roomberry display phone charge, log discharge trends and detect an unplugged charging connection. Low-battery warning and mission policies remain to be decided; charging alone does not prove that incoming power exceeds tracking consumption.

## Frame rates and phone power

Treat these as separate rates:

- NavLink transmission: initially 10 Hz.
- ARKit camera capture and frame delivery: select from `ARWorldTrackingConfiguration.supportedVideoFormats`; investigate a 30 fps format if the SE offers one.
- SceneKit preview rendering: the displayed 60 fps statistic describes rendering, not a measurement of ARKit's internal processing rate. A lower preview rate can be selected independently.
- IMU acquisition and summaries: retain enough sampling bandwidth for impacts and turns, then summarize for the 10 Hz packet.

ARKit's camera frame rate and resolution are controlled by the configuration's `videoFormat`, selected from the supported formats. Do not assume arbitrary rates such as 10 fps are available. See [Apple: ARConfiguration.VideoFormat](https://developer.apple.com/documentation/arkit/arconfiguration/videoformat-swift.class).

Reducing NavLink frequency alone does not reduce camera or tracking work. For a future operating mode, minimize preview rendering, disable debug overlays and unused plane detection, dim the display, and keep the tracking session active. Screen locking/backgrounding is not a power-saving tracking mode.

Compare supported 30 and 60 fps capture modes on the actual ceiling route. Measure battery drain, thermal state, tracking losses, pose jitter and latency over sustained runs. Lower capture rates may reduce power but may also weaken tracking during turns or vibration; the tradeoff is not yet measured. Following a resource-constraint warning on Peters SE, the current app requests 15 fps preview rendering and selects the lowest-resolution supported 30 fps camera format, if available; otherwise it retains ARKit's default camera format. It prints the actual requested camera format at startup. Debug overlays, statistics and light estimation are disabled; plane detection is not enabled. NavLink remains at 10 Hz.

For representative performance measurements, turn off GPU Frame Capture and Metal API Validation in Xcode's Edit Scheme > Run settings, or launch the installed app directly from the phone outside the debugger. These tools add runtime overhead; see [Apple: Metal scheme settings and performance](https://developer.apple.com/library/archive/documentation/Miscellaneous/Conceptual/MetalProgrammingGuide/Dev-Technique/Dev-Technique.html). A resource-constraint warning does not by itself establish the cause of a signal-9 termination. Check device logs and a matching JetsamEvent report to confirm a memory-pressure kill; see [Apple: jetsam event reports](https://developer.apple.com/documentation/xcode/identifying-high-memory-use-with-jetsam-event-reports).

## Pi recording and manual operation

The [receiver](../roomberry/roomberry_navlink.py) uses only the Python standard library. The `navlink` section in `roomberry/autonomy.json` enables it when Roomberry starts normally, including a manual `python3 roomberry.py` launch. It closes and flushes on normal Roomberry shutdown. No systemd service is required. Deploy and start/stop on the Pi manually; no Pi deployment is performed by this change.

For telemetry-only testing, run the receiver alone from the deployed `roomberry` directory, without opening serial or camera hardware:

```sh
python3 roomberry_navlink.py --directory "$HOME/navlink-logs"
```

Stop with Ctrl-C. Do not run both the standalone receiver and Roomberry's enabled receiver on port 5010 simultaneously. If Roomberry cannot open the UDP port or log directory, it logs a warning and continues without NavLink recording. Set `navlink.enabled` to false to disable it; optional `allowed_source` takes a literal IPv4 address.

Default integrated logs: `/var/log/roomberry-navlink/roomberry-navlink-YYYYMMDD-HHMMSS-NNNN.bin`. The user running Roomberry needs write access to that directory. A 64 KiB Python buffer is flushed every 10 seconds (also while idle), on rotation and at normal shutdown. No per-packet fsync. Abrupt termination can lose buffered data.

Files rotate on receiver start or before exceeding 16 MiB; at most 20 matching logs are retained by default. Both limits are configurable with `max_file_bytes` and `max_files`. At 10 Hz, records occupy about 5.18 MB/hour, excluding the small file header.

Binary log layout:

- 16-byte header, `<8sHHI`: magic `NVLLOG1\0`, log version 1, record size 144, UDP payload size 128.
- Each 144-byte record: `<QQ` Pi receive wall-clock nanoseconds and Pi receive monotonic nanoseconds, followed by the unchanged 128-byte UDP payload.
- Pi receive wall time supports comparison with serial sensor CSV logs. Phone uptime is a separate clock; do not subtract it from Pi timestamps. Clock synchronization is not implemented in this milestone.

Export on the Mac or Pi without changing the low-cost recording path:

```sh
python3 roomberry_navlink.py --csv /path/to/roomberry-navlink-run.bin > navlink.csv
```

The exporter includes named fields and receipt timestamps and warns/ignores an incomplete final record after an abrupt shutdown. `roomberry/tools/get-pi-logs` also fetches the integrated log directory into `roomberry/logs/navlink/`.

The iPhone requires camera and local-network access. Its status says “UDP sent” and “receipt unconfirmed”; inspect a growing Pi log to confirm reception. The app tries `pi` first and `pi.local` as fallback. This milestone supports the Pi's IPv4 endpoint.

## Room dimensions, walls and furniture

The first-generation iPhone SE and the upward-facing camera set the practical limits.

| Capability | What to pursue |
| --- | --- |
| Horizontal/vertical plane detection | Plane positions, orientations and observed boundaries; candidates for ceilings, floors and walls |
| Sparse feature points | Tracking diagnostics and experimental geometry processing |
| Room dimensions | Estimate from observed opposing planes or deliberately selected measurement points |
| Furniture geometry | Some visible surfaces; recognizing complete furniture requires additional processing |
| Dense mesh / RoomPlan | Requires capabilities the first-generation SE lacks |

ARKit reports observed planes through `ARPlaneAnchor`. Their boundaries describe detected surface patches; a patch's extent is not necessarily the full wall dimension. Check classification support on-device. See [Apple: ARPlaneAnchor](https://developer.apple.com/documentation/arkit/arplaneanchor).

Raw feature points are intermediate tracking features. Apple warns that their number and arrangement can change between frames. Do not turn them directly into obstacle cells. See [Apple: rawFeaturePoints](https://developer.apple.com/documentation/arkit/arframe/rawfeaturepoints).

RoomPlan provides dimensions and furniture categories using the camera and LiDAR. It requires a different device from Peters SE. See [Apple: RoomPlan](https://developer.apple.com/augmented-reality/roomplan/).

With the camera pointing upward, expect the best observations to be the ceiling and upper wall portions. Furniture and floor-level obstacles will often be outside its view. This is a practical expectation to test, not a measured result. A separate handheld survey mode could inspect the whole room, although aligning that survey with subsequent robot tracking would need deliberate calibration.

## Map transfer

StarLock should reduce observations to room-coordinate wall segments, obstacle footprints or occupancy tiles. Send these as separate, bounded messages with revision numbers and acknowledgement/retry.

Motion packets can discard old samples; map updates need recovery from packet loss. Avoid sending raw images, point clouds or meshes to the Pi for interpretation.

## Preferred first version

- 128-byte motion packets at 10 Hz.
- Phone-side IMU processing and recording.
- Occasional health packets.
- A separate mapping channel, developed after motion telemetry.

This provides localization and motion diagnostics while leaving room surveying open for experimentation. Existing freshness, explicit alignment binding and receiver watchdog requirements from the earlier proposal remain relevant even though the encoding changes.
