<!-- @(#)CAPTAINSLOG.md 3.1.tiles.6 2026/11/06 10:00:00 -->
# Captains Log

### November 6 short-outbound guard + confirm fixes (3.1.tiles.6)

- Scan-free approach now requires outbound ≥1000 mm; zero-length re-runs
  at the grout end stay in 'return' instead of aborting instantly on the
  seeded (lying) range. Short-run return is bounded by outbound+5000 mm
  travel without contact.
- Line-end confirmation accepts 3 losses interleaved with good frames
  (only 3 good frames cancel), fixing the 4528 mm 'could not be confirmed'
  outbound fault.
- Fresh GridDrive in an ongoing phone session re-baselines the crossing
  count instead of logging missed=13 spans on re-run.
- 70 gridrunner tests pass. Pi sync + restart pending; no iOS change.

### November 6 scan-free return + speed steps (3.1.tiles.5 / 3.1.grout.20)

- Return no longer scans checkpoints or seeks tag fixes: grout steering
  drives home, front bumper ends the approach; line-loss/overtravel aborts.
  `_scan`/`_scan_tick` remain for explicit Tag15Return recovery only. Map
  flushing is on mode-exit/shutdown (`_flush_map`), so scan pauses were
  never needed for SD writes. Explicit tag homing (`return_to_tag15`) is
  unchanged.
- Speeds pit-calibrated: slow/approach/pivot 30 → 40 mm/s (firmware floors
  <~40), cruise 100, I/O steps now 0 → 40 → 70 → 100 (`roomberry_control`).
  Launch tolerates a sleeping Roomba: waiting stage now waits up to 10 s
  for fresh sensors instead of aborting instantly.
- Tests: 110 gridrunner+control pass, incl. updated step timing and
  scan-free handoff/abort expectations. Pi sync + restart pending; no iOS
  change in this build.

### November 5 return line-loss resilience (3.1.tiles.4)

- Root cause from the 17:32 run: immediately after turnaround the stripe
  rode at scan_x 0.17–0.20 (left search edge) and flickered flags=3/2.
  The 1 s degraded timer expired mid-flicker and handed off to tag
  recovery before the stripe could stabilize.
- Pi: return/approach loss grace **1 s → 3 s** (`GRID_RETURN_LOSS_GRACE_S`);
  steering reuses the **last-good line correction/heading for 1.5 s**
  (`GRID_LAST_GOOD_STEER_S`) instead of snapping to heading hold; samples
  log `last_good_line_age_s`.
- iOS: scan window widened `width/8..7w/8` → `width/16..15w/16`; no-stripe
  now NSLogs top/bottom hit counts for edge diagnostics. Build 3.1.5
  installed on Peters 10.
- Tests: 67 gridrunner tests pass, incl. new grace/last-good steering test.

### November 5 tile-crossing durable table + calibration report (3.1.tiles.3)

- `build_crossing_report()` in `roomberry_gridrunner.py` turns the in-memory
  crossings into a durable per-tile table: per-span tile span (304.8 mm),
  absolute wheel delta, error mm/%, missed counts, leg reset between outbound
  and return, and a summary (mean error, median + total wheel/tile ratios).
- The table is stored in the `GridDrive` result (`crossings`,
  `crossing_report`) on both complete and abort, logged once as
  `GridRunner crossing report:` JSON, and exposed in the gridrunner status
  snapshot. `tools/tile-crossings.py` rebuilds CSV + Markdown from any
  `roomberry.log` offline. Observation only; no steering/scale change.
- Tests: per-tile + leg reset, missed-span widening, abort persistence.
  All 66 gridrunner tests pass. Next: reinstall GridRunner 3.1 build 4 on
  Peters 10, sync/restart the Pi, run a full kitchen out-and-back, and
  compare the report's median ratio against the provisional wheel factor.

### November 5 tile-crossing recording — iOS phase 3 + Pi table

- Replaced the type-5 reserved 28-byte padding with a crossing trailer:
  magic `0xC7`, version 1, valid-band flags, monotonic count, interpolated
  last-crossing uptime (us), band row, confidence and last interval (s).
  `GridPacket.encoded()` still produces exactly 128 bytes; the old all-zero
  trailer remains decodable as the legacy pre-crossing format.
- Python `GRID_PACKET` is now `<4sBBHQQIHbBQQ12fHHBBHIQfff`; `GRID_FIELDS` and
  `decode_grid_packet` validate the trailer (magic/version/flags, 0..1 row and
  confidence, 0..600 s interval, count/time consistency, crossing time not
  after send time). NavLink recording and CSV export pick up the new columns
  automatically.
- `GridDrive` watches the phone count per `(session, calibration)` and logs one
  `GridRunner crossing:` JSON record per new count with crossing time, interval,
  stage, direction, wheel distance/heading and tag distance. A skipped packet
  is recorded as `missed=N` without inventing a time. Samples and the complete
  result now include `tiles=N`. No steering or stop behavior changed.
- Added wire/Swift/legacy and Pi recording tests: 63 gridrunner tests pass,
  including the real Swift encoder/decoder round trip. Full suite: 484 tests,
  15 pre-existing import errors for missing PIL/numpy/serial/six only.
  Release build succeeded (`/tmp/GridRunner-tiles-wire-build.log`).
- App build bumped to 3.1 build 4. Next: reinstall on Peters 10, sync/restart
  the Pi service, then verify `GridRunner crossing:` rows in `roomberry.log`
  and the exported NavLink CSV against a full run.

### November 5 transverse tile-crossing detector — iOS phases 1–2

- Added `GridCrossing.swift`: two vertical strips at22%/78% image width either
  side of the longitudinal line avoid the centre grout and LED corona. Per-row
  medians and a local bright-tile background find a dark run independently in
  each strip; width3–64px, contrast, ambiguity and a yaw-tolerant centre
  agreement reject one-sided texture and reflections while allowing a few
  degrees of robot tilt.
- Added a direction-agnostic crossing state machine. A confirmed band must be
  seen for2 approach frames, passes a fixed50% reference row, interpolates its
  crossing time, then clears the row for2 frames beyond30mm with a1.5s minimum
  interval. It only observes; no steering, speed or stop changes.
- `GridCamera` runs the detector on the same luma frame as line detection,
  resets the tracker on session start and snapshots `crossing` on stop. Each
  crossing logs `count/time/y/confidence/interval`; periodic samples add
  `tiles=`. `GridPacket` carries local crossing state only: the128-byte wire
  packet and28 zero trailer bytes are unchanged. Pi table/recording deferred.
- Overlay adds a white dashed reference row, two white strip guides, orange
  band markers and a green flash/dot on a counted crossing. Status shows
  `Tiles N · last interval X s`. Help text updated.
- New `tests/GridCrossingCheck.swift` compiles the real detector with synthetic
  images: moving band, reverse travel, stationary band, reversal before the row,
  one-sided texture, a slightly tilted band, misaligned strips, low contrast,
  LED corona, jitter and a15-tile sequence. `roomberry_gridrunner_test.py` now
  compiles/runs it with `-O` and also links `GridCrossing.swift` into the
  existing wire test.
- Validation: focused Swift crossing check reports `crossings=15 expected=15`;
  all5 `GridWireTest` cases pass. Signed Release build succeeded and ios-deploy
  installed GridRunner3.1 build3 on Peters10 (iPhone X, iOS16.7.16). Logs:
  `/tmp/GridRunner-tiles-release-build.log`,
  `/tmp/GridRunner-tiles-install.log`. No app launch or robot motion requested.
- Next: Pi decoding of the reserved type-5 trailer, crossing/odometry table and
  recordings, then a physical15-tile verification in both directions.

### November 4 continuous grout out-and-back with tag-15 return
- Build 3.1.grout.4 changes Clock/web GridRunner into one reverse-out/forward-
  return mission. Fresh explicit line loss slows50→20 mm/s with last wheel
  heading hold; three distinct good observations restore speed. Stale frames,
  health or stopped/camera/IMU states still abort. Slow outbound allowance30s/
  750mm, maximum outbound5000mm and600s total; motor lease remains600ms moving.
- A new phone bump brakes outbound and records onset/settled wheel distance.
  Hold1s, then return forward in Safe without native docking or in-place turns.
  Stop/scan at estimated robot-center/tag15 distances2000/1500/1000/500mm.
  Quality-checked tag fixes update world pose/map and bounded heading steering
  toward the tag's front-contact point. Return solver allows2.5m camera range;
  normal navigation's1.2m tag15 gate is unchanged.
- Three attempts permitted at final500mm scan; reliable fix required. Final
  creep20mm/s ends only on front bumper near predicted tag position, with
  bounded lateral/heading/overtravel guards. Unexpected return phone impacts
  or contact abort. Lease is ended while intentionally stopped/scanning and
  restarted before motion. Scan callbacks preserve guarding and Clock cancel.
- Whole mission shares the map origin; accepted tags correct it. Old scans and
  global pose are invalidated when leaving GridRunner so the last stopped
  scan cannot be applied later as if captured at the bumper endpoint.
- Console shows phase/slow state/speed/next scan and threshold/checkpoint JSON.
  Native dock button relabeled Seek charging dock. No phone rebuild needed;
  keep app Reverse through return. Docs: roomberry/docs/grout-run-controls.md
  and ios-app/GridRunner/README.md. Physical validation/deployment pending.
- Focused state-machine/model tests cover loss/reacquisition, phone-bump turn,
  all scan checkpoints, missing final tag, stale data, timeout, overtravel and
  bumper endpoint. Differential-drive model includes yaw bias, line losses,
  real camera/tag projection + pose solver and scan callbacks; finishes within
  40mm lateral error in the model. This is not a physical accuracy claim.
- Validation: 407 regression tests, 406 pass. Only the previously recorded Mac
  camera annotation exact-white-pixel test fails. JavaScriptCore syntax and
  source/document identification/whitespace checks pass. No deployment or
  physical robot movement performed.

### November 4 successful grout traversal and native dock-seeking review
- Reconstructed 11:18–11:22 session. Six outbound legs reached sustained
  line loss at 11:20:24.781, settled adjusted signed wheel travel 4536.2 mm
  (absolute 4537.5). Two Clock retries added only 10.3 mm net, final 4546.5 mm.
  First five interruptions were single invalid detector packets, reacquired
  ~100 ms later. No motor-lease expiry; driving cadence median201/max227 ms.
- Initial line offset improved −31.4→−8.1 mm; phone CPU median26.78/peak31.87%,
  thermal nominal. Endpoint is visual line loss, not verified contact; do not
  recalibrate wheels from its 88.8 mm shortfall versus assumed4625 mm travel.
- Three web return intervals used native seek_dock, explicitly no mapped dock
  route. Early scans did not localize; tag15 accepted at11:22:07 near0.65 m.
  Final interval records bumper contacts, ~164° heading change, and phone impact
  peaks up to1.93g, consistent with reported collision while turning.
- Native docking selected Passive OI; Pi reverse recovery was rejected37 times
  because it requires Safe. Also identified map reseeding on each Clock arm,
  so its trail is not a continuous trace across these resumes. Analysis only;
  no control changes. Report: output/grout-run-20261104-1118-review.md.

### November 4 short-run regression and immediate raw reset
- Investigated all five 11:05 grout attempts: each stopped on the .6 s motor
  lease with valid phone line detections. Driving-sample gaps 673–738 ms.
  New map work scanned all 9476 cells repeatedly and could synchronously
  persist/fsync before the drive tick. This was an introduced regression.
- Build 3.1.grout.3 keeps the watchdog unchanged. Grout control now takes the
  direct tick path; map follows it. Coverage visits only nearby footprint
  cells (at most nine at current pitch/radius). Active experiment map writes
  remain in memory; mode-end flush persists them. Host benchmark 1000 pose+
  sweep updates: median .0074 ms, max .7625 ms; physical Pi validation pending.
- Raw reset now writes contiguous 80 07 immediately from the request path,
  before mission-lock/owner-queue waits, with no intervening sleep or reads.
  Startup's first serial operation is the same pair. The owner later completes
  boot recovery, discards queued stale commands and requires fresh sensors.
- Focused tests cover reset with the owner stopped, stale-command cancellation,
  first startup write, bounded coverage equivalence and deferred persistence.
  211 focused regression tests pass. Detailed analysis:
  output/grout-20261104-1105-review.md. Deployment/physical checks pending.
- Full validation: 395 tests, 394 pass; only the previously documented Mac
  camera annotation exact-white-pixel assertion fails. Whitespace/SCCS checks
  pass. No watchdog extension, iPhone change or physical motion performed.

### November 4 wheel adjustment, grout steering and run controls
- Applied requested provisional wheel-size reference (4799−174)/4583.020565923183
  = 1.0091597743 (+0.915977%). Scales both encoder wheel distances and yaw;
  OI fallback distance/angle also scaled. Commands and archived logs unchanged.
- Pi grout steering gain multiplier 2, still bounded by phone limit (default
  .25) and Pi .35 cap. Added applied steering multiplier, wheel distance and
  heading to run samples for physical response comparison.
- Calibration/grout experiments now trace wheel motion and mark visited cookies
  in map.png. Separate assumed tag-15 manual origin (one body radius before
  tag, facing it), explicitly labeled estimate; no navigation localization fix.
- Local console adds grout/clean/return/manual controls, raw wake/reset and Pi
  build/factor/firmware version check. Build 3.1.grout.2. Reset cancels the run,
  bypasses driver reset/start with raw 80, wait .1 s, 07, boot wait, 80; fresh
  sensors and explicit run restart required. No pre-reset mode queries.
- Details and deployment notes: roomberry/docs/grout-run-controls.md. Pi update
  and physical steering/asleep-reset validation remain pending; no phone rebuild.
- Validation: 393 regression tests, 392 pass. Only the previously recorded
  camera annotation exact-white-pixel assertion fails on this Mac. Updated
  button-poll expectations for wheel scaling and removed a test race between
  motion-lease expiry publication and completed braking. JavaScriptCore syntax
  check passes; git diff whitespace checks pass. Raw asleep reset, scale/wrap,
  steering cap and run-map visit behavior have focused test coverage.

### November 4 grout run 1 investigation
- Confirmed 8.24 s command-to-stop run, settled wheel travel 485.7 mm (1.59 ft).
  Phone explicitly lost valid line detection at 09:45:59.533; Pi braked at
  09:45:59.652. Fresh frames/health, unchanged bump count and clear Roomba
  hazard/bumper flags exclude those as the recorded stop trigger.
- Line approached the detector's 12.5% left search boundary; last upper
  scanline center 14.05%. Edge clipping is the leading explanation, but raw
  camera frames are absent, so ambiguity/contrast cannot be ruled out.
- Report: output/grout-run-1-20261104-review.md. Actual lens-left setting
  −13 mm; steering/geometry need validation. No control changes.
- Follow-up resource decode: CPU median 26.72% of one core, peak 27.63%;
  app footprint stable 13.83 MiB, thermal nominal. Frame age at send median
  68.82 ms. No overload evidence; report discusses multi-row stripe fitting.
- Plotted both scanline positions of the same grout stripe, offset and angle
  over time, with left search boundary and detection-loss/stop times. PNG,
  PDF, decoded CSV and reproducible script: output/grout-run-1-20261104/.
  Invalid packet placeholders are excluded from measurement curves.

## Stardate 26-11-02

### Discovered
- reviewed big pickle's analysis with focus on tracking down position disagreements between roomba odometry,
april tag scan results, and iphone tracking.
- recommendation was to tape a test track on the floor. Luckily my kitchen floor has built-in tracks: the tiles
consist of imperial 1 foot squares of unknown material with a hard surface, clear black gaps between tiles,
and built-in simulated dirt particles to support optical tracking.
- we have two iphone apps: StarLock using ARKit to track the ceiling, and GroundHog using some other kit to
correlate position (like an optical mouse). When turning the iphone towards the floor, StarLink still seems
to lock on and track. Earlier problems were drop-outs when running under chairs, tables, etc. - but the floor
should be visible at all times. Worth a try!

### Next
- prepare kitchen for manual tag scans from verified positions
- tag 15 in the kitchen has moved y +57 mm to align with a gap to follow for measurements. map needs to update.
- review manual steering of the robot to test positions and trigger tag scans
- perform and record tag scanning ativities

### Completed
- positioning filter hardened: motion-aware single-tag gate, rejected scans can no
  longer unlock the jump gate, planar branch check against the known tag pose,
  tag 15 limited to 1.2 m, `max_localization_age` reduced 900 s -> 30 s.
- map rendering hides the previous session by default and marks relocation
  segments in red.
- GroundHog reporting moved to its own queue (build 4) with stale-heartbeat
  reports instead of inventing displacement.
- analysis written to `output/positioning-analysis-20261102.md`.
- focused python suite: 258 tests OK.
- Published snapshot `5c91169` to GitHub (`PreussLabsLLC/RoomBerry26`).
- Next: tape-measure the tile pitch and run the straight five-tile test before
  trusting an odometry scale correction.
- built an overhead-camera ground-truth pipeline for the tile-grid calibration
  run: `roomberry_overhead.py` (numpy + Pillow only, ffmpeg for decode) plus
  `tools/overhead-track.py` with `frame`, `calibrate`, `check`, `swatch`,
  `track`, `legs`, and `compare` commands. The four clicked tile intersections
  give a pixel-to-millimetre homography; red/green markers give position,
  heading, and a measured marker baseline. `legs --expected-tiles 1` reports
  the real grid distance between every scan stop, which distinguishes a short
  wheel scale from stops that never reached the next tile. `compare` aligns the
  video to the Pi sensor log by speed correlation and reports the wheel-scale
  ratio.
- procedure and acceptance criteria written to
  `docs/overhead-ground-truth.md`.
- end-to-end pipeline verified on a synthetic 6x4-tile 4K-style clip: 4-tile
  travel measured 1219.2 mm, 5 % short wheel log recovered as scale 1.0526.
- 15 new unit tests for homography, marker detection, track/video decode, and
  the compare fit; full suite has two pre-existing failures unrelated to this
  work (`create2_test` needs `RPi`, camera annotation test needs a system font).

### Next
- mount the phone over the kitchen run, calibrate the grid, and record a
  forward/reverse six-tile sweep.
- measure the marker baseline with the tape and compare with the tracked
  baseline before trusting the scale.



### Calibration overhead recording implementation
- Replaced stepped reverse/scan/contact calibration with one reverse leg, one
  one-second turnaround hold, and a forward return to the starting wheel
  distance. No calibration tag scans or bumper approach; manual alignment at
  tag 15 establishes the start. Both estimates use a local start frame.
- GroundHog relative yaw now controls heading with gain 4.0 and steering cap
  0.35, including the reverse sign correction. Tracking invalidity, stale data,
  nonfinite poses, and session/calibration/continuity changes stop the run.
  Existing physical sensor, impact, odometry, and heading guards remain active.
- Added timestamped motion JSON, start/turnaround/finish checkpoints, and
  distance/hold values in calibration status. Configure the measured six-pitch
  span with ROOMBERRY_CALIBRATION_DISTANCE_MM; default 1828.8 mm excludes the
  unmeasured grout. ROOMBERRY_CALIBRATION_HOLD_S defaults to 1 second.
- Updated overhead recording instructions and replaced obsolete scan/contact
  tests with continuous-route, steering, tracking-loss, and no-scan coverage.
- Validation: 189 calibration, mission, and control tests plus all 7 GroundHog
  tests pass (GroundHog rerun outside the sandbox for UDP/macOS Vision). Physical floor
  validation of the stronger heading gains and measured grout-inclusive span
  remains necessary before interpreting the overhead run.

### Calibration startup import repair
- Fixed a missed calibration dependency in roomberry_web.py that prevented
  startup after removal of the old tag-scan acceptance constants. Command
  metadata now describes manual alignment, no scans, and wheel endpoint
  tolerance. Updated the current dashboard acceptance text to match.
- Added command-catalog regression coverage. All 35 web and calibration tests
  pass, including importing RoomberryHandler through the application module.
- JavaScript syntax CLI check unavailable because Node is not installed.

### Timer scans disabled for overhead calibration
- Camera worker now waits only for explicit scan requests. Timer-driven
  captures and tag scans are disabled in every mode, regardless of the legacy
  snapshot_interval setting. Explicit manual/mission requests remain available,
  with calibration's scan-pause guard rejecting detection during the run.
- Regression coverage confirms no unrequested scan, queued explicit requests,
  shutdown wakeup, and Clock cancel/release/press starting a fresh calibration.
  No reproduced Clock logic failure or button behavior change; actual Pi
  interruption/restart failure remains unconfirmed.
- Validation: 43 camera archive, calibration, and web tests pass.
- Changes remain on development system; user will deploy and restart.

### Short calibration run and unresponsive Clock, 20:36
- Analyzed current application log, sensor CSV and raw NavLink recording. The
  1850 mm run stopped after about 1.2 seconds of commanded motion / 35.6 mm
  wheel travel because GroundHog continuity changed 1 -> 2. No tag scan occurred.
  One rejected frame lies between valid packets 614 and 615; the transient
  failure reason was not transmitted before recovery.
- Idle after calibration retained OI Safe, leaving firmware Clock input
  unavailable. Restore Passive after calibration exits to idle; preserve the
  explicit OI-stop latch and log mode-transition failures. Added regression
  tests for abort/restart, completion, and refusing to rearm an OI stop.
- Added old/new identities and packet diagnostics to continuity-abort messages.
  Full analysis: output/calibration-20261102-2036-analysis.md. GroundHog's
  underlying frame rejection remains undiagnosed; no baseline stitching added.
- Validation: all 208 relevant tests pass. Development-only changes; user
  handles deployment and process restart.

### GroundHog build 5: landscape display and robust spatial coverage
- Landscape-only interface supports both sides. Data/calibration scroll on the
  left; a stamp-size 72x96-point preview and large fixed Start/Stop control sit
  on the right. Live labels coalesce updates on a 0.5-second timer. Capture
  pixels stay portrait and mount calibration still uses the physical top edge.
- Replaced the all-four-quadrants candidate gate with spatial coverage of robust
  inliers: 30% width/height span, four occupied 4x4 cells, covariance area ratio
  >=0.10. Existing count, agreement and residual limits remain.
- Fit failures log candidate/inlier counts or residual; coverage failures log
  occupied quadrants/cells, spans and area ratio. Last failure remains visible
  after recovery. Packet format, capture rate and 10 Hz reporting remain intact.
- Validation: unsigned iPhoneOS build succeeds; actual Swift geometry/serializer
  and reporting isolation tests pass. Geometry cases cover all four choices
  of missing quadrant, patches, narrow bands, diagonals and clustered inliers
  with scattered outliers. Final geometry rerun also passes. Physical floor
  validation and on-device layout inspection remain pending. No deployment.

### GroundHog build 5 deployed to SE
- Built signed Release and installed GroundHog 3.1 build 5 over USB on Peters
  SE (iOS 15.8.8). ios-deploy completed successfully (100% installed); built
  bundle CFBundleVersion verified as 5. Installed over the existing application
  without uninstalling. No tracking session or robot motion was started.

### GroundHog build 6: camera LED control
- Added LED On/Off below Start/Stop. Selection while stopped is queued and
  applied after capture starts; live toggles run on the camera queue using
  AVCaptureDevice configuration locking. Stop, backgrounding, and startup
  failure extinguish the torch and clear the selection. Hardware availability
  and configuration errors are reported rather than assuming LED success.
- Moved startup focus settling after capture/torch activation. Saved mount
  calibration and estimator/telemetry rates remain unchanged.
- Signed Release build succeeds; CFBundleVersion 6 verified. Installed over
  existing GroundHog on Peters SE via USB (ios-deploy 100% success). Physical
  LED illumination and low-light tracking need user verification on the phone.

### Review of successful 21:15 calibration
- Full 1850 mm target out-and-back completed in 65.0 seconds with one
  turnaround hold, no tag scan or abort. Passive restored at completion.
- 650/650 motion reports valid, same continuity segment, zero rejected-frame
  increments and no missing UDP sequences. Maximum GroundHog heading deviation
  3.35 degrees; steering peaked at 0.234, below 0.35 cap.
- Final GroundHog displacement ~40 mm, wheels ~39 mm; both show ~35–37 mm
  lateral offset. Outbound GroundHog distance ~5% shorter than wheel estimate;
  still evident after the turnaround hold. Need overhead truth before adjusting
  either scale. Low round-trip error cannot establish scale accuracy.
- No new impacts, physical sensor hazards or wheel overcurrents during the run.
  Phone thermal fair; accepted frame rate ~25 fps. Torch state is not recorded,
  so lighting improvement cannot be isolated from coverage changes in these logs.
- Detailed report: output/calibration-20261102-2115-review.md. No code changes.

## Stardate 26-11-03

### Discovered
- Yesterday's calibration run was successful. Adding the LED flashlight to GroundHog runs
raised tracking quality to near 100%. The heading data from GroundHog was used to nudge
Roomba back on track.
- I had inspected the caster wheel (spins and swivels freely)
as well as the drive wheels and motors, no wear, wiggling, or left/right
differences noted. The side brush already had been removed to prevent drag.

### Next
- since the iphone is sticking out the back of the roomba it is exposed to collisions
in reverse and during tight turns. That prompted the (rather sensitive) bump detection.
- Let's use that to extend the kitchen run from tag 15 to the carpet threshold
at know location. The run will span about 15.75 tiles or 4.799 m.
- Overhead recording setup but not yet analyzed.

### Threshold kitchen run prepared
- Reverse travel limit is now 5000 mm; cruise speed raised from 50 to 75 mm/s
  in both directions, retaining endpoint slowdown and GroundHog heading gains.
- A fresh iPhone bump during reverse immediately stops the command, ends that
  leg, holds one second, then returns forward to the initial wheel distance.
  Any reported peak qualifies, including an unavailable peak. Existing counts
  and later peak refinements of that event do not retrigger. A new return-leg
  impact retains the existing peak policy; physical bumper contact still aborts.
- Turnaround checkpoint records phone-bump versus distance-limit termination.
  The expected threshold is about 4799 mm; only overhead truth can confirm its
  actual location and travel scale. No scale correction applied.
- Validation: all 196 calibration, mission and control tests pass, including
  threshold stop/return, peak refinement, old-event rejection, 5000 mm fallback,
  and 75 mm/s steering commands. Updated recording instructions.
- Development changes only. Remove/update any older calibration distance
  environment override when deploying and restarting the robot process.

### Review of short November 3 runs
- Four attempts aborted after 1.0–1.4 seconds because GroundHog continuity
  changed. Raw packets show rejected frames, texture/agreement failures and
  a frame-gap/stale-frame report. Stops completed and Passive was restored.
- Updated 75 mm/s speed and threshold-run logic are deployed, but every start
  still targets 1850 mm: the old process environment override appears active.
  Remove/update ROOMBERRY_CALIBRATION_DISTANCE_MM and restart for 5000 mm.
- No threshold turnaround occurred. Exact optical failure and torch state
  cannot be established from these logs. See output/calibration-20261103-0853-review.md.
- Analysis only; no control code changed.

### Additional-light retry, 09:02
- User confirms phone torch was on for morning trials and added external LED.
- Four more attempts at 09:02:39/46/50/58 aborted after about 1.0–1.4 s on
  continuity changes. Raw recording has 408/413 valid motion reports, but
  brief fit/coverage and stale-frame failures still break the run. The app
  recovers between failures; this is not total loss of tracking.
- All start targets now read 5000 mm. Speed remains 75 mm/s. Health thermal
  state is nominal; images remain 480x640. Packet reason 7 conflates fit and
  spatial coverage failures; GroundHog's Last diagnostic is needed to separate
  them. Extra light alone has not resolved it. A controlled 50 mm/s retry
  would isolate the speed change from yesterday's successful run.
- Analysis only; no control settings changed.

### External-light-only retry and exact failure diagnostic
- Three attempts at 09:09:49, 09:10:04 and 09:10:10 again aborted on
  continuity changes after 1.0–1.4 s, with 5000 mm targets and 75 mm/s commands.
- User screenshot resolves one reason-7 failure: too few candidates=19,
  dt=0.066715584 s. FloorGeometry.fit requires 24 before robust fitting;
  this particular failure precedes the spatial coverage test.
- Candidate selection samples the central image on a 16-pixel grid, rejecting
  weak gradients, invalid/large flow, out-of-image matches, brightness mismatch
  and invalid floor projections. Nineteen candidates does not establish which
  rejection dominates. Successful-frame median candidates is 404, versus 338.5
  across yesterday's recording: a transient collapse rather than uniformly
  feature-poor input. Failed packets zero the candidate diagnostics.
- Latest raw log: 495/520 motion packets valid, reasons 7 (11), 4 (13), 3 (1).
  Median successful-frame processing 47.7 ms versus 35.2 ms yesterday; health
  battery 32% versus 100%, thermal nominal versus fair. These correlations do
  not prove battery throttling or identify the optical failure cause.
- Recommend controlled retry at previous 50 mm/s before relaxing fit gates;
  candidate rejection counts and exposure/focus diagnostics would further
  distinguish motion, texture and timing causes. No code changed.

### Calibration speed restored to 50 mm/s
- Restored cruise cap to 50 mm/s in both directions for a controlled retry.
  The 5000 mm reverse limit, phone-bump turnaround, heading corrections and
  endpoint slowdown remain in place. Updated recording instructions and
  speed/steering regression expectations.
- All 34 calibration tests pass. Local change; deployment/restart pending.

### 50 mm/s retry: long leg and recorded threshold contacts
- First attempt ran 76.7 s before another continuity abort; last motion sample
  reports 4489 mm wheel travel and 4252 mm GroundHog X displacement. User
  observed a stop about 5 cm short of the threshold; not a distance-limit stop.
- Reverse phone bumps caused turnarounds at 09:21:10 (61 mm local travel),
  09:23:41 (1939 mm) and 09:24:28 (52 mm). The latter two match the user's
  reported repeated threshold hits. Software labels are candidate contacts.
- 09:23 return aborted on a distinct impact refined to 9619 mm/s²; other two
  short bump runs completed. Intermediate restarts also had continuity aborts.
- Each restart reanchors locally, so return goes to that restart position,
  not the original tag-15 position. No control code changed.
- Full review: output/calibration-20261103-0919-review.md.

### Peters 10 GroundHog installation preparation
- USB detects Peters 10 as iPhone X on iOS 16.7.16. Xcode 14.2 builds signed
  GroundHog 3.1 build 6 Release successfully for generic iOS.
- Installation failed with 0xe8008015: current provisioning profile includes
  Peters SE only. Attempted device registration/profile refresh through Xcode;
  destination is ineligible until Developer Mode is enabled on Peters 10.
- User must enable Settings > Privacy & Security > Developer Mode and complete
  the phone restart/confirmation before device-specific signing can continue.
  App not installed, no robot motion started. Build/install logs are in
  /tmp/GroundHog-iPhoneX*.log.

### GroundHog installed on Peters 10
- After Developer Mode was enabled, Xcode's bundled iOS 16.1 developer disk
  failed to mount on iOS 16.7.16. Downloaded 16.6.zip from
  https://github.com/filsv/iOSDeviceSupport and added its developer disk and
  signature in Xcode_14.2.app's DeviceSupport/16.7 folder. Existing support
  folders preserved. Device preparation then succeeded.
- Xcode device-targeted signed Release build with automatic provisioning and
  device registration succeeded for Peters 10. ios-deploy over USB reported
  InstallComplete / 100% installed; exit 0. GroundHog version 3.1 build 6.
- No application tracking or robot motion started. New phone requires its own
  measured mount calibration and permissions. Stop SE tracking before using
  the X against the same Pi receiver; this is a replacement-phone trial.
- Build/install evidence: /tmp/GroundHog-iPhoneX-device-build.log and
  /tmp/GroundHog-iPhoneX-install.log.

### iPhone X full outbound threshold run, 09:54
- Threshold reached after 75.52 s; phone bump count 8 (0.49 g) triggered the
  intended stop/hold/return. A distinct count-9 impact (0.63 g) aborted the
  return at 09:56:26. GroundHog did not lose tracking. Wheel distance settled
  about 2462 mm from the starting coordinate; stop and Passive restoration
  completed normally, with no recorded physical bumper/hard hazard.
- All 1117 motion reports valid, zero rejected-frame increments, zero missing
  sequences, continuity 17 throughout. Accepted capture about 30 fps; median
  processing 27.39 ms versus recent SE 45–48 ms. More compute margin observed,
  but cause of SE failures is not isolated by swapping phones.
- Threshold wheel travel 4564 mm; phone X displacement 4349 mm, 249 mm total
  pose separation including 127 mm lateral disagreement. Scale remains
  unverified; GroundHog camera height reports 85 mm and needs mount confirmation.
- Report: output/calibration-20261103-0954-review.md; accompanying metrics JSON.
  Analysis only; no control code or impact thresholds changed.

### Kitchen run plots and floor-IR inspection
- Generated trajectory/time plots with reverse/return styles, both phone bumps,
  and coincident floor-IR dip candidates. Added four raw downward-IR traces
  with local baselines and a documented candidate score. PNG and vector PDF
  artifacts are in output/kitchen-run-20261103-0954/ with events CSV,
  reproducible plot script and archived motion samples.
- Two weak coincident dips at 51.26 s (3.058 m wheel distance outbound) and
  92.45 s (3.691 m returning). No clean periodic tile sequence identified;
  labels are unconfirmed grout indications, not verified grout intersections.
- Trajectory lateral scale explicitly magnified; event positions interpolate
  robot estimates at Pi receipt times. Method/limitations in the folder README.
- Installed matplotlib in the project virtual environment; visually inspected
  both generated figures. No robot control changes.

### November 3 check-in preparation
- Prepared all pending source, documentation, analysis and local runtime
  artifacts for local version control. GitHub uses the existing independent
  publication checkout at output/github-publication/Roomberry, preserving its
  main-branch history and excluding raw logs/session files and local agent
  instructions. Current analysis reports and kitchen plot artifacts included.
- Full roomberry_* suite: 373 tests run, 372 pass. The existing camera
  annotation exact-white-pixel assertion still fails on this Mac's font setup;
  this limitation was previously recorded on November 2. Swift/Vision and
  GroundHog wire/geometry/reporting checks pass. Signed Release build and
  device installation succeeded earlier; plot images visually checked.
- Reviewed pending files for oversized files and credential patterns; none
  found. Applicable pending source files have one SCCS identification each.

### Clean full kitchen run, 13:46–13:49
- User identified a grain of rice as the earlier return-impact source and
  cleaned the route. Full out-and-back now completes in 158.93 s; threshold
  bump 0.47 g triggers turnaround at 4583 mm wheel travel, with no return bump.
- All 1590 motion packets valid, zero rejected-frame increments, no lost
  sequences, continuity 0 throughout. Accepted capture 30 fps, median Vision
  time 27.93 ms, thermal nominal. No tracking cause for the observed drift.
- Finish: GroundHog (-36, -233) mm, wheels (-9, -193) mm, in local start frame.
  Final heading +0.12° phone / -0.33° wheels; lateral drift remains. Settled
  signed wheel distance -0.7 mm, phone approximately (-32, -233) mm.
- Phone distance-weighted heading +0.76° reverse and -2.24° return; rightward
  offsets accumulate on both legs. Existing proportional heading controller
  has no lateral-error feedback or integral. Return steering mean +0.157,
  peak 0.338, with bounded but biased heading oscillations.
- First post-finish sensor row shows both physical bumpers at 13:49:15.115
  with zero wheel commands; contact did not cause completion or prior drift.
- Full report, metrics, archived samples and drift plot/PDF in
  output/kitchen-run-20261103-1346/. Recommend overhead/endpoint measurement,
  mount-height confirmation and bounded line-following feedback rather than
  simply increasing heading gain. Analysis only; no control changes.

### Bounded lateral drift correction prepared
- User updated the iPhone X's GroundHog mount calibration: lens height 85 mm,
  physical top-edge angle 180°, lens forward -200 mm, lens left -23 mm.
  These measurements are entered in GroundHog; no duplicate Pi mount change.
- Calibration now uses phone lateral position to request a heading toward
  the original local y=0 line: 600 mm look-ahead, target limited to ±0.10 rad
  (5.7°). Reverse travel reverses the target sign. Turnaround preserves the
  same line and origin. Existing gain 4.0, steering cap 0.35 and 50 mm/s cruise
  remain, as do wheel-distance endpoints, impacts and absolute heading guards.
- Motion logs add cross_track_mm and target_heading_rad; checkpoint logs add
  line-control parameters. Recording documentation updated for line following.
- All 200 calibration/mission/control tests pass, including both correction
  directions, target bounding/logging, absolute heading safety, and a complete
  differential-drive model with persistent direction-dependent yaw bias.
  Model endpoint lateral error is below 40 mm; this is a software check, not
  a prediction of physical floor accuracy. Physical run validation pending.
- Development changes only; user deploys/restarts the Pi, then starts freshly
  aligned at tag 15 with the updated GroundHog mount values.

### Overhead video ground-truth investigation
- Matched IMG_0917.MOV (178.808 s, 4K portrait rotation, ~24 fps) to the
  13:46:35–13:49:14 completed run and 134454 sensor/NavLink files. Fitted
  video origin ~13:46:20.30 PST; threshold stop ~93.73 s and finish ~173.91 s.
- Added experiment-local analysis scripts, annotations, aligned measurements
  CSV (1794 rows, 13 reviewed video observations), report, trajectory PNG/PDF,
  grid check, review sheets and source checksums under
  roomberry/experiments/kitchen-run-2026-11-03/. Original movie stays local.
- Twenty visible grid intersections: nominal-pitch fit RMS 5.7 mm, held-out
  RMS 6.3 mm. Compensated small static-floor image translation. No video
  positions are filled across the unmeasured 54–136 s interval.
- End-to-end projected rim displacement is ~253 mm right, confirming drift.
  This is not height-corrected center truth. Intermediate video axes follow
  grout while telemetry follows initial body heading; alignment is uncalibrated.
- Visible spans: wheel longitudinal changes within ~1% of raw projected video;
  phone reports ~4–5% less. Nominal pitch, raised-rim parallax, uncalibrated
  distortion and annotations prevent assigning an absolute scale correction.
- Full-leg reference must be 4799 minus initial center-to-door distance minus
  rear contact reach. Threshold was a phone impact with clear body bumpers;
  actual contact geometry is unmeasured and not automatically the lens offset.
- Physical bumper assertion is first sampled after completion; its true onset
  is bracketed across a polling gap and could be slightly before completion.
- Reproduced numerical outputs identically; verified 13 sparse video rows and
  no gap filling; reviewed annotations and plot. No navigation/control changes.

### GridRunner straight grout-line follower
- Added independent iOS GridRunner app/icon, reusing unmodified GroundHog
  geometry/health helpers. Two scanlines estimate floor-relative offset/angle,
  including −13 mm lateral mounting offset; adjustable bounded proportional
  correction supports forward/reverse. Debug overlay and console logs included.
- Added validated NavLink type 5, ordered observations and binary/CSV logging.
  Mission consumes these through the existing motor arbiter at 50 mm/s for a
  single leg capped at 5000 mm. No intersection counting or automatic return.
- Clock now arms GridRunner and displays GRID; another press cancels. Clock
  still cancels active calibration; web Calibrate remains available.
- Line/health/sensor freshness, phone/body impacts, hazards, odometry validity,
  progress and run limits stop the mission. Added independent 600 ms motor
  lease to brake if the mission thread stalls. Explicit restart is required.
- Unsigned iPhoneOS Release build succeeded. Full regression suite: 387/388
  passed; existing camera annotation exact-white-pixel test still fails in
  this host environment. Synthetic Swift detector/packet tests passed.
- GroundHog sources unchanged. Not installed or physically validated; see
  ios-app/GridRunner/README.md for mounting, operation and protocol details.

### GridRunner iPhone X deployment
- Signed Release 3.1 (build 1) with the configured development team and
  installed successfully on Peter’s iPhone X (iOS 16.7.16) via USB.
- GroundHog remains installed separately. Pi deployment and physical
  line-following validation remain pending.

### Grout return corrections — Pi build 3.1.grout.5

- Return now uses forward grout steering before final approach. Once a tag fix
  is accepted, a bounded tag-heading correction contributes 25% of steering;
  the final approach uses the required final tag pose. Uncorrected wheel pose
  cannot override a visible stripe. Return line loss is bounded to 30 s/750 mm
  until the final tag fix. Samples log both steering components and fix status.
- Native AprilTag processing now runs in a persistent spawned process, keeping
  its GIL separate from Roomba polling and NavLink reception. Detection has a
  10-second timeout; original sensor/phone freshness guards remain unchanged.
- Checkpoints are consumed after processing, preserving interrupted scans for
  retry. Resume cannot skip a failed final scan, and a separate range gate
  requires final localization even if the checkpoint list is empty. Resume
  waits for any live scan to finish and rejects an already completed return.
- Removed the raw, out-of-owner START/RESET wake bypass and its special mission
  reset path. Restored the original separate startup START/delay/RESET sequence
  and standard queued driver reset. Neither wake experiment was reliable when
  undocked; the console no longer labels reset as wake.
- Blue debris LED latches on new phone-impact or physical-bumper events and
  resets on mission mode changes. A held bumper or old phone counter does not
  relatch it after reset; all LED writes stay on the I/O owner thread.
- Validation: 235 regression tests passed, followed by 38 final focused tests.
  These cover the full differential-drive route, checkpoint retries after
  abort, rejected final-scan rearming, forward line/updated-tag steering, LED
  reset behavior, and sensor polling during a native call that deliberately
  holds its worker GIL for 800 ms. An existing annotation test now tolerates
  antialiased fallback fonts whose brightest text pixel is 254 rather than 255.
- Local development changes only; Pi deployment/restart and physical run
  validation remain pending. No iPhone rebuild required. Restart clears the
  retained run, so align at tag 15 and begin a new out-and-back afterward.

### Line-loss speed trial — Pi build 3.1.grout.6

- Raised outbound and return line-loss slow speed from 20 to 30 mm/s to test
  steering response above the problematic low-speed range. Cruise stays at
  50 mm/s; tag-guided final approach stays at 20 mm/s.
- Updated existing slowdown/reacquisition assertions and the differential-drive
  route model. All 35 GridRunner tests pass. Local changes; Pi deployment and
  physical verification pending.

### Startup read preview and measured local steering pad — build 3.1.grout.7

- Startup logs an escaped representation of the first 80 decoded boot-stream
  characters before version parsing, including when parsing returns unknown.
- Local steering pad adds 5-degree left/right in-place turns and 50 mm forward/
  backward steps. Server-side wheel feedback ends the move, rather than a blind
  timed drive. Measured results appear in status JSON and beside the pad.
- Steps pause the active mission, use Safe remote control with a 600 ms I/O
  motion lease, brake and end in idle. Stop/mode changes can cancel without
  waiting for the whole step. A newer manual command takes ownership without
  stale cleanup braking it. Duplicate steps and scans in progress are rejected.
- Sensor/bumper/cliff/drop checks, wheel epoch/validity, wrong-direction motion,
  no progress and overall time limits guard steps. Brake failure leaves the
  independent lease armed. Pad motion integrates the retained grout pose,
  permitting return resumption without treating commanded motion as a push.
- 194 tests passed across manual-step, startup, web, mission and control suites.
  Mock browser checks passed at 320, 390 and 1280 px: one press sends one step,
  pad directions lock during movement, Stop stays enabled, and there is no
  horizontal overflow. Preview: output/steering-pad-preview.png.
- Local changes only. Pi sync/restart and physical distance/turn checks pending;
  no iPhone rebuild required. The firmware parser itself was not changed.

### Camera-centered grout following and rotated preview — build 3.1.grout.8

- Startup logs the full boot text before parsing, stripping binary/nonprinting
  bytes while retaining printable ASCII, tabs and line breaks. Raw stored boot
  output and the escaped first-80-character diagnostic remain unchanged.
- Grout steering targets the camera's lateral axis: tracking error is the
  measured robot-relative grout offset minus configured lens-left position.
  A +26 mm lens-left mount means the robot center tracks 26 mm robot-right
  of the stripe. The physical mount calibration remains a measurement.
- Initial run pose/map and tag-guided return aim use that same lateral offset.
  Logs add target_offset_mm and tracking_error_mm, preserving raw offset_mm.
  The local console displays the camera-line tracking error. Contact and
  heading safety envelopes remain unchanged.
- iOS cyan target, correction and stripe-candidate preference use the camera
  axis. Displayed error is relative to that axis. The preview and its overlays
  rotate 90 degrees clockwise together inside a swapped-bounds container;
  capture frames, detector coordinates and mount orientation do not rotate.
- Version-1 packet validation accepts the legacy advertised robot-center
  correction as well as the new camera-centered correction for old archives.
  Actual Pi steering is always recomputed using the new target.
- Validation: 194 focused regression tests and all 4 wire/Swift tests passed
  (198 total). Tests include +26 mm physical lens offset, aligned zero steering,
  map seeding and final approach target, real Swift detector/overlay targets,
  both travel signs, and complete binary-stripped startup output. GridRunner
  unsigned device build succeeded with the rotated preview.
- Pit-stop compliance mode is deferred. Current wheel-drop detection sends OI
  STOP and latches until rearmed; no bypass added. Future tests should compare
  floor-loaded and free-wheel responses, with fixture/suspension support and
  independent stopping considered explicitly.
- Local implementation/build only. Pi deployment/restart and installation of
  the updated iOS build remain pending. Start with camera over grout, retain
  the measured mount settings, and begin a new run after updating the Pi.

### GridRunner 3.1 build 2 installed on Peter's iPhone X

- Detected Peters 10 (iPhone X, iOS 16.7.16) connected through USB.
- Incremented GridRunner build number to 2 and built a signed Release using
  the existing development team/provisioning configuration. Build succeeded.
- ios-deploy installed com.preusslabs.GridRunner over USB and reported
  InstallComplete / 100% installed. Includes camera-centered target and the
  preview/overlay 90-degree clockwise rotation. No app launch or robot motion
  was requested. This deployment did not update the Pi.
- Build log: /tmp/GridRunner-camera-center-release-build.log.
  Install log: /tmp/GridRunner-camera-center-install.log.

### Return recovery and explicit OI rearm — Pi build 3.1.grout.9

- Added main Restart OI button and coordinated rearm: cancel the mission,
  restart OI into Passive, discard the old trace, and qualify fresh sensors.
  UI polls readiness after the explicit click and reports when Ready; it never
  starts motion automatically. No wheel-drop safeguard was bypassed.
- Replaced slow differential steering with measured in-place pivots followed
  by equal-wheel straight travel. Entry/exit heading error: 5/2 degrees.
  Opposite pivot response aborts; angular progress participates in the motion
  watchdog. Final approach stays 20 mm/s straight; cruise stays 50 mm/s.
- Later tag fixes must agree with the last fix plus wheel motion within 200 mm
  and 8 degrees. Far inconsistencies get one retry. Final approach requires
  two consistent stationary poses (75 mm / 4 degrees), at most three attempts.
- Dedicated checkpoint results now emit happy/unhappy tones; pending final
  confirmation emits neutral. Stationary tone settling avoids song replacement
  without blocking the I/O owner. Scan time pauses the moving line-loss timer.
- Pad braking anticipates the observed overshoot by 12 mm / 3 degrees. Tests
  include the observed approximately 12.5 mm / 3.2 degree coast/encoder lag.
  _change_mode now refreshes sensor state to remove cached-Passive rejection.
- 243 regression tests passed, followed by 48 final focused tests after tone
  settling was added. Coverage includes a full projected-tag differential-drive
  model, pivot/straight approach, wrong-way turns, inconsistent/final tag fixes,
  readiness qualification, old-trace invalidation, and pad compensation.
- Mock browser checks passed at 320/390/1280 px, including a single explicit
  Restart OI request, readiness polling, movement-button locking and active Stop.
- Local implementation only; Pi sync/restart pending. No iOS changes or rebuild
  needed. Threshold-impact handling remains active; pit-stop mode not added.

### 2026-11-04 — Pi 3.1.grout.10: independent tag-15 recovery

- Return to tag 15 now cancels any active mode and starts an independent homing
  operation; no threshold event, phone connection, or previous run is required.
  Repeated clicks preserve an active homing operation. Hard safety stops still
  require explicit Restart OI and fresh grounded sensors.
- Localizes using surveyed AprilTags, confirms two agreeing poses, searches
  stationary headings when position is unknown, and follows a clear mapped route
  to a final tag-15 approach. A continuous prior wheel trace may bridge a missing
  initial view; no assumed tag origin is used after restart or odometry jumps.
  Later fixes must agree with wheel projection; missing/inconsistent localization,
  blocked routes and bounded travel/time limits stop the operation.
- Fixed the unreachable slow-pivot threshold by using uncapped geometric heading
  error. Weak observations no longer refresh the recovery heading; reliable line
  reacquisition needs three distinct frames at confidence >= .75.
- Added no-phone homing simulation from a 120-degree starting heading using the
  real mapper, plus mode transitions, fresh scan queuing, pose solver, lost-tag,
  safety, route, odometry and confidence regression coverage. Final focused suite:
  70 tests passed; final broader suite: 261 tests passed. Mock browser checks
  passed at 320/390/1280 pixels, including
  homing scan status, steering controls and explicit Restart OI readiness polling.
- Local implementation only; Pi sync/restart pending. No iPhone rebuild needed.

### 2026-11-04 — 18:57 session log review

- Analysis only; report: output/grout-run-20261104-1857-review.md.
- Confirmed homing pivot overshoot/reversal guard timing fault: spin_left was
  issued only 19 ms before wrong-direction abort, after a right-turn overshoot.
- Three-scan localization only compares adjacent candidates; two later requests
  contained an agreeing first/third pair that was overlooked.
- All 11 automatic checkpoint poses rejected; no measured tag correction applied.
  Final predicted range 515 mm vs camera tag range about 1.7 m. Repeated-start
  origin assumptions and unreliable tag poses prevent a trustworthy floor trace.
- First return also aborted on serial timeout/sensors not ready. No code changes.

### 2026-11-04 — pit-stop design proposal

- Saved roomberry/docs/pit-stop-proposal.md; proposal only, no hardware commands.
- Recommend standalone serial-exclusive Pi runner, `pit` LED, explicit bench
  Full-mode arming, separate watchdog, velocity sweeps and raw sensor recording.
- Wheel drop/cliff/stasis are expected on a stand; production floor safety stays
  unchanged. Include stop/settle transitions, per-wheel compliance and coast data.
- Pending return fixes retained in output/grout-run-20261104-1857-review.md.

### 2026-11-04 — bounded standalone pit-stop implementation (3.1.pit.1)

- Added roomberry/roomberry_pitstop.py and roomberry/docs/pit-stop.md.
  Default action is a serial-free dry-run; --simulate produces accelerated
  synthetic recordings; --run requires fresh interactive WHEELS FREE arming.
- User trimmed the first test to 20 minutes. Default 184-stage profile is
  nominally 19:41, independently capped at 1200 seconds by the I/O owner.
  Covers both signs at 5..500 mm/s, each wheel alone, both equal/opposite,
  20/30/50 repeats and asymmetric navigation pairs. Smoke option is ~54 s.
- Separate exclusive serial owner reuses command packers/group-100 parser,
  displays pit, verifies Full mode and suspended wheels, records expected
  stasis/drop/cliff readings and requires unchanged suspension pattern.
  Normal Roomberry floor safety is unchanged; active service/visible serial
  users are refused. No reset/wake or auto-rearm.
- 600 ms independent heartbeat, fresh-data/overcurrent/battery/mode/button
  stops, measured settling before every reversal, final zero verification and
  Passive cleanup. Documentation states serial/process failure limitations.
- CSV/raw packet hex, manifest, command/event JSONL, per-stage compliance and
  start/stop/coast statistics, Markdown report and optional matplotlib plot.
  Targets 20 Hz and reduces to 10 Hz on sustained slow reads.
- 35 tests passed, including mock serial thread startup/cleanup and watchdog
  expiry, explicit arming boundaries, encoder wraps, malformed/stale packets,
  suspension/mode/current hazards, failed stopping and plot-free reporting.
  Complete accelerated default simulation: 184 stages, 23,726 samples,
  1186.25 seconds represented. Output: output/pit-simulated-20m-build1/.
- Local implementation and simulation only; not deployed, no physical motor
  commands. Pending homing fixes remain on file in the 18:57 run review.

### 2026-11-04 — pit charging-state diagnostics (3.1.pit.2)

- User's first empty packet occurred while Roomba was asleep; no wake/reset
  change. Empty replies now suggest manual waking and port/baud checks.
- Next awake attempt aborted with the misleading generic charger message.
  Exact failing raw packet is not yet available; posted event entries showed
  cleanup LED clearing and Passive restoration, not sensor readings.
- Corrected state interpretation: state 4 (waiting) with no powered source is
  allowed. Powered sources, active states 1..3 and charging fault 5 remain
  blocked with distinct messages containing source bits/state/current. Invalid
  charging states are rejected as malformed sensor packets.
- Manifest now preserves fault-time decoded/raw data separately from cleanup
  readings; documentation includes the OI packet definitions. 41 tests passed,
  including waiting/source/fault cases and fault snapshot preservation.
- Local implementation only; no physical commands or deployment. User was
  asked for last_packet_hex from the original manifest to identify actual state.

### 2026-11-04 — original pit abort packet confirmed

- Decoded user-supplied original last_packet_hex: charging state 4 (waiting),
  powered sources 0, battery current -344 mA, voltage 14.222 V, 24 C, charge
  1982/2696 mAh (~74%), Full mode, both wheel drops and all four cliffs set,
  no overcurrent. This was the waiting-state false positive fixed in pit.2.
- Replayed exact packet through pit.2 decode/check_sample: accepted suspended
  pattern (12, True, True, True, True). No physical command or further change.
- Packet was recorded after cleanup stop verification; original fault snapshot
  did not exist in pit.1. It supports the diagnosis; pit.2 records fault data too.

### 2026-11-04 — pit optical nuisance stop and shortened sweep (3.1.pit.3)

- Inspected roomberry/output/pit-20261104-203848-974563: 480.25 seconds,
  9,246 healthy samples; 74 stages completed, abort in stage 75 startup.
- Left cliff cleared true -> false (signal 29 baseline, 169 at fault),
  both wheel drops stayed asserted; no overcurrent/charger/button fault.
  Stop verified, cleanup clean. Cliff changes are now logged bench events,
  not aborts; losing either wheel-drop still aborts. Floor safety unchanged.
- User requested skipping 5/10 mm/s: both had zero encoder motion. Removed
  those 16 stages. New default: 168 stages, nominal 17:58, hard cap 20 min.
- Added .gitignore rules for pit-* runtime directories under /output and
  /roomberry/output; verified real and simulated recordings are ignored.
- Bench review: output/bench-20261104-203848-review.md. At 30 mm/s paired
  forward command encoder means were 42.81/40.56; 50 command 65.89/68.00.
  Firmware requested-speed quantization and unloaded left/right imbalance
  warrant further checks, not direct conclusions about loaded floor travel.
- 43 tests passed, including exact real fault-packet replay, cliff-event
  recording, retained wheel-drop guard and the reduced schedule. Local only.

### 2026-11-04 — pit speed/current plots

- Added serial-free roomberry/plot_pitstop.py for replay plotting from recorded
  CSV. Generated overview plus annotated 30 mm/s detail for the real 20:38 run,
  each as PNG/SVG under output/bench-20261104-203848-speeds-current*.
- Separates commanded speed, firmware-reported requested speed and measured
  encoder speed for each wheel; plots left/right motor current in amps below.
  Raw samples retained without smoothing; nominal encoder conversion labelled.
- Rendered and visually inspected the plot; no robot control changes or commands.

### 2026-11-04 — completed 20:56 pit run analyzed

- All 168 stages completed in 1082.95 s, 20,817 samples (~19.22 Hz).
  Full mode and both wheel drops throughout; no sampled overcurrent, charging
  source or stasis changes. Stop verified, no cleanup errors.
- Report: output/bench-20261104-205639-review.md; calibration/current/repeat
  plots and JSON under output/bench-20261104-205639-analysis*, plus raw time
  traces and 30 mm/s detail under bench-20261104-205639-speeds-current*.
- Commands 15..30 all gave ~40 nominal encoder mm/s unloaded. Small paired
  differences lost: 20/30 -> 43.0/39.1; 45/54 -> 64.2/62.7. Checked actual
  serial command bytes and firmware requested fields: ordering was correct.
- Equal +30/+30 imbalance flipped: initial 37.6/39.8, repeats 44.7/37.8 and
  44.8/38.4. This argues against a fixed wheel trim from one unloaded stage.
- Active steady mean motor currents .087/.099 A; sampled peaks .739/.795 A.
  Median startup/stop latency ~.122/.126 s, stop maxima ~.386 s. Supports
  bounded brake/settle before pivot reversal; no physical yaw proof on stand.
- Confirmed expected encoder sign on all active holds and zero steady movement
  of inactive wheels. No changes to controls or physical robot commands.

### 2026-11-04 — 150/30 grout speed experiment (3.1.grout.11)

- User requested normal 150 mm/s, slow 30, with no ramp up/down. GridDrive
  now uses 150 cruise and 30 for degraded tracking/final approach; pivots 30.
  Existing cruise steering still adjusts individual wheel speeds around base.
- Added per-command ramp=False through mission dispatch into I/O arbitration.
  GridDrive bypasses acceleration/deceleration ramps and uses immediate stops
  when changing action type. Direct commands keep ramp bookkeeping consistent
  so later ramp ticks cannot override them. Motion qualification/lease/safety
  checks remain before dispatch; other missions retain their ramp settings.
- Independent Tag15Return speeds unchanged. No iOS change or wheel delta
  calibration. Updated running version and grout operating notes.
- 237 tests passed: grout, control/ramp, mission, standalone tag return and
  manual pad. Added ramp-enabled 150 -> 30 -> 150 direct-transition regression;
  updated cruise/approach/steering expectations for the new speeds.
- Local implementation only; Pi sync/restart pending. No robot commands.

### 2026-11-04 — 22:18 high-speed grout run reviewed

- Report: output/grout-run-20261104-2218-review.md. Six starts falsely marked
  threshold after 4.3, 715.8, 0.0, 0.7, 0.0 and 24.9 mm; phone bump peaks
  2836..4645 mm/s², no corresponding physical bumper flags. Five near-start.
- All outbound samples requested -150 base, locked tracking; cruise wheel
  requests L -178..-131/R -168..-121. One +150 return sample, no slow movement.
  Early scans were return checkpoints after false threshold arrival.
- Exactly reproduced rightward homing using saved maps: cell-count BFS plus
  neighbor order chose diagonal first waypoints despite clear direct staging
  path, demanding right turns 31.95 and 20.96 degrees. No homing translation.
- Both right pivots overshot and tripped pending reversal guard fault 20/46 ms
  after spin_left dispatch. Speed experiment did not include that deferred fix.
- Analysis only, no code changes or robot commands.

### 2026-11-04 — speed versus phone bump timing plotted

- Added offline roomberry/plot_grout_bumps.py; generated overview and six launch
  close-ups as PNG/SVG, event CSV/JSON and timing note under output/grout-
  20261104-2218-speed-bumps* and output/grout-20261104-2218-bump-timing.md.
- False threshold bumps followed the first accepted -150 wheel command by
  95, 4888, 83, 83, 95 and 101 ms. Five events strongly align with launch.
  The longer run's event requires another explanation.
- Verified shared iPhone detector consumes gravity-removed user acceleration;
  branch >=0.25 g with jerk >=40 g/s can classify abrupt launches. Raw 100 Hz
  IMU/jerk not logged; plotted interval peaks and episode peaks.
- Episode peaks can update for 150 ms: retained first and updated peak values
  separately; earlier review used first values. Receipt/phone delta event-time
  estimates retain unknown network latency. Rendered/inspected plots; no control
  changes, iPhone changes or physical commands.

### 2026-11-04 — stepped grout speed and phone-impact gating (3.1.grout.12)

- User requested 0 -> 30 -> 150 and stepped deceleration, plus 150 ms
  post-speed-change phone-bump ignore with logging. Added I/O-owner discrete
  200 ms intermediate steps for grout travel and normal scan/action stops.
  Pending acceleration is canceled by immediate safety/contact/emergency stops.
  Retunes update pending target without extending the step dwell indefinitely.
- Every actual changed wheel pair is timestamped, including steering and stop
  changes. Shared phone filter matches event time (receipt minus phone
  send-to-bump age), rather than processing time, against the 150 ms window.
  Ignored counts are consumed/logged with peak, mode and wheel-change context;
  duplicate reissues do not extend windows. Physical hazard reactions retained.
  Standalone homing uses the same transient phone-impact filter.
- Mode ASCII display cache now refreshes every second and invalidates after
  beep/OI transitions. Scans retain current mode instead of overriding SCAn.
  Display writes remain I/O-owned and do not rearm wheel-drop STOP.
- 246 regression tests passed, including stepped startup/stop/retune, emergency
  cancellation, late phone-event timing, ignored-count consumption in grout and
  homing, periodic mode display recovery and beep-transition rewrites.
- Updated operating notes. Local changes only; Pi sync/restart pending, no
  iPhone rebuild or physical motor commands. Existing route/guard work remains
  separate from this user-requested speed/filter/display change.

### 2026-11-04 — 23:02 threshold/return run reviewed

- Report: output/grout-run-20261104-2302-review.md. First outbound aborted
  at ~1.73 m on recovery-pivot reversal guard; second covered another 2.959 m
  to threshold. Settled global odometry -4.691 m; accumulated travel 4.695 m.
- Six transient phone bumps correctly ignored. Return +30 command followed
  by bump ~214 ms later, outside 150 ms window; peak rose to 7405 mm/s².
  Return aborted after ~12 mm; no physical bumper flags in that window.
- Four homing requests accepted. First no-tag search stopped on phone impact.
  Second confirmed tag 16 (~4.57 m from tag 15) then guard aborted; later
  trace-based retries moved ~76/~13 mm before the same pivot reversal guard.
  Those aborts were 4/12/12 ms after reversing motor command dispatch.
- Fresh Clock start while line absent replaced the old grout object before
  homing, initially removing its fallback pose; later valid tag-16 trace reused.
- One sensor serial timeout and one display serial timeout recovered; secondary.
  Analysis only, no code changes or physical commands. Prioritize pivot settling
  and bounded threshold-exit handling before further steering tuning.

### 2026-11-04 — settle-aware shared pivot guard, 100 mm/s cruise (3.1.grout.13)

- User requested defusing the encoder-heading guard and reducing cruise to 100.
  GridDrive now uses 100 base, retaining stepped 0/30/100, slow/final/pivot 30,
  transient phone-bump filter and mode display refresh.
- Replaced duplicated pre-dispatch 1-degree guards with shared SettledTurn
  (new roomberry_turn_guard.py), used by both grout recovery and tag homing.
  Brake before pivot entry/reversal/translation; require fresh encoder quiet
  for >=150 ms (yaw <=2 deg/s, center <=5 mm/s), bounded at 1.5 s.
- Arm direction check after dispatch and anchor on a later sensor poll, using
  new snapshot sensor_monotonic_s. Old/repeated polls cannot qualify settling
  or wrong direction. Sustained >3-degree wrong travel or >8-degree excursion
  still stops. Observed turn rate also triggers earlier braking near target.
- Settling holds zero and renews lease; explicit brake, settle, dispatch and
  encoder-reference logs support the next diagnosis. No threshold-exit or
  route-shortcut policy changes included.
- 256 regression tests passed (guard, grout, control, mission, tag homing, pad).
  New tests replay the 360.64 -> 363.81 -> 365.67-degree coast sequence, stale
  pre-command polls, measured settling, real wrong-way motion and early braking.
  Ten guard tests passed again after final diagnostic logging edits.
- Local changes only; Pi sync must include new turn-guard module, then restart
  and verify 3.1.grout.13. No iPhone update or physical motor commands.

### 2026-11-05 — morning run investigated

- Report: output/grout-run-20261105-0842-review.md. Guard fix completed 24
  settling phases, no wrong-way/settling aborts. Both short outbound legs kept
  locked line tracking at -100 base. Phantom thresholds at 1.186/1.348 m had
  ~0.388/.392 g peaks and no physical bumper flags. User confirms phantom stop.
- First automatic return and last homing stopped at predicted contact-plane
  bound without bumper contact. User reports final stop ~50 mm short: model
  was roughly 0.1 m too far forward if measured from front bumper.
- First homing final scan: three mutually consistent poses rejected on heading
  innovations 13.3..14.7 deg (>8 gate), only 42..45 mm position innovation.
- Saved-map route replay still zigzags: ~853 mm vs ~682 direct clear staging
  path. Second homing accepted new pose/final fix but range bound stopped it.
- Confirmed shared phone thresholds: .25g+40g/s, .6g+15g/s or 1.2g amplitude.
  No code/settings changes or robot commands; priorities captured in report.

### 2026-11-05 — 0.5 g reaction cutoff and line-first return (3.1.grout.14)

- User requested doubling the lowest acceleration cutoff while still recording
  weaker bumps. Added shared Pi PhoneBumpPolicy: below .5 g record-only, >=.5 g
  reacts; later peak refinement of the same episode is rechecked. Phone's .25 g
  raw event stream and telemetry remain intact, so no iPhone rebuild is needed.
  Existing 150 ms speed-change suppression and physical hazard stops retained.
- Visible grout exclusively controls return steering, including final approach;
  tag poses update position without steering bias. Usable-line return is not
  diverted by the old absolute heading envelope. Cruise 100, slow/final 30.
- One second of sustained return line loss now brakes and hands to all-mapped-tag
  localization/search. Failed final scans and contact-plane bounds also get fresh
  tag recovery before idle. Three recovery handoffs maximum, hard safety retained.
- Automatic and explicit tag homing hold zero while qualifying three distinct
  good homeward line frames, then transfer pose/odometry/impact state back to grout
  following. Original heading can establish homeward direction despite tag yaw
  bias; unknown/backwards-facing robots cannot blindly follow a line away.
- Tag-only mapped paths shortcut zigzags only after full swept-footprint clearance
  checks; route goals/waypoints logged. No tag-quality thresholds loosened.
- 270 tests passed, including exact prior weak peaks, refined peaks, cutoff edge,
  line authority after tag fixes/final approach, lost-line handoff/resumption,
  zero-motion qualification, orientation gating, route shortcut and bounded stops.
- Updated operating notes. Local only; Pi sync must include new
  roomberry_phone_bumps.py and modified modules, then restart/verify grout.14.
  No iPhone build/install or physical robot commands.

### 2026-11-05 — 09:16 session reviewed; arrival metadata regression fixed (grout.15)

- Report: output/grout-run-20261105-0916-review.md. At 09:18:27 both bumpers
  pressed and arrival checks passed; completion crashed because explicit
  Tag15Return -> GridDrive lacked outbound_mm. Initialize to None (no outbound
  leg) in grout.15; extended handoff test through real completion branch.
  69 tag-return/grout integration tests passed; no physical commands/deployment.
- Weak .34g event correctly record-only; prior guard fault absent. First
  threshold marker still occurred after 708 mm on .535g phone event.
- Four aborts with visible high-confidence line were short telemetry gaps that
  pushed estimated frame age beyond 250 ms; no-stripe was not the cause there.
- Pose provenance issue documented: mid-floor fresh run assumed tag origin;
  later no-fix homing handoff called that trace tag-corrected and reported
  range180 mm, causing inappropriate final scans. Not fixed by metadata patch.
- Later verified tags/line handoffs repeatedly lost actual stripe after motion,
  exhausting 3 retries. Six sensor write timeouts + one LED timeout are separate
  I/O faults, including last return stop and earlier HTTP400 rejection.
- Only completion initialization fixed. Freshness pause/reacquisition, provenance
  and moving-line qualification remain follow-up findings, no speculative tuning.

### 2026-11-05 — Bump cutoff, 500 mm pad moves and light expiry (grout.16)

- Raise Pi phone-bump reaction cutoff to .6 g; weaker events remain recorded.
- Add forward/backward 500 mm buttons above/below the arrow pad. Measured
  odometry moves request 100 mm/s, allow 15 seconds and retain Stop, hazard,
  freshness, progress and independent motion-lease checks. Existing short steps
  unchanged. HTTP timeout accommodates longer moves; all movement buttons lock.
- Blue bump LED expires 10 seconds after the latest bump, or on mode change;
  timer handled by the existing I/O owner.
- 74 targeted tests passed. Mock browser checks at 320/390/1280 widths passed,
  including long-step routing, layout, busy lock and accessible Stop. Screenshot:
  output/steering-pad-500-preview.png. No physical robot commands or deployment;
  user syncs Pi code/assets and restarts .16. No iPhone changes required.

### 2026-11-05 — 10:17 run review (.16)

- output/grout-run-20261105-1017-review.md: .544g threshold-area event below
  cutoff; later1.466g event ignored38.84ms after stop command. Outbound stopped
  on5000mm cap. Right-wheel sustained .48A report only; slip plausible.
- Outbound tracking75% locked, final sustained stripe loss11.56s starting4526mm.
  Return97% locked, maxloss .428s; fresh frames bothways.
- Seven scans read strongtag15; localization/checkpoint rejection rather than
  visual failure. Six checkpoint fixes conflicted with retained prediction;
  final bumper contact still estimated563mm away.
- Recommended distance-gated threshold sensitivity/reaction and post-slip
  confirmed localization recovery. Analysis only; no control changes/deployment.

### 2026-11-05 — Confirmed tag relocation and threshold re-arm (grout.17)

- Keep normal grout tag correction gates (500 mm outer; 200 mm/8 degrees after
  applied fix). Quality/map-valid discrepant fixes can replace wheel prediction
  after two fresh consecutive stationary scans agree within 75 mm/4 degrees.
  Straight-approach envelope and final-corridor/route safety checks remain.
- Explicit tag return uses the same stationary agreement to recover from a bad
  wheel prediction, logging innovations and relocation. Missing/invalid results
  clear candidates. Bounded failed relocation leaves robot stopped in recovery
  or aborts rather than falling back to the disputed trace.
- At >=4000 mm outbound encoder displacement, Pi phone-bump cutoff becomes .5g
  with no speed-change suppression. Other stages keep .6g and existing150ms
  window. Log re-arm once and recheck pending events without counter reset.
- 125-test grid/wire/tag-return/phone-bump/control suite passed. After candidate
  handling refinements, 79 grid-drive/tag-return/bump tests plus an added invalid
  final-scan regression passed. Coverage includes >500mm confirmed relocation,
  disagreement, stale captures, missing scan, prior .544g episode and strong
  post-speed-change impact. Diff whitespace/SCCS checks passed.
- Updated controls notes; local only, no physical commands or deployment. Sync
  roomberry_gridrunner.py, roomberry_tag_return.py, roomberry_phone_bumps.py and
  roomberry_control.py to Pi, restart and verify3.1.grout.17. No iPhone rebuild.

### 2026-11-05 — Confirm grout-line endpoint instead of threshold bump (.18)

- Review output/grout-run-20261105-1106-review.md: restarted outbound lost stripe
  at2773mm and drove blind12s with high right-wheel load before opposite-motion
  abort. .17's4000mm re-arm window was never reached after the origin reset.
- First fresh explicit no-stripe outbound packet now hard-brakes/ends lease at
  any distance. Confirm1s and3 distinct loss frames stationary, mark endpoint
  and return;3 high-confidence new frames resume after a brief dropout.
  Repeated/ambiguous input times out stopped; stale/invalid telemetry aborts.
- Reacted phone impact now safety-aborts outbound rather than marking threshold;
  normal.6g/transient filtering remains. .17 approach re-arm superseded.
- Return interruptions include repeated moving stripe loss,56/80 and32/80byte
  sensor packets, and inconsistent stationary tag poses. Confirmed relocation
  worked later. Final119mm retained range tripped approach bound; repeated
  near-target recovery loop documented, no arrival/tolerance guard loosened.
-141 tests passed: grid/wire/tag-return/bump/control129 and web12. Differential
  drive simulation now turns around on stripe end without phone impact. Docs
  and command description updated. Local only; sync roomberry_gridrunner.py,
  roomberry_control.py and roomberry_web.py, restart/verify3.1.grout.18. No iOS
  update, physical commands or deployment.

### 2026-11-05 — 11:36 review, 150mm clearance and SCAN display (.19)

- output/grout-run-20261105-1136/report.md plus reproducible raw Health/sensor
  analysis, event CSV and comparison plot. Initial brake4528.1mm, settled
  endpoint4537.291mm; no continued reverse travel during confirmation.
- Return handed to tag recovery after only~19mm forward/1s no stripe. Add
  threshold_clearance stage:150mm straight forward at30mm/s, then brake and
  qualify3 good new frames; allow1s stopped before tag recovery if unavailable.
  Maintain fresh telemetry/hazards/phone guards,3s no-progress and12s total bound.
- Robot display now shows SCAN throughout actual I/O scan gating, including
  when mission loop is busy; periodic refresh remains and mode restores.
- Latest outbound events .403/.503/.433/.366g at session reverse encoder
  positions2.68/2.76/3.39/4.19m. No event at endpoint. Prior10:17 ramp .544g
  and1.466g (possible tap) did not recur. CSV covers five sessions, plot last3.
- Line tracking mostly good; world pose not stable. Stationary tag fixes jumped
  ~506mm then295mm; repeated scans consumed117.86s over22 captures, median4.72s
  and maximum17.04s. Last contact both bumpers11:41:56.736 was safety-aborted
  rather than arrival; tight pose-heading gate plausible, not relaxed.
-129 targeted grid-drive/control/tag-return/phone-bump tests passed, including
  real-geometry end-to-end simulation and new clearance/display regressions;
  two clearance checks rerun after stopped-status display correction. Docs,
  whitespace/SCCS checked. No robot commands/deployment. Sync grid/control
  to Pi, restart/verify3.1.grout.19. No iPhone build/install needed.

### 2026-11-05 — Three-trip distance comparison, 11:59 session

- output/grout-runs-20261105-1159/report.md, metrics.json/distances.csv and
  reproducible analyze.py. Settled outbound3103.4/4530.6/4570.0mm; net return
  including clearance/manual steps3155.0/4563.7/4600.7mm. Clearances152.8/152.1/152.5mm.
- User confirms first trip phone LED off; repeated line loss near3.0m then
  endpoint3.1m plausibly lighting-related. Exclude it from full-threshold
  repeatability. Runs2/3 differ39.5mm outbound, but starts differ52.5mm and
  continuous session encoder endpoint positions only13mm apart. Floor accuracy
  remains unverified by encoders alone. Previous11:36 endpoint4537.3mm.
- Scans18/15/7, totals94.8/69.6/35.8s. All three final stops physical bumper
  contact, still safety-aborted rather than declared mission completion.
- Viewed final map: accumulated wheel traces/coverage plus tag corrections;
  accepted293.5mm/19.6deg correction in run2 and125.7mm/13.6deg in run3.
  Stationary rejected scan pair in run3 differs~500mm/17.3deg. Tag pose bias and
  map anchoring remain suspect. Map coverage can interpolate localization
  jumps in paths without resetting the previous anchor; do not infer physical
  zigzags solely from rendered trace. Analysis only, no control/deployment.

### 2026-11-05 — Local and GitHub check-in, grout.19

- User requested all pending changes committed locally and to GitHub. Keep
  local master history and existing independent publication main history at
  output/github-publication/Roomberry; fetched origin/main and verified no
  divergence before refresh. Include GridRunner app, grout/manual/tag-return
  control, pit-stop tooling, tests, mount drawings and accumulated run reports.
- Local commit includes pending runtime/map archives; GitHub snapshot retains
  existing filtering of raw logs/runtime state and local agent instructions.
  Preserve publication-only historical files and legacy frontend assets.
  Add Finder metadata ignore and missing mount-generator SCCS identification.
- Full roomberry_* suite:555 tests passed with local socket permissions.
  Fixed stale steering-pad fixture reference after line-end test rename and
  stale SCAn display expectation; no robot behavior changed during check-in.
  Credential-pattern and file-size reviews clear;49 pending source files have
  one SCCS ID each. Source whitespace checks clear. Generated SVG/CSV whitespace
  retained as emitted. No robot deployment or motion performed.

- Main check-in completed: local e852ff1; GitHub publication94af033 pushed to
  PreussLabsLLC/RoomBerry26 main. A GridRunner-screen.PNG screenshot appeared
  during final checks; reviewed and included in a follow-up asset commit in
  both repositories. Main source validation remains555/555 tests passing.
