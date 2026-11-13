<!-- @(#)tag-scan-pipeline.md 3.2.trails.1 2026/11/10 13:54:11 -->
# AprilTag scan timing, cool-offs and spoken results

These are the Pi camera's stationary AprilTag scans. The iPhone's continuous
RoomTrek AR session is separate and keeps running during these scans.

## Recorded timing before this change

The12:57:52poster run has12scans. The first scan takes17.80seconds; the following
11have a median5.00seconds (range4.38–5.65seconds in camera timing logs).
Per-stage medians do not sum exactly to the median total.

| Stage | Warm-scan median | First scan |
| --- | ---: | ---: |
| Stop/scan guard, feedback and pending map flush |0.14s|0.38s|
| Existing stationary settling wait |1.01s|1.02s|
| Capture RGB frame |0.09s|0.12s|
| Detector call, including process/IPC overhead |2.85s|15.78s|
| JPEG archive |0.69s|0.50s|
| Total, including metadata and scheduling overhead |5.00s|17.80s|

The first child-measured detector pipeline totals2.18seconds, including2.05s
native detection, while its parent call takes15.78s. The difference is outside
those child-measured stages: startup/imports/IPC/scheduling may contribute.
It is not evidence that native detection alone consumed15.78seconds.

Detection/preprocessing/pose estimation already run in a separate spawned
process. That separates their Python GIL and native work from robot control.
It does not create CPU capacity on the user's single-core Pi: both processes
still share that core. Capture and archiving remain on the camera thread in
the parent process. These measurements do not prove CPU load causes UART faults.

## New scan sequence

1. Acknowledge the physical stop; hold the existing scan/motion guard.
2. Keep the existing one-second stationary settling wait.
3. Capture the frame and retain its actual capture timestamp.
4. **Cool off for 500 milliseconds**, outside the camera lock.
5. Run detection in the spawned detector process and collect observations.
6. **Cool off for 500 milliseconds** before archiving.
7. Save JPEG and metadata.
8. **Cool off for 500 milliseconds** before publishing/releasing the result.
9. Publish detections, stamp their ready time, queue result speech, release
   the scan guard, and let the mission apply its existing fix-validation rules.

This adds about1.5seconds to each stationary scan. The preceding run with
three1second gaps had a warm median7.924s and a cold scan17.535s; reducing
the gaps should save1.5s per scan. Physical verification is still needed.
Motion/safety/scan timeout policies remain in force. A consistent two-scan
confirmation therefore takes longer than before.

The waits use the camera worker's shutdown event, not a sleep on the robot I/O
or mission thread. Camera/detection locks are free during the waits. Sensor
polling continues and the robot remains held. Shutdown interrupts any of the
three waits; an interrupted result is not published or announced, and scan
cleanup still runs. Moving snapshots whose stationary detection is skipped
do not get these waits.

Optional `camera.scan_cooloff_seconds` configures all three waits, default0.5;
set0to compare the old pacing. `camera.scan_settle_seconds` independently
controls the pre-capture settling wait, also default1.0. No config-file edit is
needed to enable the new default. Main scan logs include actual
`cooloff_after_capture`, `cooloff_after_detect`, `cooloff_after_archive` and
total timings. Saved JSON records the configured duration and the stages
already completed when it was written; post-archive timing appears in the main
log and speech callback's report.

## Spoken results

The existing authenticated RoomTrek SPEAK worker announces each completed scan,
for example: “Captain, tag16, clear read. Camera range30centimetres.” It reports
up to two strongest readable surveyed tags, falling back to unmapped tags when
needed. Duplicate detections of one tag ID are reduced to the strongest read.
It also announces no tags, only weak detections, skipped moving scans and
detector failures. Missing quality metadata is spoken as “quality unavailable.”

Quality labels describe the detector read, not a confirmed robot pose or saved
AR-map lock. They use `min_decision_margin` (default10) and
`tag_filter.max_reprojection_error` (default10), matching configured filtering
thresholds for these measures:

- **Weak:** with complete quality metadata, corrected-bit count is nonzero, decision margin is below minimum,
  or finite pose error exceeds maximum/is negative.
- **Marginal:** passes those checks, but margin is below twice the minimum
  or pose error exceeds half the maximum.
- **Clear:** passes the stricter margin/pose-error band with zero corrected bits.
- **Unavailable:** one of those quality measures is missing/non-finite.

Labels are heuristic bands, not confidence percentages. Camera range is the
camera-to-tag distance, not robot-centre distance. Passing detector quality
does not bypass range, landmark, consistency, localization or motion guards.

Result speech is queued without network I/O on the camera/robot threads. It
uses `SCAN_RESULT`; existing safety priorities, bounded queue, stale-message
drops and delivery outcome logging remain. The main log records the spoken
summary with its command ID. Frequent scan speech resets the30second battery
quiet timer just like other speech.

## Deployment

Pi-only: sync/restart with updated roomberry.py, roomberry_camera.py and
roomberry_speech.py. The installed RoomTrek app already accepts the speech;
no iPhone rebuild or installation is needed. No live scan or robot movement
was commanded while implementing this change.

## Current-run map trails

`/map.png` and archived map PNGs show independent wheel and iPhone traces
after the first accepted stationary tag16 scan. Blue is wheel odometry;
red marks wheel segments after a large coordinate jump; purple is the
iPhone robot-centre trace, corrected for the configured camera mount.
The iPhone requires usable stationary frame history around the tag16
capture. If unavailable, it waits for another accepted tag16 scan.

These diagnostic traces continue through idle, manual steering and mission
changes, including coverage clears. Later tag fixes do not refit them. A new
service process starts a new run. A wheel odometry reset breaks the traces
and requires a new tag16 anchor. Stale/limited phone tracking or a changed
phone session/map breaks its line; a changed session/map requires a new
wheel epoch/service run before a new alignment. An unavailable phone never
gets a fabricated wheel-based trace. Traces are ephemeral; periodic PNG
archives retain them, while saved coverage does not restore them as current.
