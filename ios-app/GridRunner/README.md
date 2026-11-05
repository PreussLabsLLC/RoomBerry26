<!-- @(#)README.md 3.1.grout.8 2026/11/04 12:30:00 -->
# GridRunner

Independent iOS 15+ app for following one straight dark grout line. GroundHog's
app, defaults, bundle identifier and camera pipeline remain unchanged. This
project compiles existing GroundHog geometry and phone-health helpers directly.
No OpenCV dependency or intersection counter is included.

## First run

1. Build the GridRunner scheme in `GridRunner.xcodeproj`, select the signing
   account/device and install it alongside GroundHog. Update/restart the Pi
   Roomberry service with this checkout before using the new mode.
2. Mount the rear camera down, screen up. Defaults are height 85 mm, yaw 180°,
   lens forward −200 mm, lens left **your measured lens-left offset** (positive for a rear-left camera; +26 mm if measured). These are GridRunner's own
   settings; confirm the actual mount before running.
3. Align Rosie at tag 15, facing it, with the phone camera directly over the longitudinal grout line. Choose
   **Reverse** and start the camera stream. Yellow marks sampled rows, green
   marks accepted centers, cyan marks the camera-center target. Check line lock.
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
rejected. This handles a transverse stripe without counting intersections.

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

Existing UDP destination and logging remain unchanged (`pi`/`pi.local`:5010).
Every packet is 128 bytes, little endian, Python layout
`<4sBBHQQIHbBQQ12fHH28s`:

- `NVLK`, version 1, type 5, length 128; session/configuration UInt64 IDs;
  UInt32 sequence; UInt16 flags; signed Int8 direction; UInt8 reason.
- UInt64 frame/send uptime microseconds.
- Twelve Float32 values: scan1 x/y, scan2 x/y (normalized portrait image),
  offset mm, line angle radians, confidence, correction, gain, correction
  limit, lens left mm, camera height mm.
- UInt16 image width/height; 28 zero padding bytes.

Flags: bit 0 valid line, bit 1 streaming requested. Valid running is 3;
invalid running is 2; explicit stop is 0. Reasons: 0 valid, 1 lost line,
2 stale frame, 3 stopped, 4 startup, 5 invalid motion/tilt/frame, 6 camera.
Invalid observations request zero correction. Pi validates fields and
recomputes correction; UDP callbacks never command motors directly.

## Validation

`roomberry_gridrunner_test.py` exercises packet validation, logging/export,
ordering, safety/timeout transitions and forward/reverse polarity. It compiles
and runs `tests/GridLineCheck.swift` against synthetic floor images and decodes
the Swift packet in Python. Control tests cover motor-lease expiry independently
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
