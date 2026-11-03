<!-- @(#)CAPTAINSLOG.md 3.1 2026/11/02 17:40:00 -->
# Captains Log

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
