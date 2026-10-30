<!-- @(#)README.md 2.9 2026/10/26 -->
# Roomberry

**Roomberry 26** follows the original roomberry project (Pi Zero W with picam riding on
Roomba 630). The goal here is to evolve the camera rover into a more capable cleaning bot
using the camera and apriltags placed around the house to aid location tracking.

The architecture was updated to separate intent from actions, ie. not letting the web-app
control motors directly. Other changes were to separate the camera handling, mapping, localization, and
mission strategy. Camera handling with AprilTag detection may need to move into it's own thread
as heavy cpu usage is expected and critical sensor data / motor
actions need to be maintained. A possible solution would be for the Roomba to stop every
now & then, look for april tags, and then carry on.

[MicroDuck Architecture](https://github.com/pollen-robotics/microduck/blob/main/docs/design/architecture.md)

## Status:
- work in progress
- location data and odometry seems to make sense
- unexpected obstacles still confuse the system
- not all skills are up to speed: follow-the-wall, run-around-chair-leg, get-out-of-a-tight-spot, etc.
- next step would be to implement a follow-the-wall run with scanning and recording 12 new april tags

## AprilTag scans

The camera service captures and analyzes one frame every 10 seconds. AprilTag 3
detection runs on a grayscale copy scaled to at most 640 pixels on its longest
side; the original frame remains available for snapshots. Each observation
contains the family, tag ID, detection quality, pixel center/corners, capture
timestamp, and source image size. The service also records detector runtime so
the scan cost can be measured on the Pi Zero.

Install the official [AprilTag 3 library and Python bindings](https://github.com/AprilRobotics/apriltag#install)
on the Raspberry Pi. The current printed sheet uses family `tag16h5`, IDs 1â€“16;
only the surveyed subset is listed in `autonomy.json`. Measure the physical tag
size between the outer edges of the black square, the dimension AprilTag uses
for pose. In `tags1-8.pdf` the 80 mm label describes the white quiet-zone
square; the black tag square is nominally 60 mm. The configured 57.5 mm is the
measured black square on the current print, about 4% smaller than nominal,
which is consistent with printer scaling. Re-measure after changing printers or
disabling page scaling. Until camera intrinsics, measured tag size, surveyed tag
positions, and camera mounting pose are configured, detections are image
coordinates only and must not be treated as room coordinates. AprilTag 3
supports multiple families, including the standard family and `tag16h5` used
here. [AprilTag 3 families and pose API](https://github.com/AprilRobotics/apriltag#usage)

Stationary scans are enabled by `camera.pause_for_detection`, which is set in
the shipped `autonomy.json`. The mission coordinator stops the robot, waits one
second for it to settle, then replans after the scan. The camera never resumes
motors itself. While the robot is already stopped, the coordinator also writes
pending map changes, which keeps the large JSON fsync off moving ticks.
Continuous discovery reversals and turns skip the stationary scan so they do not
brake and restart mid-motion. The skip applies only while a continuous command
is actually running; if a safety stop or stale pose has stopped the robot, the
next scan is allowed so localization can recover instead of expiring in a
skip-scan loop. Remote-control driving also skips a scan while the wheels are
moving, but scans normally when the operator stops. Stopping after manual motion
requests an immediate scan, so the camera can capture a new tag without waiting
for the next ten-second slot. Odometry and AprilTag corrections continue in
remote-control mode, and accepted tags update the live pose and map trail.
Disable stationary scans only when the pose pipeline is trusted enough to apply
moving corrections, because a scan takes about 1.5 seconds and a moving
correction is that old by the time it is applied.

## Connecting autonomy

The service reads `roomberry/autonomy.json` when that file exists. Without it,
the mapper and mission coordinator are not started. The mission defaults to `idle`; set `start_mode` to `discovery` to run the stationary AprilTag survey cycle, or `clean` only after validating the room survey and calibration. Discovery uses the dock, tag 2, and every other configured landmark in order, moves at 50 mm/s with cleaning motors off, and captures each scan at the camera sensor maximum resolution. It approaches tag 2 until bumper contact, then parks 500 mm from each remaining tag face to scan it before returning to the 500 mm retreat point. Tags 1 and 2 are excluded from the visit list, so the current configuration visits tag 16 followed by tag 15. Each visit logs the arrival pose, the tag-corrected post-scan pose, the odometry correction, the facing error, and the landmark's optional surface so carpet and hard-floor runs can be compared. The dock anchor is (1060, 260) mm with the robot facing -Y, so the retreat target is (1060, 760) mm. Leave `start_mode` as `idle` until ready to run the robot. During any active mission, Sunday through Thursday LEDs mirror left cliff or left IR proximity, front-left cliff or front-left IR, wall or center IR, front-right cliff or front-right IR, and right cliff or right IR activity, holding each indication for two seconds after a brief trigger; Friday and Saturday remain unused. A rising edge on the physical Schedule button starts discovery and both physical Schedule and Clock presses play a short confirmation beep. The room frame uses meters in the 4x4 tag transforms, with +X to
the right, +Y forward, and heading counter-clockwise; the mapper converts its
public pose and waypoints to millimeters. The configuration needs:

- `robot_radius_mm`. The optional `map` defaults to an 8 m by 8 m room with
  grid spacing close to half the robot radius. Set `width_mm` and `height_mm`
  to change its size, or provide `cols`, `rows`, and optionally `cell_size_mm`
  to define the grid directly. `origin_mm` defaults to `[0, 0]`. Optional
  `persist_interval_s` (default 30 seconds) limits how often the full map is
  written; pending changes are also flushed whenever a stationary AprilTag scan
  stops the robot, when the mission leaves an active mode, or at shutdown.
- Optional `max_localization_age` (default 60 seconds) is how long odometry-only
  motion is trusted after the last accepted tag observation. The supplied
  `autonomy.json` raises this to 600 seconds so the long tag 2 to tag 16, tag 16
  to tag 15, and return legs can finish even while scans see only distant or
  oblique tags; an expired estimate still stops the robot and requests a fresh
  scan.
- `camera.tag_size_m`, `camera.intrinsics` (`fx`, `fy`, `cx`, `cy` calibrated
  for the configured 1296x972 camera image), and optional scan settings.
- `camera_from_robot`, a 4x4 transform that maps robot-frame points into the
  camera frame, with translations in meters.
- `landmarks`, a list of `{family, id, world_from_tag}` entries. Each 4x4
  `world_from_tag` transform places a surveyed tag in the room frame, with
  translations in meters. Roomberry converts the resulting planar pose to mm.
  An optional `surface` string (for example `carpet` or `hard_floor`) is logged
  with discovery visit measurements.
- Optional `dock_waypoint_mm` to route to a mapped staging point before asking
  the Roomba to perform its final infrared dock seek.
- Optional `wall_follow` settings (`enabled`, `target_signal`, `side`) to use
  the Create 2 wall signal as a low-speed local behavior. Calibrate its target
  on the actual floor and wall finish.
- Optional `tag_filter` thresholds. A tag estimate is ignored when its Hamming
  distance is nonzero, its decision margin is below `min_decision_margin`, its
  reprojection error exceeds `max_reprojection_error`, or its measured range is
  outside `min_tag_distance_m`..`max_tag_distance_m`. While the last accepted
  tag is younger than `max_pose_jump_age` (default 30 seconds), estimates that
  jump more than `max_pose_jump_mm` or `max_heading_jump_rad` from the
  odometry-predicted pose are rejected; after that the prediction is too stale
  to reject a correction. When several tags are visible, the largest agreeing
  group within `consensus_distance_mm` and `consensus_heading_rad` is combined
  with a quality weight; outliers are ignored. The defaults are tuned for the
  57.5 mm `tag16h5` sheet.

The coordinator fuses wheel deltas between tag observations, updates coverage,
marks bumper contacts as obstacle hints, requests mapper waypoints, and sends
short bounded drive commands through the command arbiter. Cliff, wheel-drop,
stale-sensor, and localization-age checks stop the mission. A hard safety stop
puts it in idle; it must be restarted after the condition is resolved.

## Remote control

A drive or Open Interface mode command from the web interface cancels any
running autonomous mission and enters `remote_control` mode. The original web
application can keep sending its existing `drive`, `drive_direct`, and
`drive_pwm` requests; the server accepts them as a remote operator, restores
Safe mode when needed, and stops the mission coordinator from planning or
braking over them. Repeated joystick commands refresh the remote session
without injecting stops between them. Wheel odometry and AprilTag localization
continue in remote mode, so the map trail follows the drive and accepted tags
re-anchor the pose. If the robot was left in Passive mode, the next manual drive
command switches it back to Safe automatically. Pressing the physical Clock
button ends remote control and returns to idle; Schedule still starts
discovery.

The Roomba Open Interface is allowed 1.5 seconds to settle after startup before
motion is accepted. While the robot is stationary on its home base, transient
cliff and wheel-drop readings are suppressed so the dock does not latch a false
safety stop; suppression ends as soon as a drive command is requested. During
the first 150 mm of the dock retreat, a cliff reading pauses motion for up to
two seconds so the dock ramp or its shadow can clear; a reading that persists
still aborts the mission. Continuous commands are also refreshed every mission
tick and re-sent every half second, so a brake by the command arbiter either
resumes the same motion or is reported as a rejection instead of leaving the
coordinator waiting on a command that is no longer running. Bumper contacts are
mapped as obstacles only during intentional mission motion, not while idle,
charging, or retreating off the dock. The map point is placed at the bumper
face rather than several cells into the obstacle.

After the retreat scan, discovery turns directly toward the tag 2 approach
point instead of making a full U-turn first. It turns again to face tag 2 at the
500 mm approach point before requesting its scan. After bumper contact it
reverses until the physical bumper is clear and
the robot has moved at least 150 mm from the tag, then starts the remaining tag
visits. The light bumpers are treated as proximity hints rather than contact
sensors because the white tag can keep them active. The reverse is capped at
250 mm, with a 10 second safety timeout if odometry stalls; failing either limit
stops the mission for manual recovery.

Each additional tag is approached from a parking point 500 mm along its
surveyed normal, aligned, and scanned without touching the tag or an unknown
obstacle. If the expected tag is missing, the scan is retried at yaw offsets and
finally with a 180-degree turn, which also catches a tag mounted on the opposite
side from its provisional orientation. Missing tags are logged and the visit
continues with the surveyed geometry. Bumper contact on an approach, align, or
return leg starts the same detour used for IR proximity, and the contact point
is mapped as an obstacle. Subsequent obstacles start further detours without a
per-leg count limit. After the last
visit, discovery returns through the earlier parking points (currently the tag
16 point) and stops at the retreat point.

Forward transit legs watch the raw light-bumper signals instead of waiting for
the contact bits, which in the recorded runs rise roughly a second before
impact. A reading above the carpet-noise threshold must persist for
`DISCOVERY_PROXIMITY_CONFIRM_TICKS` mission ticks (three by default, 0.6 seconds)
before the robot reacts, so single-poll spikes during motion changes do not
cause a false detour; an asserted light-bumper contact bit bypasses that
confirmation. A confirmed reading stops the robot, reverses 150 mm, turns 90
degrees away from the reported side, drives a 450 mm parallel leg, and then
rejoins the surveyed route. Further proximity or contact on the route starts
another detour without a count limit. If the bumper touches during the parallel
leg, discovery stops in `idle` for manual recovery. These detours are logged with the raw zone
signals, contact bits, and pose. The final tag 2 approach also halves speed as
soon as the light bumpers report proximity.

Debug logs report 10-second camera detection and Roomba sensor-poll timing,
plus 10-second mission-loop, planner, and command-dispatch averages. Decision
changes and rejected commands are logged as they happen. These measurements
should guide the first on-device tuning of scan size, mission period, and
stationary scans.

## Sensor recording

The optional `sensor_log` section writes one CSV file per service run, for
example `/var/log/roomberry-sensors/roomberry-sensors-20261025-153000.csv`.
It samples sensor group 100 at `interval_s` (default 0.1 seconds) and includes
wheel odometry, voltage, signed battery current, battery power, charge and
temperature, wheel/brush motor currents, bumpers, light bumpers, cliffs, wall,
overcurrent, and stasis data. The Open Interface reports `voltage` in
millivolts, stored here as `battery_voltage_v`, and `current` in milliamps,
stored as `battery_current_a` with positive values charging and negative values
discharging. `battery_power_w` combines the two.

`battery_current_avg_1s_a` and `battery_current_avg_5s_a`, plus the matching
left/right wheel-current averages, are rolling means over the recorded samples.
They make it possible to compare a normal reverse move with the earlier case
where the Roomba backed into furniture and spun its wheels: requested wheel
velocity and encoder progress can be checked against elevated current. No
automatic rear-bumper action uses these values yet; collect a few runs first to
choose a threshold that does not trigger on carpet or normal reverse recovery.

```json
"sensor_log": {
  "enabled": true,
  "directory": "/var/log/roomberry-sensors",
  "interval_s": 0.1,
  "flush_interval_s": 10,
  "max_files": 20,
  "filename_prefix": "roomberry-sensors"
}
```

The file is buffered and flushed to the operating system only every
`flush_interval_s`; it is never fsynced per sample. The normal Linux page cache
then decides when to touch the SD card. Files rotate per service start and the
oldest are removed so at most `max_files` remain. Set `enabled` to `false` to
stop recording, or raise `interval_s` for a smaller file. The records are plain
CSV with a header row and can be opened directly in Excel or a spreadsheet.
`tools/get-pi-logs` copies the directory to the repository's `logs/sensors`
folder.


**Roomberry** isÂ a surveillance robot based on **Roomba** using a **Raspberry Pi Zero W** and a **camera module**. A demo of Roomberry's capabilities as well as the web interface developed to interact with the robot can be seen in the following video:

[![Roomberry Demo](https://domoticproject.com/wp-content/uploads/2018/08/RoomberryDemoVisualCue.png)](https://www.youtube.com/watch?&v=kQcQSE5pvNA "Roomberry Demo")

## Requirements

To build this project you will need:
-	A **mini DIN 7 male connector** (DIN 8 is compatible too) with Roomba's pin 3 (RxD), 4 (TxD) and 5 (BRC).
-	A compatible **Roomba** (series 600/700/800) adapted to provide a regulated 5 V power source direct from the battery using an step-down (PololuÂ D24V5F5 is a good option).
-	A **Raspberry Pi Zero W** with Raspberry Pi OS and the Picamera2 package installed, along with the pyserial library and an adapted version of Matthew Witherwax' Python iRobot [library](https://github.com/danimaciasperea/irobot). Picamera2 requires a recent Raspberry Pi OS release with `python3-picamera2` and `python3-pil` installed.
-	A **Raspberry camera module** (I used Version 1).
-	A HAT (Hardware Attached on Top) board to connect Raspberry's GPIO with a **Logical Level Converter** (Roomba's Serial is 5 V compatible but Raspberry uses 3.3 V).
<p align="center">
<img src="https://domoticproject.com/wp-content/uploads/2018/08/Roofino_Roomba_RaspberryPiZeroW_Camera2.jpg">
</p>
<p align="center">
<img src="https://domoticproject.com/wp-content/uploads/2018/08/Roomberry-Front-View.jpg">
</p>

## How it works

`Roomberry.py` creates a **multithreading python web server** that interacts with Roomba and the camera module installed. This code is intended to run as a daemon and handles theÂ HTTP GET Requests performed against the Raspberry Pi.

To install it just download the last release and configure it as a service:
```bash
wget https://github.com/danimaciasperea/Roomberry/archive/1.0.0.tar.gz -P /tmp/
tar -xvf /tmp/1.0.0.tar.gz -C /tmp/

# Before doing next step, adapt the code to your environment (serial port used, IFTTT Key, etc.)
sudo cp /tmp/Roomberry-1.0.0/roomberry/roomberry.py /usr/local/bin/
sudo cp /tmp/Roomberry-1.0.0/roomberry/roomberry_camera.py /usr/local/bin/
sudo cp /tmp/Roomberry-1.0.0/roomberry/roomberry_control.py /usr/local/bin/
sudo cp /tmp/Roomberry-1.0.0/roomberry/roomberry.service /lib/systemd/system/

sudo systemctl enable roomberry.service
sudo system roomberry start

```

The commands sent to the robot are encoded in the **request'sÂ  URL query string**. The URL path should start with `cam`Â or `roomba`Â depending on the device that will execute the operation. If the command needs one or more parameters, they should be just passed as a field-value pair in the query string.

For instance:

```bash
#Send a clean command to Roomba
curl roomberry/roomba/?op=clean

#Drive Roomba straight at 20 mm/s
curl roomberry/roomba/?op=drive&velocity=20&radius=32768

#Set camera saturation to 65
curl roomberry/cam/?op=cam&saturation=65

#Download picture taken the 10th 08 2018 at 10:28:49
wget roomberry/cam/20180810/20180810-102849.jpg
```

To use the **web interface** you will need a Raspberry running `apache2` with `PHP` enabled. Just deploy the web-application on the web server path. For instance:

```bash
sudo cp -R /tmp/Roomberry-1.0.0/web-app/ /var/www/
```

It has been designed using Bootstrap frameworkÂ (HTML5 andÂ Javascript withÂ AJAX requests). You will probably need to adapt the `HTML` code to your particular needs/environment.

<p align="center">
<img src="https://domoticproject.com/wp-content/uploads/2018/08/Screen-capture-WebInterface-Roomberry.png">
</p>

Find the complete instructions on how to build this project in the following [post](https://domoticproject.com/roomberry-surveillance-robot-roomba-raspberry-pi-zero-w-camera/).

## License
This project is licensed under the MIT License - see the  [license file](LICENSE.md) for details

## Legal Notice
Roomba is a trademark of iRobot Corporation. All other trademarks are the property of their respective owners.

## Acknowledgments

-  Matthew Witherwax' Python iRobot [library](https://github.com/julianpistorius/irobot).
-  Picamera [package](https://github.com/waveform80/picamera).





The autonomy map is saved atomically to roomberry/map-state.json by default
and restored on the next run. Set map.state_path to choose another writable
location. Writes are throttled to map.persist_interval_s so coverage updates do
not fsync the SD card on every mission tick, and pending changes are written
while the robot is stopped for a stationary AprilTag scan. Leaving an active
mode or shutting down forces a final save. A saved grid must match the configured dimensions,
origin, cell size, and robot radius. The live pose is reacquired from AprilTags
after restart; the saved trajectory remains visible. Request http://<robot>:8080/map.png for a
fresh PNG showing cleaned, pending, unreachable, and blocked cells, playfield
boundaries, the current localized pose, its recent trail, and surveyed tags.
The trail fades from pale blue at older poses to strong blue at the newest, and
it is broken wherever consecutive poses jump more than about 275 mm, so a
localization jump between runs is not drawn as a line across the room.
