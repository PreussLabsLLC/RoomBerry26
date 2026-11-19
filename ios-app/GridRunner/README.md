<!-- @(#)README.md 3.2.gridauto.1 2026/11/14 09:15:00 -->
# GridRunner

Independent iOS 15+ app for following one straight dark grout line. GroundHog's
app, defaults, bundle identifier and camera pipeline remain unchanged. This
project compiles existing GroundHog geometry and phone-health helpers directly.
No OpenCV dependency is included. A transverse-grout crossing counter observes
and logs tile boundaries; it does not steer or stop the robot.

## First run

1. Build the GridRunner scheme in `GridRunner.xcodeproj`, select the signing
   account/device and install it alongside GroundHog. Update/restart the Pi
   Roomberry service with this checkout before using the new mode.
2. Mount the rear camera down, screen up. Defaults are height 85 mm, yaw 180°,
   lens forward −200 mm, lens left **your measured lens-left offset** (positive for a rear-left camera; +26 mm if measured). These are GridRunner's own
   settings; confirm the actual mount before running.
3. Align Rosie at tag 15, facing it, with the phone camera directly over the longitudinal grout line. Choose
   **Reverse** and start the camera stream. Yellow marks sampled rows, green
   marks accepted centers, cyan marks the camera-center target. The white
   dashed row and two vertical guides show the tile-crossing detector; orange
   marks a detected transverse grout band and flashes green when a crossing is
   counted. Check line lock.
4. Press Rosie's **Clock** button or web **Start grout out-and-back**. Pi build
   **3.1.grout.8** reverses at 50 mm/s, slows to 30 mm/s through fresh line-loss
   observations, and restores speed after stable reacquisition. A new phone
   bump brakes the outbound leg; a 5000 mm cap remains. Clock again cancels.
5. After the bump, the Pi holds one second and returns forward automatically.
   **Leave the phone direction on Reverse.** Pi tag-15 scans at estimated
   center-to-tag distances 2, 1.5, 1 and 0.5 m adjust the approach. A reliable
   final scan is required before creeping into front-bumper contact at tag 15.
6. STOP in the app, backgrounding, stale telemetry, camera errors, hazards and
   unexpected contacts abort. New phone impacts during return abort. Simple
   fresh line loss permits bounded slow continuation, not indefinite travel.

Details, safety bounds, version check and logging:
[Pi grout mission](../../roomberry/docs/grout-run-controls.md).

UDP delivery is unconfirmed: app streaming status does not confirm Pi receipt
or robot motion. The normal Roomba safety stops remain active. Calibration is
still available through the web Calibrate command; Clock cancels an active
calibration, but its next press starts GridRunner.

## Detection and steering

The camera supplies 480×640 luma images. Two horizontal scanlines near 35% and
65% image height find narrow dark runs against a light local background. Each
row may shift ±24 pixels to avoid a transverse grout stripe. Ambiguous pairs,
weak contrast, excessive line angle, old frames or excessive phone tilt are
rejected. This keeps a transverse stripe from breaking line tracking; the
separate counter below records such stripes.

Camera intrinsics, gravity, height, yaw and lens offsets project the detected
centers onto the floor. The measured lateral mount offset is included before estimating robot-relative
offset and angle. Positive offset means robot-left. The tracking target is a
parallel line through the camera, so its desired robot-relative offset equals
`lensLeftMM`, rather than zero. The mount measurement itself is unchanged.
The dimensionless wheel correction is:

```
correction = clamp(gain * ((offset_mm - lens_left_mm) / 600 + direction * angle_rad), ±limit)
left  = velocity * (1 - correction)
right = velocity * (1 + correction)
```

Direction is +1 forward, −1 reverse. Velocity includes that sign: lateral
error and heading error therefore have the required distinct reverse
polarities. Default gain is 2 and limit 0.25; the app exposes both. The Pi doubles
the effective gain, retaining the phone limit. Pi hard
limit is 0.35. Settings cannot change while streaming; changes require rearm.
These gains require physical floor validation.

## Tile crossings (phase 3)

Each transverse grout line is treated as a one-tile landmark. Two vertical
strips at 22% and 78% of image width are sampled either side of the tracked
longitudinal line, keeping clear of the centre line and the LED corona. Per-row
medians suppress specular pixels; each strip is compared with a local
bright-tile background. Each strip must contain a dark run of 3–64 pixels with
enough local contrast, and the two run centres must be close enough to allow a
few degrees of robot yaw. One-sided texture, reflections, low contrast and
ambiguous double bands are rejected.

A small state machine counts the band when it passes a fixed reference row at
50% image height. It requires two consecutive approach frames, interpolates the
crossing time between bracketing frames, and then waits until the band clears
the row for two frames plus a 1.5 s minimum before accepting another. Motion is
observed from the band's own movement, not from the app's Reverse/Forward
setting, so the return leg is counted even though the selector stays on Reverse.
No crossing commands steering, speed or a stop.

The status panel shows `Tiles N · last interval X s`. The iOS console logs one
line per crossing:

```
GridRunner tile crossing count=7 time=... y=0.5012 confidence=0.98 interval=3.06
```

and includes `tiles=N` on every periodic sample.

The 28 reserved type-5 trailer bytes now carry the crossing state, so the Pi
can record every tile itself:

```
UInt8 magic 0xC7 · UInt8 version 1 · UInt16 flags (bit 0 = band valid)
UInt32 count · UInt64 last-crossing uptime us
Float32 band row · Float32 confidence · Float32 last interval seconds
```

A legacy app still sending 28 zero bytes remains decodable and produces no
crossings. The Pi logs one JSON record per new count:

```
GridRunner crossing: {"count": 7, "crossing_us": ..., "interval_s": 3.06,
  "stage": "driving", "wheel_distance_mm": -2140.2, ...}
```

The persistent record is the NavLink binary log (all type-5 packets) and its
CSV export, which now includes the crossing columns. A skipped count is logged
with `missed=N` rather than inventing a crossing time.

## Stops and logging

Arming waits up to 10 seconds for a fresh line and matching health. Only explicit
fresh line-loss observations permit slow travel: outbound allowance 30 s or
750 mm; total mission 600 s. Stale frames/health and stopped/camera/IMU states
abort. The 600 ms I/O motor lease stays active while moving and is ended for
stationary turnaround/checkpoint scans. A missing final tag fix or absent
bumper beyond the final approach bound aborts. Other existing safety guards
remain. See the Pi mission document for exact limits.

The iOS console logs scan positions, errors, confidence and requested
correction. Pi `GridRunner sample` records include those values and commanded
wheel velocities. Existing NavLink binary logs include all type-5 packets;
CSV export includes their fields.

## NavLink type 5

UDP uses the saved Mothership host (default `pi3.local`) on port5010;
a bare hostname also tries its `.local` alternative. Logging is unchanged.
Every packet is 128 bytes, little endian, Python layout
`<4sBBHQQIHbBQQ12fHHBBHIQfff`:

- `NVLK`, version 1, type 5, length 128; session/configuration UInt64 IDs;
  UInt32 sequence; UInt16 flags; signed Int8 direction; UInt8 reason.
- UInt64 frame/send uptime microseconds.
- Twelve Float32 values: scan1 x/y, scan2 x/y (normalized portrait image),
  offset mm, line angle radians, confidence, correction, gain, correction
  limit, lens left mm, camera height mm.
- UInt16 image width/height.
- 28-byte tile-crossing trailer: UInt8 magic `0xC7`, UInt8 version `1`,
  UInt16 flags (bit 0 band valid), UInt32 count, UInt64 last-crossing uptime
  microseconds, Float32 band row, Float32 confidence, Float32 last interval
  seconds. An all-zero trailer is accepted as the legacy pre-crossing format.

Flags: bit 0 valid line, bit 1 streaming requested. Valid running is 3;
invalid running is 2; explicit stop is 0. Reasons: 0 valid, 1 lost line,
2 stale frame, 3 stopped, 4 startup, 5 invalid motion/tilt/frame, 6 camera.
Invalid observations request zero correction. Pi validates fields and
recomputes correction; UDP callbacks never command motors directly.

## Validation

`roomberry_gridrunner_test.py` exercises packet validation, logging/export,
ordering, safety/timeout transitions and forward/reverse polarity. It compiles
and runs `tests/GridLineCheck.swift` against synthetic floor images and decodes
the Swift packet in Python, including the crossing trailer. `tests/GridCrossingCheck.swift` compiles the real
detector and state machine and checks moving/reverse bands, stationary jitter,
reversal, one-sided texture, misaligned strips, low contrast, LED corona and a
15-tile sequence. Control tests cover motor-lease expiry independently
of the mission thread. Build with:

```
xcodebuild -project ios-app/GridRunner/GridRunner.xcodeproj -scheme GridRunner \
  -sdk iphoneos -configuration Release CODE_SIGNING_ALLOWED=NO build
```

Physical line following and on-device overlay alignment remain to be checked.


## Camera-centered target and preview

Pi build 3.1.grout.8 follows a parallel line through the camera's lateral mount
position. With a lens-left value of +26 mm, align the robot center 26 mm to the
robot's right of the grout and face tag 15. Keep the physical mount settings
accurate; do not zero them to obtain a centered target. The Pi's initial map
seed and tag-guided return endpoint use the same 26 mm lateral offset. Existing
bumper/heading endpoint tolerances and safety guards remain unchanged.

The phone's cyan target and displayed camera-line error use the same target.
The recorded `offset_mm` remains robot-relative for diagnostics; Pi samples add
`target_offset_mm` and `tracking_error_mm` to distinguish measurement and error.
Version-1 packets advertising the old robot-center correction still decode for
archive compatibility, while the Pi recomputes live camera-centered steering.

The preview image and all overlays rotate **90 degrees clockwise together**.
This is a view transform only: luma frames, intrinsics, camera orientation,
phone/robot geometry, packet coordinates and the 180-degree physical top-edge
setting retain their existing coordinate conventions. Rebuild/install GridRunner
for the updated overlay and preview; deploy/restart the Pi for the new target.


## Recovering from another position (Pi 3.1.grout.10)

The web **Return to tag 15** command starts standalone homing from the current
position and mission state, including after an interrupted outbound or OI
restart. It no longer requires a threshold event or phone stream. The Pi stops,
localizes from mapped tags (or an intact saved pose), plans a clear route, aims
at tag 15 and verifies the final approach. If position is unknown it searches
stationary views using bounded in-place turns, without translating blindly.
Safety stops remain explicit: put the robot down and press **Restart OI** after
wheel drop, then wait for Sensors Ready. No new iOS installation is needed.


## Stepped tag-15 distance survey (3.2.grid.1 / app build 8)

Use the current Python dashboard's **Tag 15 · stepped distance calibration**
panel. Clock starts WALL when idle on current Pi builds; it cancels a survey
rather than advancing it. The older continuous grout run remains a separate
button. This mode never returns automatically or changes camera calibration.

1. Install GridRunner build 8 and update the Pi service with this checkout.
   Place the shared NavLink key in GridRunner's own Documents/NavLink.key
   through Finder file sharing, then relaunch GridRunner (RoomTrek's app container is separate). The
   existing Pi authenticated relay/key configuration must be enabled. Keep
   other phone telemetry apps stopped during this run.
2. Set Mothership to `pi3.local` (or the Pi hostname/IP), mount/align as usual,
   face tag 15, and start the stream in Reverse. Verify
   line lock, fresh IMU and **authenticated Pi reply received**. Acceleration
   (mm/s²), gyro XYZ (rad/s), gravity and impact counts are sent at 10 Hz in
   existing type-3 health packets; compass type 4 is now also forwarded.
   These are phone-frame readings; gyro is not absolute heading. No ARKit
   motion/position is fabricated. Existing type-5 line/crossing data is unchanged.
3. Start about one measured grout pitch from tag 15. Enter the initial tape
   distance and actual grout pitch in mm, then **Start tag-15 distance run**.
   It settles for one second and scans in place. Wait for scan completion and
   refresh status. Camera range is lens-to-tag-centre straight-line range:
   measure the same endpoints, not bumper/axle clearance. If measuring floor
   distance instead, preserve that distinction when analyzing the raw depth
   and translation vector; range and optical-axis depth are different quantities.
4. At each stopped station enter the tape measurement and press **Record tape
   measurement (no motion)**. The table shows camera-minus-tape error, including
   percentage. Then press **Reverse to next grout / one tile**. It follows the
   line at 70 mm/s and brakes on the next counted transverse band, or one pitch
   of wheel travel if no crossing is seen. After settling it scans again. The
   crossing reference is under the phone, not the Pi lens; tape every station.
5. A missing/non-clear tag ends further stepping, after the final tape entry.
   Clear means tag16h5 ID15, zero hamming, margin ≥20, pose error ≤5 and finite
   positive range. **Rescan this station** allows a stationary retry and keeps
   earlier evidence. No navigation distance gate or pose fusion affects these
   raw distance observations. There is a 5 m wheel/tape bound, a 20 s step/scan
   timeout and one-hour session timeout. The next step is refused if the last
   tape distance plus one pitch would exceed 5 m. **Stop distance run** ends it.

Station scans and tape entries are JSON records in the normal Pi log, and all
scan images/reports continue through the existing camera archive. The dashboard
status includes the station records. Phone stop/background, stale telemetry,
configuration/session changes, impacts, contact, hazards, odometry reset,
heading deviation >10° or line loss while stepping abort. Physical stopping
precision and the complete floor run still require validation.

GridRunner reuses RoomTrek's signed challenge/response, replay cache and speech
engine. STATUS, SPEAK and SESSION_STOP are supported, with operation results;
other RoomTrek commands fail explicitly. Existing Pi speech and voice-test
controls can address GridRunner while its stream is active. Commands do not
start robot motion. Speech cancels on stop/background/audio interruption.
The control heartbeat is independent of camera packets. Its authenticated
reply indicator expires after six seconds; UDP send counts alone do not prove
Pi receipt. Signing uses the existing NavLink.key and ±30 s clock window.


## Trial fixes (build 9 / Pi 3.2.grid.2)

Build9 includes phone battery percentage/state in signed control heartbeats.
The Pi also accepts valid, fresh, matching-session health battery data from
build8. The web survey route now accepts fractional-mm inputs such as304.8;
the first trial's Start request failed before reaching the coordinator.
Unavailable buttons no longer show the busy cursor. Start checks live Pi state;
Refresh distance status is always available; explicitly requested scans/steps
update their controls until stopped or25s. Tape entry stays editable. Global
refresh remains manual, and no next tile starts automatically.

For close scans, keep glossy tape and reflections off the tag's black border
and white quiet zone. The trial's native detector found4 of11 clear tag15 reads;
an independent offline decoder found the visible tag in all11. This is not a
universal one-tile minimum-range limit. Do not lower quality checks: the6.2m
weak detection in that trial was an unrelated image-edge false positive.
Full evidence: [trial investigation](../../output/grid-distance-investigation-20261113/README.md).


## Tag15 range check correction

The user-selected Pi setting is now1.10× native tag15 metric translation, with
raw pose/range retained. The calibration panel shows raw and corrected camera
ranges and the applied factor. Other tags, phone geometry and steering gains
are unchanged. This is a Pi Python/configuration update; no phone reinstall is
needed. See [ten-percent correction](../../roomberry/docs/tag-range-correction.md)
for deployment and archive field details.


## Final range setting and controlled homing rollup (build10)

The current Pi configuration applies a global1.12× native translation correction
to every tag/family, replacing the earlier tag15-only1.10 setting. Raw and
corrected values remain available. See the current
[range and navigation rollup](../../roomberry/docs/tag-range-correction.md).

Build10 sends type7 attitude/gyro telemetry using the existing Core Motion
stream. The packet and integrator are shared with RoomTrek; rates are100Hz at
source and10Hz on the link. The Pi can therefore use its existing gyro-heading
comparison and guarded heading-nudge path without requiring ARKit. Type3 health
still carries acceleration/gyro/gravity and battery; no position is fabricated.

With the matching Pi update, optional grout guidance stays inside standalone
homing, which continues stopped rescans and slow, validated arrival. It no
longer switches a standalone return into the cruise-speed bumper-ended grout
mission. Brief parked sensor glitches wait up to1s; moving faults still stop.
The survey's first tape entry corrects restart station labels, and Next remains
an explicit operator action. Existing earlier sections describe historical
versions; this rollup governs the new return behavior and global scale.


## Autonomous crossing survey (build 11 / Pi 3.2.gridauto.1)

The distance-run Start command now defaults to autonomous operation. Place Rosie
facing tag 15 and aligned with the longitudinal grout, start GridRunner in Reverse,
and enter the starting lens-to-tag range as a conservative estimate for the 5 m
travel bound. A stationary baseline scan is followed by reverse travel to the next
observed crossing. Each crossing stops the robot, settles for one second and scans
tag 15, then advances without waiting for tape entry. Camera results remain raw
observations and do not change navigation or calibration. Missing/unclear tag 15
ends the survey. Other safety and telemetry guards remain active.

For 304.8 mm tiles and 0.4–0.9 mm grout, use nominal centre-to-centre crossing
pitch **305.45 mm** (range 305.2–305.7 mm). Enter 305.45 in the existing tile-pitch
field, which may still display its historical 304.8 default. The first crossing
can occur anywhere within a pitch; the survey does not label the starting
position as a known crossing or invent absolute tag distances from tile counts.
Records include relative crossing distance only while no crossing has been skipped.
Thin grout detection still requires physical validation; dimensions alone do not
establish the camera's pixel width or detection reliability.

If no crossing is seen by one pitch plus 30 mm of wheel travel, Rosie stops,
moves **forward 50 mm** (back over the area just traversed), then searches again
in reverse at 40 mm/s. Forward-leg counts do not create stations. After two
retries she logs a skipped crossing and continues toward the next crossing;
a missed crossing alone does not terminate the run. The 5 m estimated-range
bound, hazards, stale streams, line loss and motion timeouts still stop motion.
Skipped-crossing counts are search-window estimates, not measured positions.

Remote light control uses the existing authenticated Pi relay, with idempotent
commands and hardware-application acknowledgment:

```sh
python3 roomberry/roomberry_trek_control.py LED_OFF --key-file /path/to/navlink.key
python3 roomberry/roomberry_trek_control.py LED_ON --key-file /path/to/navlink.key
```

GridRunner must be streaming and have its Documents/NavLink.key installed.
STATUS includes `led_requested`; command completion confirms torch mode was
applied. LED failure is reported explicitly. Stop/background still switches it
off. To compare detection, set LED_OFF and run the survey, reposition Rosie at
the same starting view, then set LED_ON and repeat. LED switching is remote;
the survey does not automatically restart or reposition Rosie for a second pass.
Use the same pitch and lighting otherwise and compare crossing skips and scans.

For the historical operator-paced flow send `autonomous=false` on
`grid_distance_start`; tape entry and explicit Next retain their previous behavior.
Pi service update and GridRunner rebuild/install are required. This change does
not deploy either device or start a live robot run.
