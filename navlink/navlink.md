<!-- @(#)navlink.md 3.1.compass.1 2026/10/31 12:10:00 -->
# NavLink design review

Version 3.1 adds GroundHog floor-relative motion as wire version 1, message type 2. Type 1 retains its original meaning and layout. See the GroundHog specification below and [app instructions](../ios-app/GroundHog/README.md). Existing receivers must be upgraded before they can accept type 2.

NavLink v1 recording milestone, October 30, 2026. StarLock emits the binary format below; Roomberry receives and records it without using it for navigation. This replaces the earlier [JSON wire proposal](../ios-app/udp-protocol.md). Room alignment, mount calibration, clock exchange and navigation qualification remain future work.

NavLink connects StarLock on the iPhone to Roomberry on the Raspberry Pi Zero. StarLock should produce robot-ready measurements and deliver small, fixed binary records that the Pi can unpack directly. Keep every application datagram below 1 KB. A regular motion packet can fit in 128 bytes.

Separate frequent motion samples from occasional diagnostics and map updates.

## Useful measurements

### Measured rear mount, October 30

The user measured the iPhone camera lens 145 mm behind the Roomba center and
22 mm to its right when viewed from above with the robot heading upward. In
robot coordinates with X forward and Y left, the camera offset is
`r_camera = (-145, -22)` mm. This is the lens position, not the phone's center.
For a calibrated robot heading `theta`, recover the robot center using
`p_robot = p_camera - R(theta) r_camera`. Equivalently, add 145 mm forward and
22 mm left to the camera pose. This removes the camera's arc during a pivot.

The horizontal heading projection in the packet is still camera +Y, so mount
yaw must be determined separately before using the offset. Straight-motion
intervals from the 15:10:54 ride-along suggest adding about 93° to that camera
heading to obtain robot forward in session coordinates. This is an offline
estimate, not a surveyed orientation, and should not be copied from the older
mount's approximately 180° convention. No camera height was measured here.
The packet remains session-relative and recording-only; this measurement does
not set the room/axle calibration-valid flag or enable navigation fusion.

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


## GroundHog relative motion (3.1, wire v1/type 2)

GroundHog sends to the same UDP endpoint at 10 Hz. The datagram is exactly 128 bytes, little-endian, with explicit Swift serialization. Physical values are finite IEEE 754 float32. This is relative robot-center odometry, not a surveyed room position. Type 1's flag definitions, tracking reasons and field semantics must not be applied to type 2.

Python layout: `struct.Struct('<4sBBHQQIHBBQQQIII12fHHBBHI')`.

| Offset | Type | Meaning |
| ---: | --- | --- |
| 0 | 4 bytes | `NVLK` |
| 4 | u8 | Wire version 1 |
| 5 | u8 | Message type 2 |
| 6 | u16 | Length 128 |
| 8 | u64 | Random nonzero session, changed on each Start |
| 16 | u64 | Nonzero saved mount-calibration identity; changes when calibration changes |
| 24 | u32 | Emission sequence, increasing within session |
| 28 | u16 | Flags: bit 0 last frame interval valid; bit 1 mount calibration supplied; bit 2 cumulative segment valid. Other bits zero |
| 30 | u8 | State: 0 unavailable, 1 limited, 2 tracking, 3 interrupted |
| 31 | u8 | Reason: 0 none, 1 initializing/focusing, 2 excessive motion, 3 tilt/IMU/timestamp invalid, 4 stale/missing frame or frame gap, 5 capture interruption/error, 6 Vision failure, 7 insufficient texture/agreement |
| 32 | u64 | Last accepted frame interval start, phone uptime microseconds; zero before first accepted interval |
| 40 | u64 | Last accepted frame interval end, same clock; zero before first accepted interval |
| 48 | u64 | Packet assembly uptime microseconds |
| 56 | u32 | Continuity segment, increments on a break after a valid segment |
| 60 | u32 | Session accepted-frame count, saturating |
| 64 | u32 | Session rejected-frame count, saturating; heartbeat failures are excluded |
| 68 | 3 × f32 | Cumulative segment X/Y in mm and unwrapped yaw in radians |
| 80 | 3 × f32 | Last frame interval forward/left displacement in mm and yaw increment in radians |
| 92 | f32 | Translation-fit RMS residual in mm; diagnostic, not statistical uncertainty |
| 96 | f32 | Configured camera lens height above floor, mm |
| 100 | f32 | Segment path length, sum of accepted robot-center translation magnitudes, mm |
| 104 | f32 | Segment sum of accepted interval durations, seconds |
| 108 | 2 × f32 | Last frame interval forward/left speed in mm/s |
| 116 | u16 | Translation-fit inliers |
| 118 | u16 | Candidate translation samples passing image/geometric checks |
| 120 | u8 | Battery percent, 0–100 or 255 unknown |
| 121 | u8 | Battery state: 0 unknown, 1 unplugged, 2 charging, 3 full |
| 122 | u16 | Reserved, zero |
| 124 | u32 | Last accepted frame's processing duration, microseconds |

Forward is robot +X, left is robot +Y, yaw is positive left/counterclockwise viewed from above. Frame deltas are expressed in the robot axes at the interval start. Cumulative X/Y are expressed in the robot axes at the beginning of the continuous segment. They are composed as `p_next = p + R(yaw) delta`, `yaw_next = yaw + deltaYaw`. Translation has already been corrected from lens to robot center using the supplied mount offset. Consumers must not apply that correction again.

Flags 0 and 2 require bit 1. A valid interval has flags 7, state 2, reason 0, nonzero increasing start/end, a duration at most 150 ms, capture age at assembly at most 250 ms, at least 24 inliers, and positive accumulated valid duration. Unknown/reserved encodings are rejected. A supplied calibration means measured mount parameters were entered; it does not certify tracking accuracy or room alignment.

On tracking loss, cumulative values reset, flags 0/2 clear, and continuity increments if the previous segment was valid. Initial failures do not continually advance continuity. Invalid packets retain the last accepted capture timestamps for diagnostics, so an old timestamp must never be interpreted as a new zero-motion sample. A new valid segment starts from zero before its first accepted increment. Sequence and continuity exhaustion create a fresh session before reuse. Starts/restarts reset all accumulation. Accepted/rejected counts are session totals; path and duration are segment totals.

A sender repeats the latest snapshot at each emission tick without changing its capture timestamps. Last-frame deltas are diagnostics, not a command to add that delta once per datagram. To tolerate packet loss, a consumer differences cumulative transforms from two fresh snapshots with the same session, calibration and continuity:

```
delta_translation = R(-previous_yaw) * (current_position - previous_position)
delta_yaw = current_yaw - previous_yaw
```

Duplicate/reordered emissions and repeated capture end times contribute no new motion. A continuity, calibration or session change establishes a new baseline; never bridge it. A missed invalid datagram is still detectable by the continuity change in the next valid datagram. Lost visual intervals cannot be recovered from tallies. No acknowledgement/retry is needed for motion snapshots.

The Pi receiver retains type 1 and type 2 unchanged in the existing `NVLLOG1` log, since both payloads remain 128 bytes. CSV export adds `type` and relative-motion columns, leaving inapplicable values empty. Older exporters cannot decode type 2. The existing AR pose snapshot and optional position aider remain separate; `latest_ground_observation()` returns an ordered GroundHog snapshot and, when possible, `recovered_delta` between received cumulative snapshots. The first snapshot only establishes a baseline. Consumers must also deduplicate snapshot reads. Recovered deltas remain telemetry and are not automatically fused into navigation.

Capture timestamps, Core Motion and packet assembly are checked against phone uptime. Pi receive monotonic time is recorded separately; there is no phone/Pi synchronization or bounded capture freshness at the Pi. Arrival time alone does not prove a packet is fresh. Geometry, flow processing and tally composition stay on the phone.


## GroundHog sensor/health heartbeat (3.1 build 2, wire v1/type 3)

A separate 128-byte type-3 packet runs at 10 Hz independently of capture/Vision, with an additional immediate best-effort emission at impact onset. Types 1/2 and the `NVLLOG1` log container remain unchanged. Total nominal application payload for types 2+3 is 2.56 KB/s, plus occasional impact emissions. Update the Pi receiver/exporter before using type 3.

Python layout: `struct.Struct('<4sBBHQQIHBBQQQIHBB12fQHHI')`.

| Offset | Type | Meaning |
| ---: | --- | --- |
| 0 | 4 bytes | `NVLK` |
| 4 | u8 | Wire version 1 |
| 5 | u8 | Message type 3 |
| 6 | u16 | Length 128 |
| 8 | u64 | Nonzero tracking session token at Start |
| 16 | u64 | Nonzero mount calibration token |
| 24 | u32 | Independent health emission sequence |
| 28 | u16 | Health validity flags below |
| 30 | u8 | Thermal state: 0 nominal, 1 fair, 2 serious, 3 critical, 255 unknown |
| 31 | u8 | Battery state: 0 unknown, 1 unplugged, 2 charging, 3 full |
| 32 | u64 | Health packet assembly uptime, microseconds |
| 40 | u64 | Latest Core Motion uptime, microseconds, zero if absent |
| 48 | u64 | Latest impact-candidate onset uptime, microseconds, zero if none |
| 56 | u32 | Cumulative impact episode count since Start, saturating |
| 60 | u16 | IMU samples since previous health emission, saturating |
| 62 | u8 | Battery percent 0–100, or 255 unknown |
| 63 | u8 | Reserved zero |
| 64 | 3 × f32 | Latest user acceleration in native device X/Y/Z, mm/s² |
| 76 | 3 × f32 | Latest angular rate in native device X/Y/Z, rad/s |
| 88 | 3 × f32 | Latest gravity vector in native device X/Y/Z, g |
| 100 | f32 | Peak user-acceleration magnitude since previous health emission, mm/s² |
| 104 | f32 | Latest episode peak magnitude in its first 150 ms, mm/s² |
| 108 | f32 | Own-process CPU percent, 100% = one full CPU core; may exceed 100% |
| 112 | u64 | Own-process physical memory footprint, bytes |
| 120 | u16 | Actual delivered camera buffer width, pixels; zero if unknown |
| 122 | u16 | Actual delivered camera buffer height, pixels; zero if unknown |
| 124 | u32 | Age of CPU/memory sampling attempt at assembly, ms; 0xffffffff if unavailable |

Flags: bit 0 latest IMU usable (age ≤100 ms); bit 1 interval peak/sample count valid; bit 2 app CPU valid; bit 3 app memory valid; bit 4 latest impact episode exists; bit 5 battery percentage known; bit 6 actual image dimensions known. Bits 7–15 are reserved zero. Measurement values with clear flags may retain diagnostic history and must not be treated as current observations. All floats must be finite. Impact count/time/peak and their bit agree; absent impacts have zero values. CPU/memory validity requires resource age ≤2000 ms. Battery, dimension and interval count validity must agree with their fields.

Native device X points toward the phone's right edge, Y toward its top, Z out of its screen. In this screen-up mount, gravity is approximately (0,0,-1). Unlike type-2 translation, acceleration/angular-rate vectors are not converted to robot axes or corrected to robot center. They include rotation's lever-arm effects at the phone. They must not be interpreted as a measured collision direction or contact location. Gravity permits consumers to derive tilt if desired.

Impact inference uses gravity-separated acceleration and jerk with provisional thresholds, warmup and quiet/cooldown rearming; see [GroundHog detector details](../ios-app/GroundHog/README.md). A candidate is an observed jolt after contact or other disturbance, not proximity sensing or verified contact. It cannot guarantee phone protection. No automatic navigation or motor policy consumes these packets in this change.

The most recent event count, onset and episode peak are repeated in every later heartbeat. A receiver differences counts only within the same health session/calibration and increasing sequence. Missing event datagrams are recoverable from later counts. If multiple events were missed, the count recovers their number, but only the newest onset/peak is available. Repeated counts are not new impacts. A new session establishes a baseline. `latest_health_observation()` is independent of AR pose/ground motion and exposes `new_bumps`; callers must also deduplicate sequence reads. Logs retain raw duplicates/reordering for analysis.

CPU and memory are app-local, sampled about once per second, and do not describe device-wide load or GPU utilization. CPU is unavailable until a second successful counter reading. Battery repeats cached UIKit readings refreshed once per second. Thermal state is a categorical Foundation reading. Camera dimensions are cached from actual output buffers, and do not certify that frames are currently arriving. The configured VGA preset is normally delivered as 480×640 portrait at a requested 30 fps; actual FPS is not encoded here.

Health transmission does not wait for optical-flow processing. The shared UDP sender prioritizes the newest pending health record, with at most one pending record per message type and no stale backlog. This is best-effort telemetry, not an acknowledged safety channel. Sensor and packet timestamps use phone uptime; no synchronized Pi clock is claimed. Receiver arrival time alone cannot bound capture/event age. Stopping/backgrounding stops this heartbeat as well as capture.


## GroundHog compass heartbeat (3.1 build 3, wire v1/type 4)

Core Location supplies magnetic compass observations separately from gyro-relative odometry. Type 4 is a 128-byte packet emitted once per second, including when heading is unsupported, unreliable or stale. It uses the same Start session/calibration identity, its own emission sequence, and the same receiver/log container. Existing message types are unchanged. Python format: `struct.Struct('<4sBBHQQIHBBQQ8fQ40s')`.

| Offset | Type | Meaning |
| ---: | --- | --- |
| 0 | 4 bytes | `NVLK` |
| 4 | u8 | Wire version 1 |
| 5 | u8 | Message type 4 |
| 6 | u16 | Length 128 |
| 8 | u64 | Nonzero session token |
| 16 | u64 | Nonzero mount calibration identity |
| 24 | u32 | Compass emission sequence |
| 28 | u16 | Bit 0 phone magnetic bearing usable; bit 1 device field vector fresh/finite; bit 2 mount-corrected robot magnetic bearing usable; other bits zero |
| 30 | u8 | State: 0 unsupported, 1 acquiring, 2 usable, 3 unreliable, 4 stale, 5 error |
| 31 | u8 | Reserved zero |
| 32 | u64 | Assembly uptime, microseconds |
| 40 | u64 | Estimated heading sample uptime, microseconds; zero if absent/error |
| 48 | f32 | Phone top-edge magnetic bearing, radians clockwise from magnetic north |
| 52 | f32 | Robot-forward magnetic bearing, radians clockwise from magnetic north |
| 56 | f32 | Apple-reported heading accuracy in radians; negative means invalid |
| 60 | 3 × f32 | Device-axis magnetic field X/Y/Z, microteslas |
| 72 | f32 | Field magnitude, microteslas |
| 76 | f32 | Supplied mount yaw, radians counterclockwise from robot forward to phone top |
| 80 | u64 | Original Core Location sample wall-clock timestamp, Unix microseconds; zero if absent/error |
| 88 | 40 bytes | Reserved zeros |

Phone/robot bearings are north-referenced **clockwise**, not type-2 positive-left yaw or room-aligned heading. Robot bearing is `wrap_2pi(phone_bearing + mount_yaw)`. The mount conversion is already applied. Raw field vectors retain native device axes. Bits 0/2 are set together only with state 2, sample age ≤1 second, and reported accuracy between 0 and 20° inclusive. Bit 1 can remain set with state 3 to record the field despite unreliable heading. States 0/1/4/5 have no validity bits. Invalid measurements may retain finite diagnostic values. Zero bearing is a real north reading only when its validity bit is set. A small float32 rounding tolerance is allowed at angular bounds.

Core Location's heading timestamps are wall-clock Dates. The sender estimates sample uptime from callback uptime minus the observed wall-clock sample age, and retains the source Unix timestamp separately. Negative age, samples older than one second, and callbacks predating the current Start are discarded. Wall-clock anomalies can invalidate compass observations; these timestamps do not establish synchronized Pi capture time. Repeated heartbeats retain the source timestamp and become stale rather than acquiring a new apparent capture time.

The sender uses heading updates only: no GPS/location updates, authorization request or true-north bearing. Hardware availability, bad accuracy and errors are explicit. Calibration overlays are suppressed on the mounted phone. Magnetic interference from the robot can bias even apparently accurate readings; validity represents source quality/freshness checks, not surveyed heading accuracy. Compass data is recorded/displayed without changing gyro integration, floor odometry, navigation or motor control.

`latest_compass_observation()` provides a separate ordered snapshot; duplicate/reordered sequences and retired sessions are excluded from that snapshot while raw logs retain them. CSV includes named compass columns and excludes reserved padding. The UDP sender retains one latest compass packet in addition to one health and one motion packet. Health has first priority, followed by motion and compass; stale pending snapshots are discarded. Consumers must qualify freshness and deduplicate reads before any future use.
