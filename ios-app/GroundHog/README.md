<!-- @(#)README.md 3.1.docs.1 2026/10/31 14:00:00 -->
# GroundHog 3.1

GroundHog measures robot-relative motion from a downward-facing iPhone rear camera. It uses AVFoundation, Vision revision-1 optical flow, Core Motion and Network.framework, without ARKit. It is a separate app (`com.preusslabs.GroundHog`); StarLock remains available. Deployment target: iOS 15.0, including the 2016 SE on iOS 15.8. The supplied `../GroundHog.png` is preserved; the app catalog contains a generated opaque 1024-pixel copy.

[Mount measurement diagram](docs/mount-measurements.svg) · [PNG version](docs/mount-measurements.png)

## Build and run

Open `GroundHog.xcodeproj`, select the shared GroundHog scheme and Peters SE, then build/run. Signing uses the existing project's development team; select your own team if necessary. The command-line unsigned device build is:

```sh
xcodebuild -project ios-app/GroundHog/GroundHog.xcodeproj -scheme GroundHog \
  -sdk iphoneos -configuration Debug -derivedDataPath /tmp/GroundHog-build \
  CODE_SIGNING_ALLOWED=NO build
```

Mount the phone with screen up and rear camera down, approximately parallel to the floor (within 10°). The lens must see unobstructed floor texture and focus at its working distance. Do not reuse the old mount measurements without checking them.

Enter four measured values, then tap Start tracking:

- Lens height above the floor, in mm (50–1500).
- Phone top-edge direction relative to robot forward: 0° forward, +90° left, ±180° backward.
- Lens offset from the robot center, positive forward, in mm.
- Lens offset from the robot center, positive left, in mm.

Calibration is saved locally, with a new random calibration identity whenever its values change. No assumed lens height or old mount offset is silently enabled. Camera and local-network permission are required. Allow Motion access if requested. After a system permission prompt, tap Start again if tracking has not begun.

The app stays awake while tracking. Stop, screen lock, loss of foreground, or restart ends capture/transmission. Foreground return requires an explicit Start and creates a new session. The screen reports segment X/Y/yaw, accepted/rejected frame counts, fit residual and UDP send status. UDP completion does not prove Pi reception. Confirm a growing NavLink log on the Pi. No Pi deployment or motor commands are performed by building this app.

## Estimator

Capture requests VGA at 30 fps when supported, with a fixed portrait pixel orientation and stabilization disabled. One-shot near-range autofocus runs at Start; its first second and focus-adjustment frames are excluded. Intrinsics come from per-frame AVFoundation attachments when available and consistent with the delivered frame. The fallback estimates centered pinhole intrinsics from the active format's horizontal field of view, scaled to portrait output. This fallback needs a measured-distance scale check. No lens-distortion calibration is claimed; the estimator samples the central 75% of the image.

Core Motion runs at a requested 100 Hz independently of the image-processing queue. Buffered gravity-projected gyro rates supply yaw at camera timestamps, with bounded nearest-sample extrapolation (25 ms) and IMU-gap rejection. This is gyro-relative heading without magnetic correction. Gravity levels image rays; known camera height intersects rays with the floor plane. Consecutive ray intersections, compensated for yaw, yield camera translation. Mount yaw converts this to forward/left; the change in the rotated lens offset removes the camera's arc about the robot center.

Only one low-accuracy classical Vision optical-flow request exists at a time. Capture discards late frames rather than building a processing queue. Sampled flow must pass texture, brightness-match, bounds and four-quadrant coverage checks. A robust median/inlier fit requires at least 24 samples, at least 65% agreement, and RMS residual at most 2 mm. Frames older than 250 ms, intervals longer than 150 ms, tilt over 10°, missing IMU, excessive speed/turn rate and failed fits invalidate tracking. The fit residual is an internal consistency diagnostic, **not calibrated measurement uncertainty**; repeating textures can still fool the estimator.

At 10 Hz, NavLink carries the latest frame delta plus an SE(2) cumulative transform, path length and accepted duration for the continuous segment. Translation is composed with rotation rather than simply summing body-frame distances. Failed observation breaks continuity and resets the transform. Transport loss does not reset it. Repeated frame snapshots retain the original timestamps and tallies.

The initial implementation is for recording and validation. Throughput on the SE and metric accuracy on the actual floors remain unmeasured. Heavy optical-flow processing may result in invalid/stale packets rather than usable odometry. Height changes, glossy/blank/repeating floor surfaces, rolling shutter, lighting changes and motion blur can degrade accuracy. Camera height error directly scales movement error. Neither local X/Y nor integrated yaw is an absolute room fix.

## Pi support and verification

The extended `roomberry_navlink.py` receiver accepts StarLock type 1 and GroundHog type 2 in the same 128-byte datagram / 144-byte log record format. CSV export includes named GroundHog columns and a `type` discriminator. `latest_ground_observation()` is separate from pose aiding: GroundHog data cannot enter the existing ARKit position corrector. It exposes a recovered transform delta between fresh snapshots in the same continuous segment, tolerating missed UDP packets. The first received snapshot is a baseline. A consumer must deduplicate by session/sequence and perform its own freshness/qualification before navigation use.

From the repository root:

```sh
env PYTHONPATH=roomberry:roomberry/irobot/tests .venv/bin/python -m unittest \
  roomberry_compass_test roomberry_health_test roomberry_groundhog_test roomberry_navlink_test roomberry_phone_position_test
```

On macOS these tests compile the actual Swift serializer/geometry and compare wire bytes with Python. A separate synthetic Vision test verifies image-flow sign and row direction with a known +8/+4 pixel translation. UDP tests cover mixed log/export, reordered/repeated frames, dropped packets, rotated transform recovery, tracking loss and session changes. Mac tests need local UDP sockets and access to image-buffer/GPU services.

Before using motion for navigation, record stationary jitter, measured forward/reverse travel, pure pivots, deliberate wheel slip and floor transitions. Verify forward/left signs and yaw sign, distance scale, center translation near zero in pivots, and continuity changes during occlusion/lift/blank-floor tests. Repeat over sustained runs to measure SE throughput, thermal behavior, battery drain and invalid intervals. AprilTags remain the source of absolute correction.


## Impact and phone health telemetry (3.1 build 2)

The reported rear extension reaches 195 mm from the Roomba center and sits 85 mm above the floor; focus is working at this mount height. The 195 mm dimension describes exposed phone reach, **not necessarily the lens location**. It must not silently replace the lens offset calibration. Enter 85 mm as lens height only if measured at the lens. Existing saved calibration is preserved. These dimensions also do not change the robot's collision footprint automatically.

GroundHog retains VGA capture: nominal 640×480 at a requested 30 fps. Portrait output is normally 480×640. The health screen and packets report actual delivered width and height, including while visual tracking is invalid; the displayed fps is explicitly a target, not measured throughput.

A dedicated health queue and 10 Hz timer run independently of the Vision/capture queue, using the existing requested 100 Hz Core Motion device-motion stream. Each type-3 NavLink packet contains:

- Latest native-device user acceleration (gravity removed, mm/s²), angular velocity (rad/s), and gravity direction (g), with a sensor timestamp and freshness bit.
- Peak acceleration magnitude over received IMU samples since the previous health emission, plus sample count. Slow sustained acceleration and rotational lever-arm acceleration remain in these device-axis measurements.
- Cumulative impact-like episode count, last event timestamp, and peak acceleration in the first 150 ms of the latest episode. Counts survive visual tracking breaks and repeated heartbeats recover event notifications after UDP loss.
- Cached battery percentage/charging state, actual image dimensions, app CPU use, app physical memory footprint and system thermal state.

An impact triggers an immediate best-effort health emission. The transport holds at most one latest motion packet and one latest health packet, prioritizing health for the next send and discarding stale pending snapshots. No receipt or guaranteed stop latency is claimed. Health continues when optical flow is slow or loses its lock, and stops when tracking is stopped/backgrounded. UIKit battery polling remains once per second. Bump counts reset on Start.

The initial detector uses gravity-free acceleration magnitude and vector jerk. A candidate occurs at 0.6 g with at least 15 g/s jerk, at 1.2 g regardless of jerk, or at 0.25 g with at least 40 g/s jerk. It excludes the first 300 ms after initialization or an IMU gap over 30 ms, ignores reordered/invalid samples, and groups ringing into an episode. It rearms only after at least 80 ms below 0.15 g and 300 ms since the previous onset. These are provisional thresholds in `BumpDetector`, to tune from on-robot logs. The event is an **impact candidate**, not proof that the exposed phone hit something. Floor joints, chassis bumps and mount vibration may trigger it; gentle/sustained contact and short impulses between samples may be missed. It cannot detect obstacles before contact. No automatic motor response is introduced.

CPU and memory are sampled once per second using Mach `task_info` for this app's own task. CPU uses the difference in cumulative user+system absolute CPU time divided by wall-clock absolute time: 100% means one core fully occupied, so multicore use can exceed 100%. It is not device-wide CPU utilization, and GPU/other-process work is excluded. The first CPU sample establishes a baseline. Memory is `TASK_VM_INFO.phys_footprint`, in bytes, not the phone's total/free RAM. Failures clear the corresponding validity bit. Thermal state comes from Foundation; no unsupported temperature or device-wide usage API is used. Capture metrics and memory describe this app's process and do not include every camera/Vision service allocation.

The receiver records type 3 with types 1/2 in the same binary log and exports named health columns. `latest_health_observation()` has its own sequence/session ordering and `new_bumps` difference; the first received snapshot establishes a baseline. A consumer must deduplicate snapshot reads and qualify freshness. The receiver does not feed impacts or health data into navigation or motor control.

Synthetic tests exercise impulse detection, ring suppression, quiet rearming, smooth acceleration, gaps, invalid/reordered samples, actual own-process counters, Swift/Python wire equivalence, and mixed UDP/CSV plus lost/reordered impact packets. Actual sensitivity and false-positive rate still need controlled stationary taps and slow supervised floor/turn trials, without deliberately striking obstacles.

Apple references: [CMDeviceMotion](https://developer.apple.com/documentation/coremotion/cmdevicemotion) and [ProcessInfo thermal state](https://developer.apple.com/documentation/foundation/processinfo/thermalstate-swift.property). Mach task layouts are provided by the installed Apple SDK's `mach/task_info.h`.


## Magnetic compass (3.1 build 3)

Core Location heading updates now provide phone and mount-corrected robot magnetic bearings, Apple-reported angular accuracy, device-axis magnetic field X/Y/Z and field magnitude in microteslas. The app displays robot bearing and accuracy; a separate fixed-size type-4 NavLink heartbeat sends the latest compass snapshot once per second, including explicit unsupported/acquiring/unreliable/stale/error states. The existing type-3 health packet and other wire layouts remain unchanged. Pi recording, mixed CSV export and `latest_compass_observation()` support type 4 independently of navigation.

Compass bearings are **clockwise from magnetic north**, unlike the positive-left yaw increments in odometry. Portrait orientation fixes the reference to the phone's top edge. Robot bearing is `wrap(phone bearing + mount yaw)` because mount yaw describes the phone top direction counterclockwise from robot forward. The packet includes the mount yaw and calibration identity to make this convention explicit. It does not replace gyro-relative yaw or alter optical-flow rotation compensation.

A heading is marked usable only if the source sample is at most one second old and Apple reports a nonnegative accuracy no worse than 20°. Raw field data has a separate validity bit. Poor-accuracy readings remain diagnostic; stale readings clear all validity. A good reported accuracy does not prove freedom from magnetic bias. Roomba motors, wiring, steel, magnets and nearby furniture may distort magnetic bearings. Compare readings with motors stopped and running before using them for anything beyond logging. No automatic heading correction is implemented.

Only `startUpdatingHeading()` is used. No GPS/location updates, true-north calculation or location-authorization request is introduced. Compass lifecycle follows tracking Start/Stop/background behavior. Automatic calibration overlays are suppressed while mounted; invalid accuracy is reported instead of asking the user to swing the attached phone around. Heading's original wall-clock timestamp is retained, and an estimated phone-uptime timestamp is formed from its age at callback receipt. Negative ages, old samples and old-session callbacks are rejected; wall-clock changes may temporarily invalidate readings. No synchronized Pi timestamp is claimed.

Tests include byte-for-byte Swift/Python type-4 serialization, mount-angle sign/wrap, accuracy and freshness rejection, unsupported/error representation, ordered sessions and mixed four-type UDP logs/CSV. On-phone magnetic accuracy and distortion remain to be measured.

Apple references: [CLHeading](https://developer.apple.com/documentation/corelocation/clheading), [magnetic heading](https://developer.apple.com/documentation/corelocation/clheading/magneticheading) and [heading updates](https://developer.apple.com/documentation/corelocation/cllocationmanager/startupdatingheading()).
