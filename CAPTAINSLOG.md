<!-- @(#)CAPTAINSLOG.md 3.2.pulse.1 2026/11/12 16:24:51 -->
# Captains Log

### 2026-11-12 — Local and GitHub check-in preparation

- User explicitly requests both local Git and GitHub. Preserve independent
  localmaster and publicationmain histories. Publication checkout points to
  PreussLabsLLC/RoomBerry26; fetchedorigin/main, verified no divergence/changes.
- Scope:Pi3/Mothership phone setting,CoreMotion diagnosticstream/comparison,
  maptrails,mount/tag15surveyupdates,scanpacing,30degreepad,42mm/sfloor,
  IOtimedshortpulses,exactspeechtranscript,tests/docs and accumulated analyses.
  Local includes pendingruntime/maparchives and toolbackups. GitHub follows
  existing filteredsnapshot policy: exclude runtime logs/state,local agent
  instructions/credentials; retain reports and publication-only historicalfiles.
- Validation:752fulltests passed plus33focused speech/battery/scan/webtests;
  signediphonebuild and wirechecks previouslypassed. All244pendingfiles
  reviewed:sourceSCCSidentitiesexactlyone,credentialpatternscan clear,
  whitespace checks acceptgeneratedCSVCRLF. No robot/app deployment.

### 2026-11-12 — Exact speech transcript for phrase review

- User asks to log Rosie's speech for clarification. SpeechSender logs exact
  JSON-quoted text atqueue andonce-per-job deliveryattempt, including direct
  batteryreminders. SharedIDs join text to accepted/completed/failed/dropped
  delivery records. Job snapshots retain text through state changes.
- Transcript records speech_announceFalse; tests verify no recursive speech,
  escaped multiline/custom text, directbattery path and deduplicated retrylog.
 33speech/battery/scan/webtests pass after change. Pi-only; no phone rebuild.

### 2026-11-12 —42mm/s minimum and100ms tag-homing pulses

- User requests no wheel speed below42mm/s, shorter pulses instead. Shared
  wheel_speeds floors each nonzero explicitvelocity target to42,preserveszero
  andsign, validatesfinite/max500. Applied atarbiter including ramps/steps;
  padturns use42. Minimum proximity waypoint motion aligns before straight
  advance; footprint checks use actual normalized speeds. PWM/firmwareowned
  autonomous routines do not express explicitmm/s and are not normalized.
- Tag15pivots/search/aim and finalforwardapproach use100msnominal pulses at42;
  IOthread deadline brakes independently of200msmissionloop. Queuewaitbounded
  bydeadline,checkedbeforecommands/afterpolls; serialblocking can still delay.
  Stops/safetycancel deadline; pulsedcommands bypassramp. Longtransit50retained.
- Fresh quiet encoder samples required betweenapproachbursts;1.5ssettletimeout
  andthreeempty-pulse abortretainboundedstalls. Afterpulse/reversal return/
  approach need5degnewerror;2degonlycontinuingdirection/search/aim. Existing
  scansafety/leases/travel/300mmvalidation retained. No automatic reapproach
  after rejectedtagfix. Controlversion3.2.pulse.1,statusminimum/pulseactive.
-752fulltests pass(97.9s),226focusedmotion tests pass. Coverageincludesserial
  floor,rampzero,IOdeadlinewithoutmissiontick,stops,durationbounds,measured
  settling,stallabort,reversalhysteresis. Updatedoldconfiguredtag15testY1225.
- Docsroomberry/docs/short-pulse-motion.md. Syncnewwheelmodule/control/mission/
  tagreturn/manualstep/server/speech toPi3andrestart. NoPi/appdeployment or
  hardwaremovementperformed; physicalpulse/overshoot verification pending.

### 2026-11-12 — Tag15 approach rocking and speed mismatch

- User observed back/forth during152528run approach. Commands alternate
  opposite40mm/spivots/settles,forward20mm/s; no straight reverse commanded.
 35steadythree-sample windows: encoder centre speed p10/median/p90
 39.36/41.60/44.95mm/s at20requested,confirm low-speed mismatch.
- Stopdecision15:29:06.439 error+1.89deg→-4.68degsettled. Gyro+2.11deg and
  AR+2.01deg physical rotation afterdecision; full6.57deglog swing includes
  cached sensor/decisiontiming. Oppositeexamplegyro-2.51deg. Pivot guard
  prevents reversing before quiet but does not eliminate overshoot/hunting.
-5degentry/2degcontinuing threshold plus200msloop and coast produce repeated
  corrections; some reversals inherit tighter threshold. Diagnose/calibrate
  speed and earlierbrake/shortpulses before changing gains. No runtime edits.
- Notes:output/imu-roundtrip-20261112-152528/approach-rocking.md.

### 2026-11-12 — First full gyro/AR/wheel/tag comparison

- Run152528:4419ARnormal/4420validIMUpackets,no sequence gaps;onegeneration,
 3repeatIMUtimestamps deduplicated(4417samples). MedianIMUage11.7ms,p9520.8ms;
  median4ARfeatures. Initialtag16onlyalignment;8.739m wheeltravel.
- Finaltag16positionerrors: wheel12mm,gyroheading+wheeldistancehybrid15mm,
  AR821mm. Headerrorswheel+6.46deg,gyro+0.91deg,AR+0.77deg. Tagfinal9.2mm
  fromstart,heading-5.39deg. Hybrid isoffline,not an independent IMU position.
- AR/gyroheadingabs p951.00deg,max1.60deg;wheel/gyro p954.71deg,max5.70deg.
  Eleven30degwindows wheel328.04degvsgyro318.92deg,medianexcess.66deg/turn.
- Tag15accepted Ywithin25.4mmof1225line;ARposerror1.03–1.24m,wheel154–262mm,
  hybrid90–240mm. Good heading butremainingARdistanceissue. No scale fit.
-17scans/warm2.955s,detect.289s;zero serialpoll/writefaults. Battery88→85.8%.
  Finaltag15range393mmoutside300,safelyrejectsarrival. No runtime changes.
- Full report/frozenconfig/log evidence, reproducible mixedtype6/7analysis,
  metrics/CSV/map/PNG/PDF:output/imu-roundtrip-20261112-152528.

### 2026-11-12 — Tag15 moved to centre grout Y1225mm

- User physically relocates tag15 to Y1225mm for easier measured camera/wheel
  alignment. Updated surveyed world_from_tagY0.790→1.225m; X7730mm,height160mm,
  facing-X and all other landmarks unchanged. Updated config note/mount doc.
- JSON and landmark-diff checks pass; historical recordings/replay configs
  preserved. Pi sync/restart needed; no remote changes or robot commands.

### 2026-11-12 — Motion comparison build installed on iPhone X

- User requests deployment. USB discovery confirms Peters10/iPhoneX,
  ab151810c534a3ffe07756d271a25095fe25e5d2,iOS16.7.16. Sputnik also visible
  overWiFi but not selected. Signed RoomTrek3.2.imu.1 from/tmp/RoomTrek-motion
  installed viaUSB;100%InstallComplete at15:20. No uninstall/data reset.
- CoreMotion type7sender now installed; Pi receiver/web updates still require
  user sync/restart. Device motion signs/physical streaming not verified here.

### 2026-11-12 — Independent Core Motion comparison and30degree pad turns

- User requests independent IMU comparison; then steering additions clarified
  from15to30degrees. RoomTrek3.2.imu.1 requests50HzCoreMotion with arbitrary
  yaw/gravityvertical reference. Type7at10Hz carries native attitude,processed
  gyro,useraccel,gravity and integrated vertical gyro rotation; local2Hz events.
  Sensor failures/gaps reset generation,ARunavailability does not stop raw IMU.
- Pi validates/orders/records type7andexportsCSV. Fresh same-session AR and
  wheel pairs within150ms provide relative gyro/AR/wheel turns and differences.
  New session,generation,wheel epoch resets baseline. Web Turn comparison
  hides stale/unavailable values; diagnostic failures isolated from control.
  No compass/position integration or steering fusion introduced.
- Addedpadleft+30/right-30 beside5/15,backendroutes/catalogue and measured
  step targets. Existing braking,safety,motionlease/cancellation unchanged.
-746fulltests passed(96.9s);166focusedmission/motion/steering/web pass.
  Swift integration checks pass for rotated gravity axes,roll rejection,gaps;
  Swiftfixture decodes inPython. Unsigned/signediphoneosbuildspass,JSCore
  syntax,plist,whitespace/SCCSverified. Hardware signs/drift stillunverified.
- Signedapp /tmp/RoomTrek-motion/Build/Products/Release-iphoneos/RoomTrek.app;
  details/type7layout inios-app/RoomTrek/NAVLINK.md,verificationnotes/fixture
  output/motion-comparison-20261112. No phoneinstall/Pisync/robotmoves performed.

### 2026-11-12 — Forward mount round trip analysis

- Run143842: live mount(-66,-58),yaw0,pitch20confirmed.5731packets allnormal,
  no gaps,median3features. Repeated initialtag16stable within0.6mm; final
  tag16chosen aftertag15, not the second initial scan35.98safterfirst.
- Finalclose tag15 phone1351mm/-11.29deg,wheel445mm/-3.38deg. Returntag16
  phone371mm/-4.81deg,wheel356mm/+2.75deg. Phone/wheelheadingp958.16deg,
  max8.80deg; improveddirection but persistent substantial translation issue.
-16forward500mmsteps phone/wheel advance ratios29–82%,median57%; tag15
  also showsphone short. No constant scale fit justified. Need measured1m
  straight test with texturedview; normaltracking does not establish accuracy.
-12scans,warm2.973s,detect.319s; startupwrite timeout14:38:43.926beforefirst
  scan,none later. Battery99.3→96.7%. Tag15arrival382mm outside300mm.
- Frozen config/log evidence,analysis,metrics,straightsteps and plots:
  output/forward-mount-20261112-143842. No runtime/config changes.

### 2026-11-12 — Replacement forward-facing phone mount

- User changes phone mount: lensX-66mm,Y-58mm,straightforward,20degup.
  Active roomtrek_alignment now lens(-66,-58),yaw0,pitch20. Robot axes mean
 66mmback/58mmright. Pi camera extrinsics and scan resolution unchanged.
- Updated config and mount documentation. Sync/restart/new stationarytag16
  anchor required; no iPhone build or deployment performed.

### 2026-11-12 — Pi3 versus Zero W scan timing and resolution review

- Same820x616/500msgap pacing: ZeroW warmmedian6.58s/cold16.23s versus
  Pi3warm2.974s(range2.859–3.048)/cold4.483s.13Pi3scans,12warm.
- Older ZeroWposter stage medians detect2.85s/archive.69s versusPi3
 .303/.037s. Pi3native.267s; deliberate1ssettle+three.5sgaps dominate.
  Software/nativepose bindings changed too; not a controlled CPU-only test.
- Recommend staged1296x972capture ANDmax_dimension1296, keeping
  highest_resolutionfalse.2.49xpixels; estimated3.5–4swarm, unbenchmarked.
  Fullsensor mode unmeasured;10sdetector timeout retained. No config changes.
- Frozen Pi3timing evidence,metrics,comparison and notes:
  output/pi3-scan-timing-20261112/report.md.

### 2026-11-12 — Replayed map using measured mounts

- User requests map.png update and measurement sensitivity. Replayed122222
  recorded paths; recomputed full-matrix initial/finaltag16 and idle tag15
  poses with new Pi extrinsics. Rebound phone initial alignment with measured
  lens/yaw, freewheel with updatedtag16. No scale/path fitting or runtime changes.
- Pi tag positions shift25–27mm. Phone path rotates+10deg with yawrevision;
  tag15 midway error1029→782mm,finaltag16 175→157mm. Wheel final925→926mm.
  Offset-onlyrevision38mm gives at most76mm initial-alignment error change;
  yaw dominates (1deg at4m≈70mm). Residual discrepancy still substantial.
- Updated prior run map.png link, preserving map-before-remeasurement.png;
  new map/before/after PNG/PDF, frozen-input replay script,metrics and report in
  output/pi3-mount-replay-20261112. Old analysis metrics/CSV untouched.

### 2026-11-12 — Remeasured phone and Pi camera mount settings

- User measures phone lens202mmleft,21mmback,optical30degleft. Active
  roomtrek_alignment now lens(-21,202)mm,yawcorrection-30deg. Unremeasured
  pitch15deg retained; disabled legacy phone_position untouched.
- Pi lens centred laterally,148mmforward,137mmhigh. Retained forward-facing
  rotation; camera_from_robot translation(0,+0.137,-0.148)m, derived as
  minusRtimes camera centre(0.148,0,0.137)m. Prior translation(0,.160,-.125).
- Validation:29localization/anchor tests passed; JSON, transform origin/signs,
  SCCS and whitespace verified.
- Updated autonomy.json and roomtrek-alignment.md. Sync/restart Roomberry and
  new stationary tag16 anchor needed; no phone rebuild or deployment performed.

### 2026-11-12 — Pi3 round trip and mount sensitivity reviewed

- Run122222: active fresh session4991packets,4initializing/restnormal,no gaps;
  previous223loaded-map packets excluded.13scans median2.976s/detect0.304s,
  no run-time poll/write faults. Battery97.8→95.5%;9.444m wheel travel.
- Close tag15 phone1145mm/-11.72deg versuswheel241mm/-24.95deg; finaltag16
  phone175mm/-5.25deg versuswheel925mm/-9.75deg. Initial/finaltag86mm/+0.10deg.
  Returnturn matchingwindows wheel131.15/74.20deg,phone128.73/72.74deg: only
 2.42/1.46deg differences, not a wholesale turn-heading failure.
- Active lens10forward/180left, optical20left, yawcorrection-20. Disabled old
  phone_position values do not apply. Diagnostic yaw-only fit still847mmRMS;
  lens-only fit needs implausible775mmrear/326mmleft. Similarity fit1.299scale
  is diagnostic, not a correction. Asked for physical lens/mount measurements;
  no configuration adjusted to force agreement.
- Rightbumper12:25:56 stops firsthoming; retry finaltag15range379mm outside300.
  Report/plots/reproducible analysis output/pi3-roundtrip-20261112-122222.

### 2026-11-12 — Pi3 first uploaded run: map resume and missing detector

- NavLink/authenticated map controls/speech work.1569type6packets;365normal
  fresh-session packets. WALL12:03:28 stops that session and resumes selected
  map11CEE584-D76D-4B69-B3AF-2FE1C804BB7C; ARKit remains relocalizing.
 30s timeout then one same-map retry; SURVEY_START:Session stopped12:04:22,
  WALLabort0mm. Map mismatch cause not established, not a transport outage.
- Scan12:04:48 captures image but worker cannot import required
  from apriltag import apriltag; detector unavailable on new Pi. Failure spoken.
  Missing/wrong binding or native import dependency unresolved; no image/tag
  quality conclusion possible. Tag localization does not restore AR map lock.
- Zero write timeouts; startup0/1byte retry and16/80byte sensor short read.
  Report output/pi3-startup-20261112-120250/report.md. No runtime changes.

### 2026-11-12 — Mothership build deployed to iPhone X

- User requests deployment to connected iPhoneX. USB confirmed Peters10,
  iOS16.7.16, deviceab151810c534a3ffe07756d271a25095fe25e5d2.
- Signed Release iphoneos build succeeded at /tmp/RoomTrek-mothership-signed;
  ios-deploy USB installation completed100%/InstallComplete at11:54.
  Installed RoomTrek3.2.mothership.1, defaultpi3.local and saved Mothership
  field. No app uninstall/data reset or Pi commands; live reporting unverified.

### 2026-11-12 — RoomTrek Mothership setting for Pi3 (3.2.mothership.1)

- User upgraded ZeroW to Pi3, hostname pi3/pi3.local. Relabeled the existing
  app host field as Mothership, default pi3.local; saved via UserDefaults
  navlink.mothership on Done/end editing, restored across launches. Accepts
  hostnames/IPv4, trims surrounding whitespace, rejects URLs/paths/ports;
  invalid input restores the last saved setting with an explanation.
- UDP5010 unchanged; endpoint applies to telemetry, heartbeat and control
  replies. Configuration changes/reconnect execute on transport's serial
  queue; status displays the actual selected host. Bare pi3 retains existing
  .local fallback. Editing remains disabled during an active AR session.
- Validation: unsigned Release iphoneos build succeeded (Xcode14.2/SDK16.2);
  whitespace and SCCS checks passed. Device/network verification still needed.
- Updated visible build identity and app README. Existing keys/map library
  retained; no Pi deployment or iPhone installation performed.

### 2026-11-10 — Half-second-gap uploaded run reviewed (3.2.analysis.4)

- Run135820: one write timeout14:01:23.312 requesting buttons18 during scan,
  followed GridRunner stale/safety abort. Traceback mentions timeout twice,
  only one event. Startup0/1byte retry and separate72/80byte short read.
- Twelve scans/speech completions;500ms gaps confirmed, warmmedian6.581s,
  cold16.227s. Both live-map trails confirmed in actual archived PNG.
-5434phone packets allnormal,1gap; initial phone/tag16 alignment succeeds.
  Offline final error: phone407mm/-3.87deg,wheel317mm/+12.25deg.9.061m travel.
  Retried tag15 validated340mm outside300mm and safely stopped again.
- Charge estimate99.7→62.4% in126ms with unchanged14.667V, finish60.5%.
  Whole-run current integral58.3mAh versus reported1064mAh drop: physical
  discharge alone cannot explain it. Recalculation versus corruption unknown.
- Report, reproducible analysis and plots:
  output/roundtrip-halfgap-20261110-135820. Read-only runtime review.

### 2026-11-10 — Half-second scan gaps and current-run map trails (3.2.trails.1)

- Reduced all three stationary scan cool-off defaults from1s to0.5s, both
  standalone camera service and server configuration fallback. Initial1s
  settling wait remains; expected saving1.5s per scan. Existing explicit
  camera.scan_cooloff_seconds overrides still apply.
- Added diagnostic RunTrails, first accepted stationary tag16 seeds wheel
  integration and qualified phone capture pairing with configured mount/lens.
  Independent wheel/phone trails continue through idle/manual/missions and
  coverage resets; later tag fixes do not refit drift. Phone tracking/session
  gaps break the line; wheel epoch changes require a new tag16 anchor.
- Mapper snapshots expose ephemeral run_trails; map.png and archived PNGs
  render blue/red wheel and purple iPhone lines with legend. Old saved traces
  hidden when current-run traces exist; clipping protects axes from drift.
  Incremental trace publication avoids copying the entire path each tick.
- Preview of uploaded133352run at
  output/roundtrip-cooloff-20261110-133352/map.png; analysis script regenerates
  it. Navigation/safety policies unchanged. No Pi deployment or phone build.
- Focused182tests passed;19render/trail tests passed after clipping change.
  Full suite738tests passed (113.6s), with local-socket access outside the
  sandbox. SCCS and whitespace checks passed.

### 2026-11-10 — Uploaded cool-off round trip reviewed (3.2.analysis.3)

- Run133352: 5130phone packets all normal; one sequence gap,9.377m wheel
  travel. All12scans announced clear mapped tag results and completed speech.
  Three1s gaps executed each scan; cold17.535s,warmmedian7.924s.
- No scan-time poll failures. One64/80byte short read13:41:33.196 preceded
  final scan by14.655s; left15 refusal13:41:31 due sensor/safety readiness.
  Roomba92.2→90.1%, no charge collapse. STATUS completion after30s quiet
  consistent with battery reminder; words/phone percent absent in delivery log.
- Initial-only offline tag16 alignment: final tag38mm/-3.95deg from start;
  phone error705mm/-1.37deg; freewheel124mm/+20.88deg. Phone tag15 position
  error0.96–1.30m, heading-12to-19deg despite all-normal tracking.
- Tag15 accepted final pose validates351mm robot-centre range, outside300mm;
  safe stop warning persisted. Spoken245mm is camera range, distinct origin;
  final pose innovation83mm. Not a completed autonomous arrival.
- Analysis, CSV, metrics, PNG/PDF and report under
  output/roundtrip-cooloff-20261110-133352. Raw logs preserved; no runtime,
  controller, deployment or app changes.

### 2026-11-10 — Local check-in of pending RoomTrek work

- Reviewed the pending map controls, survey preservation, WALL readiness,
  steering, battery and scan speech, scan timing, and associated run reports
  and map archives for local Git check-in at the user's request.
- Validation: 734 Python tests passed; Git whitespace checks passed. Source
  identification lines verified; generated browser HTML snapshots are exempt.

### 2026-11-10 — Scan-stage cool-offs and spoken tag-read quality (3.2.scan.2)

- User requests scan timing detail,1second gaps, confirms single-core/GIL
  concern, and asks Rosie to speak scan results/quality. Detector already uses
  spawned process (preprocessing/native detect/pose); capture/archive remain
  parent camera worker. GIL separation does not add CPU capacity on one core.
-125752run warm medians: pause/feedback0.141s,settle1.007s,capture0.093s,
  detector call2.854s,JPEG0.693s,total5.002s. First scan17.804s, detector call
 15.777s versus child-measured2.185s/native2.050s; unmeasured difference can
  include startup/IPC/scheduling and does not prove CPU-caused UART faults.
- Camera adds1s cool-off after capture, after detection, and after archiving
  before result publication/scan release. Existing1s pre-capture settle stays.
  Shutdown-event waits execute outside camera/detection/mission locks, with
  scan/motion guard held and independent polling active. Interrupted results
  never publish/speak; cleanup still releases scan guard. Moving skipped scans
  get no added waits. Default camera.scan_cooloff_seconds=1.0,0restoresoldpacing.
  Expected warm~8s/cold~21s; unchanged scan deadlines, physical benefit untested.
- Completed scan queues existing authenticated SPEAK with SCAN_RESULT: tag ID,
  camera-to-tag centimetres, clear/marginal/weak/unavailable quality. Uses
  configured margin/pose-error thresholds and zero corrected bits. Best
  duplicate read wins, up to2readable tags, mapped preferred. No tags, weak-only,
  skipped moving scans and detector failures spoken explicitly. Labels describe
  detector reads, not localization/AR-map confidence. Existing speech priorities,
  stale drops, delivery logging and30s battery silence timer retain their rules.
-26focused camera/scan-speech/catalogue tests and all734full-suite tests pass
  (101.3s). Tests cover stage ordering, held guard/free locks during waits,
  shutdown at every gap, no premature publication/speech, callback failure
  isolation, quality/range/mapped selection and queueing. Whitespace/SCCS pass.
- Docs roomberry/docs/tag-scan-pipeline.md; verification notes in
  output/scan-cooloff-speech-20261110. Pi sync/restart roomberry.py,
  roomberry_camera.py and roomberry_speech.py; existing iPhone SPEAK supports it.
  No robot/scan commands, Pi deployment or phone rebuild/install performed.

### 2026-11-10 — Poll-timeout correlation with tag scans (3.2.analysis.2)

- User asks whether timeouts coincided with scans. Twelve scan start/complete
  windows in the125752run. Six of seven poll failures occur12:58:00.261 through
 12:58:05.571 during initial tag16 scan12:57:59.165–12:58:16.942 (17.777s).
  Display serial write also times out12:58:02.870 during that same scan.
- Seventh poll failure13:01:14.729 occurs3.061s after tag15 scan completes
 13:01:11.668, following confirmed pose11.810, while encoders/wheel requests
  remain stationary until13:01:17. Other eleven scan windows (4.3–5.6s) contain
  no poll failures. Exceptions are serial Write timeout, not zero-byte reads
  from the earlier reset-related run. Temporal association established;
  scan CPU/IPC/startup or serial I/O contention cause not established by logs.
- Correlation table saved output/roundtrip-poster-20261110-1257/scan-timeouts.csv
  and report updated. Read-only analysis; no robot/camera/app/config changes.

### 2026-11-10 — Poster-door round trip with initial/final tag16 checks (3.2.analysis.2)

- User completes charged round trip with Kandinsky poster near tag15. One
  fresh phone session9855001675563444002:4719packets all normal, no feature-loss
  interval, median18features versus5/33seconds limited on preceding full trip.
  Two packet gaps, one duplicate camera frame. Consistent with poster helping;
  path/turns differ, so causality is not established by this comparison alone.
- Starting tag16 captured12:58:00.654, return13:05:06.319 and13:05:30.394.
  Offline one-time alignment at initial tag16; scale1, configured mount/lens,
  free wheel integration, no later tag corrections/path fitting. No live WALL
  anchor record. Final tag scans agree2.44mm/0.30deg; last tag16 is25mm/+3.23deg
  from first tag16. Initial sparse wheel sampling checked stationary across1.5s.
- At last tag16: phone heading differs+0.66deg from tag pose, wheel+32.52deg.
  Phone heading change+3.90deg versus tag+3.23deg and wheel+35.75deg modulo360.
  Phone position differs520mm from tag, free wheels196mm. Earlier return scan
  independently supports522/197mm and+0.42/+32.21deg. Normal tracking therefore
  supports heading closure but does not establish reliable metric translation.
- Tag15 checkpoints: phone–tag position differences1053–1220mm; free wheels
 98–269mm. Phone–wheel separation peaks1.384m and ends342mm, with possible
  cancellation. Intermediate tag15 heading checks disagree too; endpoint phone
  heading accuracy does not imply uniformly accurate heading along the route.
  Wheel path9.579m. Live tag-corrected navigation is distinct from free odometry.
- Tag15 validation again stops just outside target:354mm centre range versus
 300mm gate. Battery99.9→97.9%; six startup poll write errors before12:58:06 and
  one13:01:14 after stationary tag fix/before homing drive, recovered;19NULbytes in supplied main log
  preserved. No application/config changes, live commands or deployment.
- Reproducible script, PNG/PDF plots, metrics and CSVs in
  output/roundtrip-poster-20261110-1257. Identity/timing/stationary anchor checks
  pass. Report distinguishes tag-derived reference uncertainty and no path fit.

### 2026-11-10 — Early stop: low battery first, serial silence after web reset (3.2.analysis.1)

- User ends test and returns Rosie to charger; read-only log review only.
  Startup12:01:15 reset stream contains processor-sleep; first connection
  attempt12:01:52 receives0/1bytes. Retry connects12:02:14. Tag16 fix accepted
  12:02:37; seven15deg left pad turns complete. Forward500mm step starts12:02:59.
-12:03:02 first low-battery classification and LOW_BATT speech. Charge report
  changes2690→757mAh (99.8→28.1%) between adjacent samples159ms apart, capacity
 2696mAh; voltage/current remain14.194V/−0.594A across that jump. Integrated
  sample current over47.6seconds before transition is~4.8mAh, not1933mAh.
  Abrupt gauge/charge-report change, not literal71.7%discharge in that interval;
  logs do not establish battery health or exact cause of the gauge revision.
-30% low threshold triggers brake and seek-dock request. Forward step stops,
  result~283mm; settled cumulative distance321.4mm. Further steps rejected for
  low battery. Sensor polls remain healthy until12:03:55.382; no during-run
  serial failure precedes the battery stop. No cliff/wheel-drop trigger there.
- Restart OI12:03:34 succeeds; raw Reset Roomba web command12:03:55.864 follows.
  First sensor timeout12:03:58.976, then17zero-byte/80expected failures through
 12:04:49.905. Driver reset sets OI OFF; this route does not perform full
  startup/reconnect. Consistent with reset/off interface rather than evidence
  of a spontaneous serial failure causing the initial stop.
- Phone remains normal for all1486packets in one fresh session (one seq gap).
  No complete round trip/poster comparison. Copied successful sensor rows all
  home_base=0, so later charger placement/charging is not verified by this log.
  After charging, wake/restart Roomberry/OI and wait for fresh Sensors Ready;
  avoid treating a reset-completed HTTP response as restored communications.
- Notes/metrics: output/serial-battery-20261110-1202. No app/config changes,
  deployment, live robot/AR/reset/charging commands or new tests performed.

### 2026-11-10 — Tag15/tag16 round-trip heading and position comparison (3.2.analysis.1)

-11:38:43–11:45:55 recording: one fresh phone session9257763700918216142,
 4320packets,3986normal/334limited-insufficientFeatures, zero seq gaps. Four
  repeated frame timestamps de-duplicated for interpolation. Phone feature
  median5. Lost-feature interval11:42:30.498–11:43:03.794 (~33s) near tag15;
  user confirms featureless door and plans poster. Effect not yet tested.
- No recorded live tag16 anchor. Relative comparison fixes common stationary
  start at11:39:10, scale1, configured dashboard lens/mount, no path fitting.
  Wheel track integrated without tag corrections. First confirmed tag15 capture:
  0.811m phone–wheel separation,−0.20deg heading; peak qualified separation1.112m.
  Tag16 return capture11:45:07:0.442m separation,−5.19deg heading; wheel path9.111m.
  Outbound |heading disagreement| median0.27deg,p95=0.72deg,max1.97deg;
  usable return peak8.64deg. Early501/513mm wheel steps give299/321mm phone
  displacements even with usable tracking; does not establish which is correct.
- Supplemental offline independent first-tag15 alignment (not live calibration):
  later tag15 fixes differ96–138mm from phone/71–153mm from free wheel track;
  final tag16 differs764/783mm and7.78/12.78deg. Tag/camera/mount uncertainty and
  absent initial surveyed pose prevent treating either estimate as ground truth.
- Tag15 final robot-centre range356mm exceeds300mm gate by56mm, so homing stops
  explicitly. Camera range~250mm is not centre range. Back to tag16 is manual.
- Reproducible script, PNG/PDF plot, metrics and CSVs in
  output/roundtrip-20261110-1138. Qualified/stationary baseline checks pass;
  actual tag capture timestamps used. No live commands, deployment or app/config
  changes. Poster may address local feature loss; earlier translation discrepancy
  predates that interval and remains unexplained.

### 2026-11-10 — Additional left/right15degree pad buttons (3.2.pad.1)

- User requests +/-15degree buttons. Added Left+15deg and Right-15deg above
  the existing5degree controls, flanking the forward50mm button. Routes
  step_left_15/step_right_15 use the existing measured wheel-angle step runner,
  same30mm/s wheel speeds, predictive braking, timeout, guards and cancellation.
  Existing5degree and50/500mm controls remain available. Status labels and
  command index include15degree turns; direction display normalized to left/right.
-25focused manual-step/web tests pass, including measured +/-15degree turns
  and route dispatch. Desktop1440px/mobile390px browser checks pass for both
  button clicks, pad locking during commands, Stop availability, no overlaps
  or horizontal overflow. Screenshots: output/steering-pad-15deg-20261110.
  JS syntax, whitespace and SCCS checks pass. No live movement or deployment.
- Pi sync/restart and browser reload required for new backend routes/assets;
  no iPhone update needed. Legacy web-app unchanged.

### 2026-11-10 — Healthy steering survey; tag return blocked by survey guard (3.2.maps.4)

- User reports many happy beeps but refused tag15 approach. Latest11:17–11:22
  log confirms continuous fresh session14180529187437353947 from11:17:48 through
  11:22:26:2778packets,2775normal/3initializing, zero sequence gaps. All pad
  movements preserve that session; no automatic restart/save queue churn.
- Return to tag15 clicks11:21:00 and11:21:53 getHTTP400 from the unsaved-survey
  guard, before homing starts. Pi camera accepts tag15 at11:21:32 (~0.707m camera
  translationZ, not robot clearance), but idle mode has no autonomous target.
  This is a command-policy rejection, not evidence of tag approach failure.
- Narrow fix: independent Tag15Return reports return_to_tag15 to the phone
  lifecycle guard/coordinator while retaining its existing gridrunner robot
  execution mode. It can run with an unsaved kept survey, without AR start/save/
  stop, and preserves the session at idle. WALL/ordinary GridRunner still refuse
  unsaved kept surveys; active map mutations still block all mission starts.
  Sensor/tag-fix/route/odometry/contact guards unchanged.
-61focused tag-return/map/survey tests pass, including actual homing startup
  with unsaved survey, stationary fix qualification before forward movement,
  zero phone commands/jobs through idle, and retained WALL restriction.
  All726full-suite tests pass in100.2seconds; JS syntax/whitespace/SCCS pass.
- Pi-only update: roomberry_mission.py, roomberry_trek_survey.py and web help.
  Sync/restart Pi, reload UI; no phone update needed. No robot movement, live
  AR/map commands, deployment or phone installation performed. Notes/metrics:
  output/roomtrek-tag15-20261110-1117.

### 2026-11-10 — Steering-triggered AR restart churn; preserve phone by default (3.2.maps.3)

- User reports happy beeps becoming sad after moving; updated11:02–11:11 logs
  show fresh session13744358242786495527 normal for630packets until11:03:38.
  First5degree pad turn enters remote_control, queues automatic start, stops AR
  and resumes old seed11:03:39. Subsequent pad remote/idle transitions fill the
  lifecycle queue; queued start/save/stop jobs keep changing sessions afterward.
  Cached live panel has no map job/kept survey, consistent with no console
  adoption after this Pi restart. Prior fix required explicit fresh/Keep action.
-19phone sessions,4559packets,31valid localized packets in six brief matches.
  Four successful child saves at11:04:52,11:04:58,11:05:12,11:09:39 (revisions2–5).
  Later starts repeatedly resume revision5,11CEE584-D76D-4B69-B3AF-2FE1C804BB7C.
  This is no longer evidence of zero map matches. Restart churn prevents a
  clean continuous-session test of whether movement itself loses tracking.
- Manual mode from idle now never starts the automatic phone lifecycle, even
  without Keep or after Pi restart. Pad moves/idle leave a running phone session
  untouched and cannot fill the survey queue. Explicit console fresh/Keep still
  adds unsaved-survey mission protection. Autonomous mission behavior remains;
  manual takeover ends the existing automatic survey once at idle, with no new
  survey on subsequent pad steps. No default camera start during manual mode.
-46focused map/survey/pad tests pass, covering actual four-direction moves
  without Keep,100rapid remote/idle pairs with zero jobs/phone commands, and a
  single save boundary for manual takeover. JS syntax, whitespace/SCCS checks
  pass. Notes/metrics: output/roomtrek-steering-20261110-1102.
- Pi-only change and web help update; sync/restart Roomberry to clear old queue,
  reload console. No phone rebuild needed. No live robot/AR commands, map
  changes or Pi deployment performed. Cached status read only.

### 2026-11-10 — Limited-mapping save blocker and preserved survey steering (3.2.maps.2)

- User reports grey Save survey. Read-only live Pi inventory refresh confirms
  running fresh Surveyor, tracking2:0(normal), world mapping limited,
  can_amend=false, no operation error. The save gate is working as implemented;
  normal tracking alone does not qualify for a map save. Exact mission override
  remains null/automatic old seed. No live selection/survey/motion changes made.
- Found mounted-phone workflow gap: pad moves enter remote_control/idle, which
  previously replaced the fresh survey through automatic mission start/save.
  Fresh/resume console sessions now keep explicit operator ownership. Pad and
  Stop/idle transitions retain AR without start/stop/save commands. New Keep
  current survey for steering adopts an existing Surveyor without restarting it.
  Ownership is not restored after Pi restart without explicit adoption.
- Unsaved kept surveys refuse autonomous starts before robot commands. A
  verified save or explicit Stop phone session permits normal mission lifecycle;
  selection still explicitly chooses the next mission UUID. Existing measured
  pad movements, sensor guards, stops and leases unchanged. Strict phone save
  qualification unchanged; movement does not guarantee sufficient coverage.
- Panel now identifies connection/idle/session/mode/error/mapping/tracking save
  blockers and shows survey steering ownership. User refreshes phone snapshots
  after collecting viewpoints; automatic refresh remains off.
-44 focused map/survey/steering tests pass, including actual four-direction pad
  fixture with zero phone commands during movement/idle and no lifecycle queue
  entries. Desktop/mobile browser simulation verifies limited save disabled with
  exact reason, Keep adoption, and save enabled after extending coverage.
  All722full-suite tests pass in103.3seconds. SCCS/whitespace/JS syntax checks
  pass. Verification notes: output/roomtrek-save-readiness-20261110.
- Pi/web-only update: roomberry_trek_survey.py, roomberry_trek_maps.py,
  web/index.html and web/maps.js, plus tests/docs. Pi sync/restart remains
  user-owned; existing installed RoomTrek3.2.maps.1 supports it. No phone build,
  install, deployment or robot movement requested/performed for this fix.

### 2026-11-10 — Web tests: happy beeps followed by old-seed relocalization (3.2.maps.1)

- Latest supplied10:43–10:47 logs show fresh web survey10:45:11; after seven
  initializing packets,232normal-tracking packets until10:45:34. Web Start WALL
  at10:45:34 explicitly stops that survey and resumes old kitchen seed
  0B2FA89D-F7EA-4002-9AC7-92C32AF1D0D5 at10:45:35. Both30s attempts fail;
  WALL aborts10:46:36,0mm travel. Earlier10:43 WALL also exhausts two attempts.
- No successful save or next-run selection action appears in supplied log.
  Fresh session was replaced by mission startup, not observed to lose tracking
  spontaneously.1417loaded-map packets: all limited, no localized validity,
  zero within-session gaps.391fresh packets; fresh medians3visible features.
  Sparse features do not establish saved coverage or root cause of mismatch.
- Recommend idle fresh survey, save once coverage permits, explicitly Use for
  next run, verify displayed UUID/name before WALL. Happy tone alone is not a
  saved-map match; stopped sessions also produce attention pings.
- Report/metrics output/roomtrek-web-tests-20261110-1043. Phone log listing timed
  out inside/outside sandbox; exact phone beep events unavailable. No source,
  configuration, deployment, map-selection or movement commands performed.

### 2026-11-10 — RoomTrek map-controls build installed on iPhone X (3.2.maps.1)

- User explicitly requests deployment to connected iPhone10. ios-deploy identifies
  Peters10, iPhone X, iOS16.7.16, USB device ab151810c534a3ffe07756d271a25095fe25e5d2.
  Installs /tmp/RoomTrek-maps/Build/Products/Release-iphoneos/RoomTrek.app;
  exit0,100% InstallComplete/Installed package confirms installation.
- Installed build headline3.2.maps.1 2026/11/10 10:15:00. No uninstall/data wipe,
  map changes, AR start or robot commands issued. User should open RoomTrek and
  keep it foreground. Pi sync/restart remains outstanding/user-owned.

### 2026-11-10 — Mounted-phone web map controls and 30-second battery reports (3.2.maps.1)

- Added RoomTrek maps panel to existing roomberry/web console, leaving legacy
  web-app untouched. Lists all readable phone maps with storage/revision/quality
  metadata and shows active phone session separately from next mission choice.
  Fresh/resume/stop/save/rename/delete and exact next-run UUID selection work
  through asynchronous JSON jobs and the existing authenticated loopback relay.
- Exact mission choice persists atomically in logs/roomtrek-map-selection.json,
  overrides bootstrap/automatic choice and survives Pi restarts. Missing/corrupt
  overrides fail explicitly; the web console can replace a corrupt selection.
  Automatic selection remains available. Save verifies returned UUID/name;
  rename/delete verify library result. Unknown outcomes are not blindly replayed.
- Map mutations require robot idle and a drained mission survey lifecycle.
  Reservation shares mission coordinator lock; Clock/web starts are rejected
  before motion while a mutation is busy. Stop remains available. Worker holds
  survey operation lock for whole job; read-only refresh may run during missions.
- Phone advertises map_library_v1 and adds paginated MAP_LIST, MAP_RENAME,
  MAP_DELETE. Page inventory revision guards against intervening library edits.
  Local/remote deletion refuses active AR parent; filesystem errors now surface.
  Pi refuses deleting effective mission selection/seed until another is chosen.
  No cascade deletion, archive transfer or automatic frame reset.
- User requests battery reports after30seconds without speech. Existing speech
  worker announces fresh Roomba charge/capacity and iPhone battery/charging state
  from challenge-verified heartbeat. Runs only with free speech queue; resets
  quiet timer on acknowledgment/completion. Missing readings explicit; no report
  if both missing. Failed attempts throttled30seconds; beeps do not count.
-718 full Python tests pass in104.4s; final13 focused map/battery checks pass,
  including corrupt selection recovery. Swift authentication/replay/command
  checks pass. Signed Release iPhone build succeeds at /tmp/RoomTrek-maps.
  Desktop1440px/mobile390px browser simulation passes fresh/save/select/rename/
  resume/stop/delete, deletion protection, escaped names and no horizontal
  overflow. Screenshots and browser artifacts in output/roomtrek-map-controls-20261110.
- Docs updated. App headline3.2.maps.1 2026/11/10 10:15:00. Both Pi service and
  phone app need updates; existing sync-up includes modules/web assets. No Pi
  upload, phone installation, live map change or robot movement performed.

### 2026-11-10 — Daylight startup and Delete Selected investigation (3.2)

- Supplied 09:54/09:58/10:00 WALL starts all fail before departure. Loaded-map
  sessions never reach normal tracking/localized validity; fresh sessions do
  reach normal tracking. Loaded packet sequences continuous, median ages55–73ms.
  Daylight did not resolve saved-map recognition; lighting alone insufficient.
- User deleted selected map during run. Delete Selected removes library file
  without stopping/clearing active AR map; selected row can differ from remote
  surveyParentID. Deletion errors ignored. Cannot establish actual deleted ID.
- Coordinator pins configured kitchen seed when no child revision exists,
  even if absent from inventory. Library deletion does not request fresh WALL;
  deleted seed would cause map-load failure on later start. These logs instead
  show relocalization timeouts. Recommend idle local fresh Surveyor diagnostic
  before any explicit seed-policy change. No automatic coordinate-frame reset.
- Report/metrics: output/roomtrek-daylight-20261110-0954. Read-only iPhone log
  listing timed out; no phone events available. No source/config changes,
  deployment, AR commands or movement; existing pending edits preserved.

### 2026-11-09 — Local and GitHub check-in, 3.2 tag

- Pending WALL work checked in locally and on GitHub (publication
  `output/github-publication/Roomberry`): wall.14 20-30 IR band +
  fluctuation hold, wall.15 corner go-around (20deg-first, follow
  contact after wall loss), wall.16 5000mm tag15_scan + 8 searches +
  360s, tag15 y 1.237 to 0.79m (autonomy 3.1.posgate.2), plus wall-run
  reports 221411/223448/092328/094542/100017/101115 and map archives.
  Publication keeps runtime-log/local-agent exclusions.
- Start new version: tag 3.2 marks this check-in as the base for
  upcoming work. Next builds will use 3.2.* numbering.
- Local commit on master; publication main fetched origin/main,
  verified clean, copied source files, committed and pushed to
  PreussLabsLLC/RoomBerry26. No robot deployment or motion.

### 2026-11-09 — Extend 1.5m past fridge and tag-15 scan at 5m, wall.16

- Tag 15 moved to the same y as tag 16 in roomberry/autonomy.json:
  y 1.237 to 0.79m (x 7.73, z 0.16 kept), so it is in view when
  following the wall. Approach waypoint is now (7230, 790)mm;
  mission tests updated. Autonomy SCCS bumped to 3.1.posgate.2.
- 101115 run (wall.15) travelled 3575mm in 170s with three bypass
  contacts, then stopped at 10:14:16.069 with `wall-loss search limit
  reached`. Follow 340 samples, rejoin 147, encoder to 2357mm, last
  heading 121.09deg. Go-around fired as designed (left 20 at 41.24deg,
  then 90deg twice) and swept around the fridge front, reaching almost
  past the fridge. Fluctuation holds fired 8 times. Report and
  telemetry at output/wall-run-20261109-101115/.
- Trial extended to total 5000mm travelled (about1.5m past the ~3.5m
  fridge point). Wall-loss budget raised 4 to 8 and whole-run time
  240s to 360s; 6m distance bound unchanged. At >=5000mm in follow,
  mission transitions to `tag15_scan` (stopped, request scans every
  2s) and finishes complete after two consistent tag-15 fixes
  (75mm/0.1rad). `scan_pause` now allows WALL scans in anchor and
  tag15_scan, targeting tag16 or tag15. Operator moved tag 15 to the
  same y as tag 16 so it should be in view while following.
- Focused WALL tests 48/48 passed (including new 5000mm/tag15 scan
  tests); mission 133/133, control 47/47 passed. Whitespace and
  exactly-one SCCS checks passed; legacy web-app untouched. Local
  only; sync wall/control/mission modules over wall.15, restart and
  verify 3.1.wall.16. No deployment or robot commands.

### 2026-11-09 — Go-around on corner bump after wall loss, wall.15

- 100017 run (wall.14) travelled 2317mm with two right-bumper contacts
  and four wall-loss searches, then stopped at 10:02:19.996 with
  `wall-loss search limit reached`. It followed to 80.94deg, did four
  right sweeps (66.5, 73.25, 24.75, 31.5) facing the dishwasher front,
  and hit the cabinet corner twice in follow (10:02:03, 10:02:12,
  `next_left_deg=15`). Go-around never triggered because it requires
  detour or contact in a `wall_loss` rejoin; both contacts were in
  follow, so they were treated as ordinary 15deg side bumps and
  re-hit the same corner ~22mm later. Final heading 41.6deg facing the
  dishwasher. Report and telemetry at
  output/wall-run-20261109-100017/.
- Follow contact within 500mm travelled after a wall-loss search now
  starts the bounded go-around (20deg first, 90deg on repeat) like a
  wall-loss contact, so a head-on corner bump goes around instead of
  burning wall-loss searches face-on. `last_loss_mm` tracks the search
  start; isolated side-wall contacts keep 15deg. Doc updated.
- Focused WALL tests 46/46 passed (including new corner go-around
  tests); mission 133/133, control 47/47 passed. Whitespace and
  exactly-one SCCS checks passed; legacy web-app untouched. Local
  only; sync wall/control/mission modules over wall.14, restart and
  verify 3.1.wall.15. No deployment or robot commands.

### 2026-11-09 — Twenty-to-thirty IR band and fluctuation hold, wall.14

- 094542 run (wall.13) travelled 3893mm in 300s with 27 contact
  recoveries but only one wall rejoin, then stopped at 09:49:51.824 with
  `time limit during rejoin`. It never reached the fridge, spending 497
  samples in rejoin, 185 in release, 164 in contact_left and only 92 in
  follow, looping at encoder ~1350-1505mm (back 32-36mm, left 15deg,
  right 5deg/30mm advance, contact again). Follow IR was 13.5-53.2
  (mean 33.5) with 15.5 max jump; rejoin IR averaged 19.1 over 497
  samples with only 5 samples >=30 but 163 >=20. Report and telemetry at
  output/wall-run-20261109-094542/.
- Single 30-unit chase replaced by a 20-30 deadband (centre 25):
  acquisition/rejoin/bypass-handoff now qualify at >=20, steering drives
  straight inside 20-30 and otherwise tracks the centre. Logs/comments in
  wall.13 claimed 30-only behaviour; status now exposes target_min/max.
- If the latest four raw IR samples spread >20, follow now stops,
  records `wall_signal_fluctuating`, and holds stopped for 1s to collect
  fresh stationary samples before resuming, rather than steering on the
  fluctuation. The 180s follow deadline still bounds holds.
- Focused WALL tests 44/44 passed (including new band/hold tests);
  mission 133/133, control 47/47 passed. Whitespace and exactly-one
  SCCS checks passed; legacy web-app untouched. Local only; sync
  wall/control/mission modules over wall.13, restart and verify
  3.1.wall.14. No deployment or robot commands.

### 2026-11-09 — Smaller left bypass first in front of dishwasher, wall.13

- 092328 run (wall.12) travelled 2518mm with two contact recoveries and
  three wall-loss rejoins, then stopped at 09:25:39.117 with `wall rejoin
  reached 90 degree bound without target signal`. First two wall-loss
  searches rejoined at signals 90 and 72.75, then contact during the third
  search started a 90deg left bypass (37.74 to 126.12deg) and swept right
  130.28 to 39.27deg over ~243mm with averaged IR 0.5-7.0, never
  reacquiring 30. Operator reports the robot was in front of the
  dishwasher close to the fridge and the left bypass was too much. Report
  and telemetry at output/wall-run-20261109-092328/.
- First obstacle-bypass left step is now 20deg; it escalates to 90deg only
  if contact repeats while the bypass is active. The 20deg attempt keeps
  the robot nearer the recessed dishwasher front for the following right
  sweep. Bypass rejoin (15deg/50mm/90deg/25s), 1500mm/90s detour bound,
  four wall-loss searches and 42 recoveries unchanged.
- Focused WALL tests 42/42 passed including new repeat-contact escalation
  test; mission 133/133, control 47/47 passed. Whitespace and exactly-one
  SCCS checks passed; legacy web-app untouched. Local only; sync
  wall/control/mission modules over wall.12, restart and verify
  3.1.wall.13. No deployment or robot commands.

### 2026-11-08 — Recessed-front right sweep and WALL map trail, wall.12

- 223448 run (wall.11) travelled 3081mm with seven contact recoveries and
  three wall-loss rejoins, then stopped at 22:37:29.972 with `wall rejoin
  reached 90 degree bound without target signal`. Left bypass turned
  44.85 to135.74deg, then searched right 137.38 to47.03deg over ~246mm
  with averaged IR 0.0-2.5, never reacquiring 30. Operator reports the
  dishwasher in front of the fridge is recessed from the cabinets, so
  IR loss there should seek a recessed front with a right turn. Report
  and telemetry at output/wall-run-20261108-223448/.
- Wall-loss search now sweeps right in 10deg steps bounded by 60deg or
  20s, seeking the recessed front line/wall/obstacle. Contact rejoin
  remains 5deg/30deg/10s, bypass 15deg/90deg/25s unchanged. Wall-loss
  accounting and contact budgets unchanged (4 searches, 42 recoveries).
- WALL clears map coverage on start and records the localizer pose
  (tag16 anchor dead-reckoned by wheel odometry) as the run trail even
  when no tags are visible (localized=True, persist=False). Prior run
  left only 11 trail points in 3.08m after leaving tag16; trail now
  continues through wall-loss and bypass segments until flush on exit.
- Focused WALL tests 41/41 passed including recessed-sweep beyond-30deg
  and mission WALL start/trail tests; mission 133/133, control 47/47
  passed. Whitespace and exactly-one SCCS checks passed; legacy web-app
  untouched. Local only; sync wall/control/mission modules over wall.11,
  restart and verify 3.1.wall.12. No deployment or robot commands.

### 2026-11-08 — Four-frame IR average and forty-two contact recoveries, wall.11

- 221411 run (wall.10) followed the wall for 883mm with five right-bumper
  contacts; four recoveries succeeded (reverse ~30–36mm, left 15deg,
  measured rejoin) and the fifth stopped with `contact recovery limit
  reached`. Operator reports the map looked okay, bumps are useful wall
  fixes once position is known, and the IR signal seems unsteady. Report
  and telemetry at output/wall-run-20261108-221411/.
- WALL now averages the right light-bumper signal over the latest four
  distinct sensor frames for acquire/align/rejoin/follow decisions. The
  average resets on each stage transition; raw_signal, signal and
  signal_avg_n are logged. LED still shows the live raw reading.
  Single spikes no longer steer or qualify the wall; sustained loss still
  triggers wall-loss rejoin after the window clears.
- Separate contact-recovery budget as WALL_MAX_CONTACT_RECOVERIES=42 for
  longer runs toward the fridge bypass; acquisition reapproaches remain
  four, wall-loss searches four, bypass/trial limits unchanged. Bump
  recovery still reverses 30mm and turns left 15deg (90deg only for
  wall-loss/bypass contact). Added averaging and 42-limit regressions.
- Focused WALL tests 40/40 passed, including new spike-suppression and
  fifth-recovery tests. Full discovery ran 623 tests with one pre-existing
  RPi import error; wall/control/mission subsets (40/47/132) passed.
  Whitespace and exactly-one SCCS checks passed; legacy web-app untouched.
  Local only; sync wall/control modules over wall.10, restart and verify
  3.1.wall.11. No deployment or robot commands.

### 2026-11-08 — Local check-in of pending WALL and RoomTrek changes

- User requests all pending changes committed to the local repository. Include
  WALL3.1.wall.10 controller/Clock/LED/Python-console integration and regressions,
  imported RoomTrek stopped-survey Save Map fix and operating guide, accumulated
  WALL sensor/run reports and generated map archives/runtime map-state update.
- Pending set90 files/~1.95MB before this log addition. Credential-pattern and
  whitespace review clear;27 applicable source/doc files each have one SCCS ID.
  Preserve generated CSV/PNG archives as emitted (CSV uses CRLF); staged checks
  allow CR at line endings. Trim final extra WALL source blank line; legacy
  web-app untouched.
- Prior validation:612-test full suite passed, followed by38 focused WALL tests
  after the final pivot-drift refinement. No implementation changes during
  check-in. Local master only; no GitHub operations or robot deployment/motion.

### 2026-11-08 — Minimum30 wheel commands and measured rejoin, wall.10

- User requests30 speed floor because lower commands seem to produce poor or
  opposite turning, and questions rejoin limit. Clamp every nonzero WALL wheel
  command to abs>=30; approach/reverse30, pivots30, follow corrections floored30.
  Target remains30 raw packet51 units and LED alternation unchanged.
- Replace fixed weak differential arc with measured right steps and straight
  advances: normal5deg/30mm, bypass15deg/50mm. Pivot right=-30,left=30; advance
  both30. Before moving, collect3 fresh stationary frames to avoid residual
  left settling being counted as a wrong-way turn. Confirm3 target frames stopped.
- Remove100/350mm per-rejoin cutoffs. Retain ordinary30deg/10s and bypass90deg/25s,
  four searches/contacts,1500mm/90s bypass and6m/240s whole-run limits. Never seek
  indefinitely without IR. Pivot-center odometry drift is allowed; actual reverse
  movement during forward advance and wrong-way yaw still abort.
- Full regression612/612 passed;38 focused WALL tests passed after final pivot-
  drift guard refinement, including minimum-speed, >100mm continuation, measured
  turn/advance, fresh-frame and stop/contact precedence. Local only; sync wall/
  control modules overwall.9, restart and verify3.1.wall.10. No robot commands.

### 2026-11-08 — wall.9 rejoin stops at100mm with weak realized right turn

-195639 run: both side-contact corrections stayed~14–15deg; second contact
  during drive logged contact_preempted_drive and recovered, no generic abort.
  No90deg escalation. Last recovery retreated30.06mm then turned left14.11deg.
- Terminal19:58:00.586 reason wall rejoin reached100mm/15degree bound without
  target. Entry744.738mm/yaw107.633, final845.006mm/yaw107.086:100.27mm advance
  but only0.55deg net right. Post-stop left settling peaked110.15; arc corrected
  3.06deg from peak. IR17–24 never reached30. Last successful heading92.21deg.
- Fixed right15/left25 commands did not yield enough measured yaw. Requested
  firmware speeds14/28 are command reports, not measured wheel speed. Recommend
  bounded heading-controlled right steps before inward re-approach, rather than
  merely increasing forward-distance bound. No terminal hazard/contact/race.
- Report/telemetry at output/wall-run-20261108-195639/. Analysis only; no runtime
  changes, deployment or robot commands.

### 2026-11-08 — Small side-contact corrections and contact/drive race, wall.9

- User authorizes fixes from194434 review. Remove nearby-repeat (<200mm)
  escalation: ordinary repeated side-wall contacts retain15deg left correction.
  Left90 remains for contact during wall-loss search or an already active bypass;
  existing fridge-like search/bypass behavior and budgets are preserved.
- Add typed WallContactStop from owner for rejected moves against WALL latch.
  Drive catches only that condition, rereads controller snapshot, requires a
  still-confirmed latch and rechecks all mission safety/freshness/odometry guards
  before normal retreat recovery. Never resend the rejected forward command.
  Unrelated exceptions and unconfirmed latches propagate; hard hazards abort.
- Regression coverage injects contact between snapshot and drive; verifies normal
  recovery, preserved search→left90 bypass, and no retreat on stale/cliff/drop/
  expired lease or unrelated failure. Owner queue preserves the typed exception.
- Full regression610/610 passed, including35 WALL tests. Whitespace and
  exactly-one SCCS checks passed; legacy frontend untouched. Local only; sync
  wall/control Python modules together overwall.8, restart and verify3.1.wall.9.
  No deployment or robot commands performed.

### 2026-11-08 — Excessive correction and terminal bumper race, 19:44 run

- First right contact recovered with37mm reverse/~17deg left. Another right
  contact after62mm forward triggered nearby_repeat (<200mm path) and selected
  left90deg; actual88.49deg. This rule is too eager for ordinary side-wall bumps;
  no sensor evidence here identifies a fridge. Recommend removing proximity-only
  escalation while keeping bypass for contact during wall-loss searching.
- Right rejoin recovered after150mm/~71deg and resumed following another364mm.
  Third right bumper19:45:53.695 braked/latch53.698; first contact CSV53.699
  already applied0/0. A drive using pre-contact snapshot53.660 was rejected by
  contact latch at execution; unhandled exception aborted mission53.875.
  Need fresh-state contact recovery on that rejection, preserving hard hazards
  and other failures as aborts. Hardware safety stop worked.
- output/wall-run-20261108-194434/report.md and events-and-samples.csv preserve
  evidence for regression. Analysis only; no runtime change/deployment/motion.

### 2026-11-08 — Wall-loss right search and left obstacle bypass, wall.8

- User authorizes heading right on lost IR and go-around-left if next contact
  is fridge, continuing boundary following. Follow signal<7.5 now stops/ends
  lease and enters normal100mm/15deg/10s right rejoin; max4 loss searches.
- Bump/stall while wall-loss searching, or repeated contact within200 encoder mm,
  starts bounded obstacle bypass: immediate owner latch, reverse30mm/clear,
  turn left90deg and resume right-boundary tracking. Other isolated contacts
  retain proven15deg correction. No fridge recognition or global route claim.
- During bypass, right corner search uses5/25mm/s wheels (mean15), up to350mm,
  90deg/25s. Complete bypass bounded1500mm/90s; original trial/hazard/contact
  budgets remain. Hand back to ordinary tracking only after>=200mm and3 fresh
  >=30 readings within20deg of entry heading. Record search source, counts,
  bypass status and heading handoff; this does not identify the original wall.
-30 WALL tests passed, including lost-IR right recovery, contact→left90→boundary
  tracking→right corner→heading handoff, repeated contacts and explicit bounds.
  Real deadman stopped qualification coverage retained. No deployment/motion;
  sync wall/control Python files overwall.7 and verify3.1.wall.8 before trial.
- Full regression605/605 passed. Whitespace and exactly-one SCCS checks passed;
  legacy frontend untouched. Physical fridge bypass remains untested.

### 2026-11-08 — WALL tracks~20mm by observation; terminal IR loss

- User observes successful following at~20mm.192245 run qualified initial
  alignment, followed618mm, right-bumper stop/reverse32.97mm/left14.33deg;
  rejoin qualified existing73-unit signal stationary, then followed another742mm.
- Final IR27–30→16→12→8→7 at19:24:11.796 triggered stopped wall-loss wait.
  Applied wheels0/0 by11.851; signal remained2–5. Mission ended13.407 with
  wall IR lost; stopped without blind cabinet seeking. No terminal contact,
  hard hazard or watchdog fault. Total forward follow encoders~1.36m.
- Right correction was active before loss; log cannot distinguish plank edge,
  reflectivity or physical stand-off change. Current rejoin handles contact
  recovery only. Recommend bounded right rejoin for ordinary wall loss as next
  increment, retaining existing motion/safety limits. Report at
  output/wall-run-20261108-192245/report.md. Analysis only; no runtime changes.

### 2026-11-08 — Gentle right-arc rejoin after contact, wall.7

- User requests turning right to catch up with the wall after retreat/left
  correction. Replace contact_left→acquire with bounded rejoin; no repeated
  initial approach/45deg left alignment when an established wall can be resumed.
- Below target30 packet51 units, arc right at15/25mm/s right/left wheels
  (mean20), max100mm/15deg/10s. At>=30 stop and qualify3 distinct fresh samples,
  then follow directly; uploaded post-contact32 resumes without extra movement.
  Reset PID derivative on resume; log last successful follow yaw.
- Separate four-event contact-recovery budget from initial acquisition retries;
  retain global trial/time/distance limits, bumper latch, stalled-drive detection
  and hard-hazard priority. New tests replay32-unit resume, right-arc direction,
  bounds, fresh-frame qualification, recurring contact and distinct retry budgets.
-74 focused WALL/control tests passed before full regression. No deployment or
  robot commands; sync wall/control Python modules over wall.6 and verifywall.7.
- Full regression602/602 passed, including27 WALL tests. Whitespace and
  exactly-one SCCS checks passed; legacy frontend untouched.

### 2026-11-08 — WALL plank trial: follow, bumper recovery, retry-limit stop

- User reports~30mm gap and lost-position stop.191116 run actually ends
  19:12:33.837 with wall alignment failed after four bounded re-approaches;
  not global localization loss. Two initial alignment failures consumed retries.
- Follow entered19:12:16.903, drove~155 encoder mm with IR40–70. Right bumper
  latched20.632; first contact CSV row20.634 already applied0/0. Reverse34.1mm,
  left14.33deg worked. At23.577 recovery ended with rightIR32, near target30.
- Found next transition repeats initial acquisition: advances~91mm, then another
  left alignment loses signal5; budget exhausted on next failed check. Recommend
  stopped3-frame usable-signal check after contact-left and direct follow resume,
  with reacquisition only if needed; retain hardware guards/bounds and clearer
  acquisition-vs-recovery status. Do not infer mm calibration from observed gap.
- output/wall-run-20261108-191116/report.md records evidence and next trial plan.
  Analysis only; no runtime edits/deployment/motion.

### 2026-11-08 — DIN snag review and WALL contact recovery, wall.6

- User reports contact and continued wheel effort, then identifies DIN plug
  catching cabinet doors above bumper; wood planks added to prevent underrun.
  185925 CSV463 rows: both physical bumper bits always0; acquisitionIR0–24
  never reached30. Flat encoders and~0.8A currents18.18–20.16 preceded old2s
  stall abort. Zero applied speeds first recorded20.355. No bumper failure inferred.
- Add serial-owner WALL stop latch on physical contact and scoped both-wheel
  forward stall (>=350mA each, <0.5mm delta/poll for200ms). Replay triggers
  19:00:18.505,0.322s after first flat/load frame; not a hardware timing claim.
  Latch blocks forward/spin even after switch release; permit bounded reverse.
- Mission stops first, reverses~30mm, requires cleared bumper/safety and stop,
  releases latch, turns left15deg for new approach. Max retreat50mm/5s; recovery
  shares4-retry budget. Hard hazards/startup-contact aborts remain. Target30 and
  WALL/raw LED retained; motor-current fallback does not fabricate bumper events.
- Added owner latch, replay, guard scope, mission retreat/left retry, held bumper
  and cliff precedence tests. Report output/wall-run-20261108-185925/report.md.
  Local only; sync wall/control/mission Python modules and verify3.1.wall.6.
  No deployment or robot commands; planks have not yet been tested in these logs.
- Full regression598/598 passed, including replay and contact-recovery tests.
  Whitespace and exactly-one SCCS checks passed; legacy frontend untouched.

### 2026-11-08 — Bounded WALL re-approach and stopped-lease fix, wall.5

- User reports robot still>200mm from board after first run; correct previous
  wording:30-unit threshold qualified an IR candidate, not intended-wall arrival.
  Annotate prior run report. Target30 packet51 and alternating LED retained.
- Replace unconditional left45 with <=15deg steps, each stopped/checked using
  3 distinct fresh readings>=15. Loss returns to candidate approach heading,
  then requires50mm additional advance before threshold can qualify again.
  Limit4 retries,600mm net-forward envelope,90s acquisition/alignment;
  hard hazards, bump policy and overall trial bounds remain.
- Stop helper requires acknowledged stop before ending lease; failed stop leaves
  watchdog armed. Deliberate checks/wall-loss waits no longer expire moving lease.
  Unexpected expiry has distinct abort reason; shared I/O messages no longer
  mislabel all lease users GridRunner. Added logged-sequence regression, failed
  stop and real-arbiter deadman tests, retry bounds and stepped drive simulation.
- Local update only; sync roomberry_wall.py and roomberry_control.py, restart
  and verify3.1.wall.5 before trial. No deployment or robot commands performed.
- Full regression591/591 passed, including19 WALL tests and real-deadman
  stopped-wait coverage. Whitespace/SCCS checks passed; legacy frontend untouched.

### 2026-11-08 — First WALL motion log review, 18:44 run

- Tag16 qualified18:44:48; left88.05deg, forward199.64mm, right47.69deg;
  acquisition31mm and packet51 readings32/33/39 reached target30 at18:45:04.
- Fixed left44.08deg alignment lost signal40→0. Follow saw1 (<7.5) and never
  issued a drive command; wheels already stopped18:45:07.891. No bump/cliff,
  ready sensors and continuing polls. Absolute encoder path289mm, net242mm.
- Found deliberate-stop lease bookkeeping defect: last moving renewal07.64,
  lease expired08.238 while stopped, generic guard abort08.245 preempted intended
  wall-loss wait. Recommend bounded sensor-qualified alignment and explicit
  stopped-lease lifecycle/reason reporting, with replay regression.
- output/wall-run-20261108-184421/report.md and events-and-samples.csv record
  findings. Analysis only; no code change, deployment or robot commands.

### 2026-11-08 — WALL controls from right light-bumper at30 units, wall.4

- User replaces physical clearance target with fixed30 raw units on higher
  resolution right light-bumper packet51. WALL starts at stopped tag16 anchor
  qualification without clearance capture. Preserve WALL/live packet51 LED.
- Controller acquisition and P/D following now read light_bump_right_signal,
  validate0–4095 and use30. Status/logs identify sensor/packet and leave desired
  and measured mm unset. Dashboard/catalog remove100mm capture; old HTTP capture
  explicitly rejects without target mutation. Update operating instructions.
- IR acquisition goes directly to left45deg alignment rather than backing away
  160mm and losing the short-range wall signal. Physical bumper fallback retains
  conservative160mm release; loss after alignment stops/aborts rather than blind
  seeking. Departure left90/forward200/right45 and safety/trial bounds retained.
- Added old-versus-new sensor acquisition regression, fixed-target/retired-capture
  checks and updated Clock tests; ideal differential-drive simulation exercises
  acquisition and60seconds of tracking (not a real sensor distance calibration).
  JavaScript syntax passed. No deployment or robot commands performed.
- Full regression suite586/586 passed with local socket/framework permissions.
  Whitespace and exactly-one SCCS checks passed; legacy frontend untouched.

### 2026-11-08 — Three-position right light-bumper trial review

- User reports0/10/50mm only in new183024 session.345 sensor samples and3
  stationary encoder plateaus; assume reported order for gap labels. Right
  min/median/max56/61/66 at wall,1/5/10 at10mm,0/0/2 at50mm; old wall13/15/16,
  0/1/2,0/0/1. At10mm right median falls~92%; no useful50mm range demonstrated.
- Requested/applied wheel speeds zero, no physical bumpers or binary wall bits;
  mission remained clearance with null target. Black surface is plausible,
  not isolated from geometry without a comparison. No counts-to-mm fit justified.
- Report and held-window CSV at output/wall-sensor-20261108/183024-report.md
  and183024-held-positions.csv. Analysis only; no runtime change/deployment/motion.

### 2026-11-08 — Right light-bumper LED and gap-test review, wall.3

- User held0/10/20/100mm gaps5–10seconds and requests right light-bumper LED.
  WALL now alternates every second with raw packet51 intensity0–4095, instead
  of packet27. Keep one-second sample hold, SCAN priority, zero and---- handling.
  Display only; wall controller and clearance capture still use old wall signal.
- Uploaded182455 CSV has419 samples18:24:55.659–18:25:56.126. Five-second
  right-signal medians~54–56,19–20,4,then0; old signal~13–14,4–5,then0.
  No distance markers permit reliable gap-to-interval assignment. Save summary
  at output/wall-sensor-20261108/182455-five-second-summary.csv.
-53 targeted control/startup tests pass, including separate old/right values,
  full4095 display and invalid4096 rejection. Whitespace/SCCS checks pass.
  Control version3.1.wall.3; local only, no deployment or robot motion.

### 2026-11-08 — WALL alternating LED feedback, wall.2

- User requests wall feedback for black-baseboard trials at contact,10,20,50,
  100mm. Alternate WALL/raw old packet27 intensity every second; no unverified
  counts-to-mm conversion. Hold numeric sample for its full second, preserve
  SCAN priority and wheel-drop suppression; unavailable/out-of-range shows----.
- Phase starts on WALL entry and survives mission display refreshes; mode exit
  restores normal display. Control version3.1.wall.2. Operator notes added to
  wall-mission.md: do not capture100mm reference at other measured gaps; stopped
  clearance observation window still times out after90s.
-66 targeted control/startup/WALL tests passed, including LED timing, sample
  hold, scan precedence, restart and invalid signal. Whitespace and SCCS checks
  passed. Local change only; no Pi deployment or robot motion.

### 2026-11-08 — Uploaded WALL sensor log review

- output/wall-sensor-20261108/report.md reviews18:08 and18:10 sensor sessions
  plus application log through18:13:20. Old wall signal plateaus0–1,2–4,29–32;
  operator identifies last position as at wall. Final10s right light-bumper
  signal117–128, median123. Binary wall/physical bumpers never asserted.
- WALL stayed clearance with null target; captures18:11:12/18:11:38 failed,
  first90s wait timed out. All requested/applied wheel velocities zero; no
  autonomous departure/following. Encoder movement is not measured wall gap.
- iRobot2018 OI spec deprecates wall packet27 (0–1023) in favour of right
  light-bumper packet51 (0–4095), already logged. Both report raw intensity,
  not mm; WALL currently uses the older input. Recommend evaluating packet51.
- Found capture sampling flaw:100ms reads require distinct frames despite
  median140ms polls; generic failure also conflates weak input with duplicates.
  Close-wall capture would not establish100mm clearance. Report only; no
  runtime changes, deployment or robot commands.

### 2026-11-08 — WALL mission and Python console, wall.1

- Clock now starts/cancels new WALL mission; GRID remains web-startable and
  Clock still cancels active GRID/CAL. WALL LED, Python HTTP start/reference
  capture operations, dashboard stage/signal/result and command catalog added.
  Legacy web-app untouched; pending RoomTrek import changes retained.
- Require operator-measured100mm body-to-wall parallel IR reference:5 fresh
  stationary, stable readings; weak/saturated signal inhibits motion. Reference
  resets with server. Live clearance remains unknown, surface dependent.
- Qualify2 consistent fresh tag16 fixes; left90deg, forward200mm, right45deg,
  slow IR/bumper acquisition, back160mm before left45deg alignment, then right
  wall P/D tracking at35mm/s. Conservative oblique-acquisition backoff is not
  a measured overhead clearance. Bound acquisition600mm/25s and trial6m/240s;
  wall loss stops without blind seeking; unexpected contact aborts.
- Preserve sensor/cliff/wheel-drop/battery/OI guards; add wheel epoch/jump,
  wrong-direction/stall checks and independent0.6s I/O motion lease. Stage,
  sensor/odometry and commanded wheel records go to existing robot log/status.
- Added independent differential-drive/IR-geometry simulation and WALL safety,
  anchor, bumper release, stale-frame, Clock, scan and HTTP routing checks.
  Phone remote commands, type6 reception/IMU fusion and full survey-validation
  orchestration remain subsequent work. No Pi deployment or physical motion.
- Validation:584/584 roomberry tests passed with local socket/framework
  permissions, including the differential-drive simulation. Dashboard JavaScript
  syntax, whitespace and exactly-one SCCS checks passed for pending text files.

### 2026-11-08 — Automated RoomTrek survey/validation planning

- User reports 11 Pro map import failed on Peters 10; same-phone survey and
  navigation appeared to recognize prior features. Import cause unconfirmed.
- Reviewed map import, type6 sender, NavLink receiver and discovery wall follower.
  Plan standalone bounded right-wall acquisition/following from tag16, remote
  acknowledged phone commands, type6 reception plus explicit IMU transport,
  synchronized run logs and independent tag checkpoint validation before fusion.
- Planning only; no implementation, deployment or robot motion performed.

### 2026-11-08 — Latest RoomTrek deployed to Peters 10

- Built current local RoomTrek, including GitHub9039ebe stopped-survey Save Map
  fix, as signed Release using Xcode14.2 and automatic provisioning.
- Detected Peters 10 on iOS16.7.16, device
  ab151810c534a3ffe07756d271a25095fe25e5d2. ios-deploy finished InstallComplete
  with exit0. No launch, camera/ARKit or map workflow validation performed.
- Build: /tmp/RoomTrek-Peters10-build.log; install:
  /tmp/RoomTrek-Peters10-install.log. No robot commands or source changes.

### 2026-11-08 — Pull recent GitHub changes locally

- Fast-forwarded existing publication checkout from f6064e5 to9039ebe from
  PreussLabsLLC/RoomBerry26 main. Copied all four changed files into the main
  local workspace after verifying each existing file matched the prior snapshot.
- Includes RoomTrek stopped-survey Save Map fix and room scan/transfer guide.
  Verified copied file contents and one SCCS identification per changed file;
  no app build, deployment, robot commands or GitHub writes performed.

### 2026-11-08 — RoomTrek local and GitHub check-in

- Commit pending Save Map fix, device deployment notes and room scan/transfer
  guide in local master and the existing independent GitHub publication main.
- Fetched origin/main and verified publication checkout clean and synchronized
  before copying the four changed files. SCCS and whitespace checks pass.
- Prior signed Release build and Sputnik installation are recorded below;
  stopped-session capture and cross-phone map accuracy still need device tests.

### 2026-11-08 — Room scan and transfer operator guide

- Added RoomTrek/ROOM-SCAN-GUIDE.md and README link: Sputnik surveying, save
  confirmation/selection, Files export/AirDrop, Peters10 import, candidate
  localization, measured checkpoint/return tests, repeats and log export.
- Checked control names, coordinate axes and validity gates against source.
  Distinguish installed Sputnik update from unverified iPhoneX installation,
  paused-save capture and cross-version map portability. Documentation only.

### 2026-11-08 — Save Map after stopping a survey

- User reports Save Map unresponsive after Stop; code disabled the button and
  rejected stopped saves. Retrieved logs confirm Surveyor start/stop with no save.
- Keep stopped survey eligible for saving until a new session replaces it. Add
  disabled styling, Saving Map status, duplicate-save guard and request logging;
  prevent starting/replacing sessions during capture. Missing frames show an alert.
- Signed Xcode27.2 Release build passed; updated app installed on Sputnik.
  Stop-then-save ARKit capture still needs an on-device retest. Prior unsaved
  in-memory survey does not survive app replacement. No robot changes.

### 2026-11-08 — Sputnik launch verified

- After user trusted the developer on Sputnik, CoreDevice successfully launched
  com.preusslabs.RoomTrek. Deployment and launch verified; camera/ARKit and
  surveying behavior still require on-device testing. No source/robot changes.

### 2026-11-08 — RoomTrek installed on Sputnik after Xcode sign-in

- User signed into Xcode; device-targeted Release build with automatic
  provisioning succeeds. CoreDevice successfully installs com.preusslabs.RoomTrek
  on Sputnik (00008030-001D581226E2802E).
- Launch denied by iOS security: invalid signature/entitlements or profile not
  explicitly trusted. Local codesign verification reports CSSMERR_TP_NOT_TRUSTED.
  Next step: trust Personal Team developer on phone in Settings > General >
  VPN & Device Management, then open RoomTrek and retry if still blocked.
- No runtime/camera validation claimed; no app source or robot changes.

### 2026-11-08 — Sputnik deployment retry with Xcode 27.2

- New environment selects Xcode27.2 (27B52). CoreDevice detects Sputnik,
  UDID00008030-001D581226E2802E, available and paired.
- Retried device-targeted RoomTrek Release build with automatic provisioning
  updates/device registration. Build stops at signing (exit65): No Accounts
  and no iOS App Development profile for com.preusslabs.RoomTrek.
- Sign in to the Personal Team account in Xcode Settings > Accounts, then
  retry. No app installed or launched; no source or robot changes.
  Build log: /tmp/roomtrek-sputnik-build.log.

### 2026-11-08 — Local and GitHub check-in: RoomTrek and tile refinements

- User requests all pending changes checked in locally and on GitHub. Preserve
  local master and independent publication main history; origin/main fetched
  and verified equal before copying30 changed source/doc/asset files.
- Local check-in includes53 pending files including runtime state/map archives;
  publication keeps established runtime-log/local-agent exclusions (23 files).
  Preserve publication-only files and legacy frontend. No robot deployment.
- Includes standalone RoomTrek, app artwork, map transfer/pose diagnostics and
  approved optional type6 sender; GridRunner heading fusion/PID/line-loss,
  crossing/scanline/lens refinements, coverage reset and regression tests.
- Correct free-account notes: Personal Team provisioning must run through Xcode;
  manual paid-portal registration advice was inapplicable. Sputnik installation
  remains unverified; use newer Mac/Xcode for iOS18, retain old setup for iPhoneX.
- Full Python suite570/570 passed (108.437s); GridRunner Release build passed;
  RoomTrek host checks passed, signed Release previously passed. Source SCCS,
  credential-pattern, file-size and whitespace reviews clear. Generated map CSV
  CRLF retained. Physical map portability/accuracy testing remains outstanding.


### 2026-11-08 — RoomTrek provisioning refresh attempt

- User authorizes registering Sputnik and regenerating its profile. Generic
  signed build with allowProvisioningUpdates/allowProvisioningDeviceRegistration
  succeeds, but embedded profile still lists only the two older phones.
- Device-targeted registration remains blocked by Xcode14.2's missing iOS18
  device support. No configured App Store Connect API key/fastlane tools found
  in standard locations. Sputnik has not been registered by this attempt.
- Manual Apple Developer Devices registration required: Sputnik,
  UDID00008030-001D581226E2802E, team D7C5ZZCATF. Then refresh RoomTrek profile,
  inspect inclusion and retry installation; no additional failed install run.


### 2026-11-08 — RoomTrek device name correction

- User confirms the iPhone 11 Pro is Sputnik. Correct README and device notes;
  installation attempts already used the correct hardware ID.

### 2026-11-08 — RoomTrek installation retry after Developer Mode enabled

- User enabled Developer Mode; retry device-targeted Xcode build with automatic
  provisioning/device registration. Developer Mode warning is resolved, but
  Xcode14.2 cannot prepare iOS18.7.7: missing device support files (exit70).
- Direct ios-deploy retry completes transfer but fails verification again with
  0xe8008015, invalid provisioning profile. RoomTrek is not installed.
- Need supported Xcode/device support plus development profile containing
  Sputnik's UDID00008030-001D581226E2802E. No app source or robot changes.


### 2026-11-08 — Standalone RoomTrek surveying/localization implementation

- Reviewed existing RoomTrek outline, StarLock and NavLink conventions. Keep
  Swift5/iOS15/Xcode14.2 and automatic team signing; no edits to existing apps,
  robot behavior, legacy frontend or remotes. Preserve pre-existing worktree edits.
- Correct ARKit frame delegate callback, mapped-world quaternion, camera/body
  mount transform direction, Stop/Start logging and main-thread map-save UI.
  Navigator requires observed relocalization plus1s normal tracking; stale,
  limited, failed/interrupted and Surveyor poses cannot be valid navigation data.
- Secure local ARWorldMap archive in versioned metadata container, validated
  Files import/export, atomic replacement, metadata-version and128MiB import
  bounds; map library, side-by-side camera/features/status UI, retry/stop.
- Add tracking/mapping/attempt/outcome diagnostics and1/2/5Hz pose logging.
  User approved RoomTrek NavLink v1/type6 extension: full UUID/quaternion,
  mapped camera pose, timestamps, tracking/relocalization/validity. Off by
  default; existing Pi receiver rejects type6 and needs a separate upgrade.
- Signed Release build passed without compiler warnings. Host checks passed
  packet layout/UUID, pose validity/freshness, mount inversion, JSON round-trip
  and malformed/version rejection. Plists and SCCS checks pass.
- USB11Pro detected as Sputnik, iOS18.7.7. Install
  rejected0xe8008015: profile omits UDID00008030-001D581226E2802E. Xcode
  registration attempt reports Developer Mode disabled; enable on phone then
  register/refresh provisioning. No camera runtime or cross-phone accuracy
  result claimed. README includes build, limitations and kitchen trial procedure.


### November 6 lens recalibration, stale tolerance, crossing skips (3.1.tiles.10)

- Camera lens_left set to 15 mm (was 26 config): run residuals showed a
  constant -10.6 mm tracking error, i.e. physical ≈ 15 mm; grout now
  centres the robot body. UserDefaults key versioned so the old stored
  26 doesn't override. GridRunner 3.1 build 7 on Peters 10.
- Stale phone frames (flags=2 reason=2) brake-hold for up to 1 s instead
  of aborting (the 12:18 terminal fault); abort after.
- Transverse ambiguity gate relaxed 0.8 → 0.95 score ratio to reduce
  silently skipped crossings at cruise.
- 73 gridrunner tests pass. Pi sync pending (roomberry_gridrunner.py).

### November 6 lost-line return + PID (3.1.tiles.9)

- Return/approach with the stripe lost dead-reckons toward surveyed tag
  15 on the fused wheel pose (reacquisition expected as it re-enters
  view) instead of aborting at the 3 s grace; only the 30 s / 750 mm
  outer bound aborts.
- Line steering is now PID (Ki 0.15, Kd 0.08, integral clamped at ±150)
  instead of proportional-only, to damp the weave.
- 72 gridrunner tests pass. Pi sync + restart pending; no iOS change.

### November 6 double-count fix, scanlines, map clear (3.1.tiles.8 / grout.21)

- Crossing tracker: minimum interval 1.5 → 2.5 s, re-arm horizon 30 → 50 mm
  so a stopped/braced robot sitting on a grout line no longer counts it
  twice. GridRunner 3.1 build 6 installed on Peters 10.
- GridLine scanlines moved 35 %/65 % → 25 %/75 % of frame to clear the LED
  reflection corona, a likely contributor to lost-line flicker.
- `RoomberryMapper.clear_coverage()` resets visited cookies + trail
  (blocked cells kept); `set_mode(gridrunner)` clears coverage on arm so
  each run starts from a fresh map. Tag positions live in autonomy.json
  landmarks and are untouched.
- 222 gridrunner/mapper/mission tests pass. Pi sync pending
  (roomberry_gridrunner/mapper/mission.py).

### November 6 heading fusion + anchor line (3.1.tiles.7)

- Map trace showed a +3 deg heading bend: pose heading was wheel-yaw
  integration only (wheel imbalance flipped between stages in pit tests),
  unchecked without tag fixes after scan-free returns.
- `_fuse_line_heading` pulls pose heading toward tag heading minus the
  phone's line angle (weak 0.02/tick) to bound integration drift.
- Initial pose records anchor y on the tag-15 heading line; return
  steering adds a bounded anchor term past 120 mm lateral drift.
- 72 gridrunner tests pass. Pi sync + restart pending; no iOS change.

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


### 2026-11-09 — RoomTrek bidirectional NavLink (3.2.navlink.1)

- Inspected Swift NWConnection and Pi UDP recorder. Existing connected socket
  retains an ephemeral source port until reconnect; now reused for command
  receive/replies and across AR start/retry/stop. Preserve host pi, pi.local
  fallback, port5010, 128-byte type6 poses, latest-only queue and legacy types1–5.
- Add opt-in HMAC-SHA256 envelopes with provisioned Documents/NavLink.key /
  Pi command_key_file, timestamp checks and per-process target UUID. Signed
  controller-status heartbeats and endpoint challenge/proof permit authenticated
  IP/source-port changes; unauthenticated binary poses never rebind control.
  Connected UDP filters Pi peer; relay requires signed loopback CLI requests
  and matching phone source, target and command ID for responses.
- STATUS, SURVEY_START, SURVEY_SAVE, NAV_START, NAV_RETRY, SESSION_STOP route
  to existing session/UI controller on main. Accepted and final acknowledgments,
  lifetime target duplicate suppression (bounded capacity refuses new work),
  explicit map-load/tracking failures, fixed30s relocalization deadline and
  20s map-capture timeout. Timed-out navigation remains invalid until retry.
  Idle/stopped sessions retain enabled NavLink for remote start/status.
- Pi validates/records/exports type6 without using it in legacy navigation
  fusion. Add roomberry_trek_control.py CLI using the existing receiver socket
  as relay; no new service port, HTTP, WebSocket or discovery. NAVLINK.md and
  README document key provisioning, wire format, status and CLI examples.
- Validation:12 Python tests pass, including legacy receiver, authenticated
  endpoint migration, malformed/replayed traffic, real shared-socket relay and
  actual CLI subprocess. ARKit-independent Swift checks pass for all six
  command dispatches, asynchronous acknowledgment, duplicate/changed-content
  suppression, bad/stale MAC envelopes, wrong target and disabled control.
  Python/Swift HMAC fixtures verified both directions; existing TrekChecks
  pose/wire/package checks pass. Unsigned iPhoneOS Release build succeeds.
  Source whitespace/SCCS checked. No device installation, Pi deployment,
  robot commands or remote git operations. Physical ARKit/Wi-Fi trials remain.


### 2026-11-09 — RoomTrek Australian SPEAK voice (3.2.voice.1)

- Current RoomTrek had no speech handler. Add authenticated SPEAK with required
  text, CLI --text, existing ID/ACK/duplicate behavior, completed on synthesis
  completion and explicit failed on busy/invalid input/audio setup/cancellation.
  Keep synthesis alive in a dedicated controller; audio/background cancellation
  and delegate completion return to main, with utterance identity checks.
- Enumerate installed en-AU AVSpeechSynthesisVoice options and log every name,
  identifier, language and named/numeric quality in existing JSONL logs. Refresh
  on launch, foreground return and speech. Do not infer age or gender or assume
  any named voice is installed. User auditions for young Australian female
  character via Test Voice: “G’day, Captain! I’m running a bit low on juice!”
- Australian voice menu persists identifier in UserDefaults; pitch/rate sliders
  persist, initial1.08/0.52 with supported bounds and invalid-value recovery.
  Preferred unavailable falls back to an installed en-AU voice ordered by
  quality/identifier, then system default; retain missing preference for restore.
  Same configuration applies to Test Voice and remote SPEAK. Document settings,
  inventory log export, fallbacks, limitations and CLI example.
- Swift speech checks pass: defaults, persisted preference/pitch/rate, preferred
  selection, missing/empty inventory fallbacks, bounds/nonfinite values, input
  limits and exact test phrase without speaking audio. Swift authenticated
  control checks include SPEAK and pass.12 Python NavLink tests pass including
  actual SPEAK CLI text/ACK relay. Unsigned iPhoneOS Release build passes;
  whitespace and SCCS checks clear. No deployment, audio audition or device
  inventory claimed; installed voices and desired character require phone test.


### 2026-11-09 — Roomberry mnemonic speech catalogue (3.2)

- Add roomberry_speech.py with16 en-AU phrases, covering mission/navigation
  modes, low/critical/charging batteries, scans, general statuses/errors and
  safety stops. Keep translations out of mission/sensor logic. Server logger
  prefixes codes and retains original diagnostic details plus speech_code/text
  fields. Routine status/debug diagnostics are coded but not continuously spoken.
- Effective mode/recovery changes, battery transitions, scans and safety/error
  events enqueue catalogue text for authenticated RoomTrek SPEAK. Per-code30s
  cooldown, four-item background queue,10s expiry, stable UUID retries, target
  pinning and explicit delivery-result logging; no network on control thread.
  Use ephemeral loopback client to existing NavLink5010 relay, no second service.
  Keyless operation remains log-only. Worker lifecycle follows receiver/server.
- CONTROL_VERSION and newly touched source/docs SCCS use3.2. Preserve pending
  NavLink/iOS voice work. Document all16 phrases, logging and delivery behavior
  in roomberry/docs/speech.md.233 focused speech/mission/control/server/map-log/
  NavLink tests passed, including robot-before-speech shutdown cleanup order.
  Whitespace and SCCS checks clear. No deployment,
  robot movement, live speech or remote git operations.


### 2026-11-09 — No-speech run check and Python console speech test (3.2)

- Review updated11:33 logs. NavLink bound0.0.0.0:5010; latest11:33 and11:27
  binary files and all seven Nov9 archives are16-byte headers, zero recorded
  packets. Most recent nonempty recording Nov6 12:57 has1703 type5 /1709 type3;
  last valid IMU sample Nov6 12:59:59.272957 Pacific. RoomTrek type6 is ARKit
  pose rather than raw IMU. Source autonomy.json lacks command_key_file and run
  has no Speech delivery records, consistent with disabled speech configuration.
- Add500-character free-text Test Speech form to existing roomberry/web console
  (legacy web-app untouched). Existing SPEAK already handles free text. POST
  /speech queues a bounded tracked job; GET /speech.json reports auth/config/
  worker/peer readiness, packet and IMU snapshot status and per-ID outcome.
  Explicit unavailable before queueing, queued/accepted/final outcomes and ID
  retained in64-job memory history; async UI uses textContent, no raw HTML.
- Speech sender supports validated free text without expanding16-phrase catalogue;
  stable retry ID and target preserved. Log startup missing-key explanation,
  phone acceptance and final status/ID, without speaking delivery-result logs.
  Document diagnostics and setup in output/speech-20261109/report.md and docs.
- Validation:58 focused web/speech/server/NavLink tests passed, including live
  HTTP submit/poll. JavaScriptCore DOM/fetch harness passes submit→accepted→
  completed, server failure and invalid-input paths. Whitespace/SCCS clear.
  No Pi deployment/restart, device installation, robot commands or live speech.
  User-supplied runtime/map archives untouched.


### 2026-11-09 — Configure RoomTrek command key path (3.2)

- Add navlink.command_key_file=/home/pi/NavLink.key to autonomy.json, matching
  the documented Pi CLI/provisioning path. Preserve host pi/port5010 behavior,
  receiver bind and other configuration. Update existing JSON SCCS to3.2.
- JSON validation confirms only key path and SCCS changed; whitespace/SCCS
  checks pass. The secret file itself has not been found/provisioned here;
  it must exist on the Pi and match iPhone Documents/NavLink.key. Configured
  missing/unreadable keys fail receiver initialization, so provision before
  restarting with this configuration. No generated secret, deployment/restart,
  device changes or live authenticated command test.
- Pi remote commands implemented: STATUS, SURVEY_START, SURVEY_SAVE, NAV_START,
  NAV_RETRY, SESSION_STOP, SPEAK. Require updated foreground RoomTrek, NavLink
  enabled and matching key; current supplied logs do not establish a live
  authenticated link. Does not remotely launch/unlock the phone/app.


### 2026-11-09 — Provision connected iPhone key; Pi upload delegated to user (3.2)

- User supplied a short key and requested Pi roomberry-folder / iPhone setup,
  then explicitly reserved Pi uploads for themselves. Prepare ignored local
  roomberry/navlink.key (mode0600) and configure absolute Pi destination
  /home/pi/Projects/Roomberry/roomberry/navlink.key. No Pi uploads or service
  restart performed; only read-only Pi inspection completed before that steering.
- Python/Swift key loaders now accept nonempty trimmed contents verbatim instead
  of requiring32 bytes. Empty/missing phone key remains disabled; invalid Pi
  key files fail explicitly. Longer existing keys preserve exact behavior.
  Document short-key/file-location support; no credential compiled into the app.
- Signed Release build succeeded. Install updated RoomTrek on USB iPhone X
  Peters10 (ab151810c534a3ffe07756d271a25095fe25e5d2). Upload key to its
  Documents/NavLink.key; download/readback after installation matches local key.
  No uninstall or map deletion. Sandboxed install timed out; full USB install
  succeeded. Automated launch unavailable because Xcode DeviceSupport Symbols
  directory is missing; user must open RoomTrek and enable NavLink manually.
-22 Python key/authentication/speech/web tests pass. Swift control checks plus
  Python-signed short-key fixture verification pass. JSON/key location, git
  ignore, source whitespace and one SCCS per applicable file verified. Pending
  user Pi uploads: navlink.key, autonomy.json, roomberry_trek_control.py; then
  restart their Roomberry process. No live Pi→phone command or speech claimed.


### 2026-11-09 — 12:14 WALL run, confirmed speech and bypass-distance stop (3.2)

- Updated logs show eight accepted/completed SPEAK commands after one startup
  unavailable-peer result. Authenticated Pi↔iPhone speech works. Latest12:14
  NavLink file remains16-byte header only: zero recorded binary pose/IMU packets.
  Signed control responses are separate from binary navigation telemetry;
  working speech does not establish ARSession running or a selected phone mode.
- WALL bypass started12:15:46.340; stop12:16:55.243, elapsed68.902s. Abort was
  cumulative1500mm bypass distance rather than90s timeout. Total wheel-derived
  travel3525.17mm,3 contacts,7 wall-loss searches. Rejoined wall but never
  recorded obstacle_bypass_heading_resumed; final heading73.72 vs reference40.69
  and signal11.25 fail current20deg /≥20-signal qualification. No limits changed.
- Explain Surveyor scans/saves a map; Navigator loads that map and must Start /
  relocalize with Valid YES for map-relative poses. Type6 is recorded only,
  deliberately not fused into WALL navigation. Analysis report saved to
  output/wall-run-20261109-1214/report.md. No deployment, remote commands or
  runtime/map archive changes; documentation SCCS/whitespace verified.


### 2026-11-09 — Pi-owned survey lifecycle and installed SCCS headline (3.2)

- User steered the pending survey request into the next run and clarified the Pi
  should control the phone; user continues to handle Pi uploads. Add background
  roomberry_trek_survey.py coordinator and enable roomtrek_survey in autonomy.json.
  Mission non-idle transition sends STATUS, SESSION_STOP and SURVEY_START. Active
  mode changes coalesce into one survey; idle/abort queues SURVEY_SAVE named
  kitchen-YYMMDD from the run-start date, verifies a new map UUID/name via STATUS,
  and sends SESSION_STOP. No extra relay/server/port. Existing WALL limits unchanged.
- Stable per-command UUIDs/target pinning, bounded transition queue, explicit
  unavailable/failed/unknown reporting and status.json survey snapshot. Robot
  motion never waits for network; shutdown stops robot before draining pending
  phone save. Errors still close speech worker/receiver. Map remains on phone;
  no automatic transfer or claim of full kitchen coverage.
- RoomTrek starts NavLink with a provisioned key unless an explicit persisted Off
  choice exists. Pi owns AR mode/start/save/stop through main-thread controller;
  foreground/unlock/camera permission remain iOS requirements. Add visible build
  headline sourced from the AppDelegate SCCS ID: RoomTrek3.2,2026/11/09 12:33:06.
- Signed Release build succeeds and installed on USB Peters10 without uninstall.
  Confirm expected SCCS string in built binary.187 survey/mission/speech/server/
  web/control tests pass, including command retry identity, dated name and new-map
  verification, failed saves, worker drain, and robot-first cleanup on errors.
  JSON, whitespace and one SCCS identification per applicable source verified.
- Document uploads/config/operation in roomberry/docs/roomtrek-survey.md and
  RoomTrek README. Pi deployment/restart left to user; no live mission, phone
  survey or kitchen map save performed while implementing next-run automation.


### 2026-11-09 — 12:38 run: phone poses and kitchen map confirmed (3.2)

- Decode supplied latest NavLink archive:1677 type6 packets,12:38:56.231 through
  12:41:43.816,10.001Hz, sequence0–1676 contiguous,1669 normal /8 initializing,
  max frame age163.278ms. Survey frame XYZ/quaternion/yaw present; map-relative
  validity clear by design. Median features3; no raw IMU/type3 packets. Pi now
  controls AR startup: SURVEY_START acknowledged12:38:55.916; kitchen-261109
  save/new library entry verified12:41:43.855, then phone stopped12:41:44.167.
- First fridge bypass completed heading-resumed gate12:41:33.311 after1437.66mm.
  Next right-bumper contact initiated reverse release; stop12:41:42.192 was
  wheel motion opposite commanded direction, total wheel travel3630.82mm.
  Sensor deltas support transition-accounting issue: pre-reverse +4.9mm roll
  followed by actual−1.3mm reverse; guard compares older mission distance3341.0
  with3344.6 after new−30/−30 command. No physical wrong-direction conclusion
  and no safety/control changes. Phone poses remain recorded only, not steering.
- Save report, metrics.json and decoded phone-poses.csv under
  output/wall-run-20261109-1238. Original runtime/map logs untouched; no deployment,
  remote phone/robot commands, map download or test changes. SCCS/whitespace clear.


### 2026-11-09 — WALL speed floor, tag15 validation goal, speech and disagreement plots (3.2)

- Analyze12:38 sensor/phone run. Stable commands held≥0.5s:30mm/s produced
  left/right encoder medians41.73/39.30mm/s;35 produced39.88/39.88. Supports
  poor low-speed response, not proof of firmware intent or body speed. Raise
  WALL moving-wheel floor30→50 and cruise35→80mm/s, retain35% steering bound,
  zero stops and all existing hard hazards/lease/contact/stale/no-progress gates.
- Fix direction-boundary accounting: first fresh post-command/sign-change sample
  establishes baseline; subsequent fresh increments must match direction. Count
  all mission travel, preserve true wrong-way abort. Regression replays recorded
  +4.9mm coast then−1.3mm reverse without false abort; sustained wrong motion
  still aborts. No wheel-size factor calibrated from phone data.
- Goal is robot-centre range≤300mm from surveyed tag15, confirmed by two fresh
  post-parking tag15 fixes within75mm/0.1rad. Dead-reckon from tag16 to trigger
  stop/face/scan at estimated range or5m checkpoint. Stable farther tag fix may
  authorize≤100mm advances and rescans,12 steps/180s max. Unexpected contact
  aborts during terminal approach. Global8m/360s bound aborts without claiming
  success; previous distance-only completion removed. Log wheel prediction/tag
  correction. Missing map target prevents an unvalidated run.
- Add16 Australian phrases (32 total), key WALL stages, bounded approach and
  confirmed validation/abort, map saved/phone unavailable. Important speech may
  replace older lower-priority chatter; higher-priority queued safety preserved.
  Existing Pi-owned survey and dated map save remain. Update wall/voice docs and
  command description; no iPhone app change required for new text payloads.
- Reproducible output/wall-odometry-20261109-1238/analyze.py, PNG/PDF comparison,
  CSV and metrics/report. Align phone frame uptime with Pi receipts and only
  early0.2m departure (no scale/full-path fit). Configured lens offset assumed;
  end separation1.31m corrected /1.42m raw camera, heading disagreement−9.16deg,
  max absolute14.28deg. These are relative disagreements, not ground-truth errors.
- Full suite663 passed; final83 focused wall/speech/survey/web tests pass after
  queue-priority and terminal-bound refinements. Independent wall simulation,
  fresh/stale scan qualification, range, approach/contact/path/time caps and
  speech queue covered. Plot inspected; whitespace/SCCS checks clear. No Pi
  uploads/deployment, robot commands or physical speed/approach trial. User
  retains Pi uploads: wall, speech, survey modules and web command description.


### 2026-11-09 — Fixed initial tag16 alignment for next-run phone comparison (3.2)

- Add roomberry_trek_anchor.py. Qualified initial tag16 robot pose pairs with
  actual capture-time phone history, not delayed processing time: nearest normal
  frame within250ms, at least3 samples spanning150ms,≤20mm /2deg stationary
  spread. Fixed planar translation/yaw, scale1; no later path fitting/rebinding.
- Existing93.6deg mount estimate was for camera+Y, not RoomTrek optical yaw.
  Derive mapped camera+Y from quaternion and apply that mount correction plus
  measured lens(-145,-22)mm to recover robot centre and remove pivot lever arc.
  Expose roomtrek_alignment config; planar/mount assumptions documented, no
  AR scale or camera-height calibration claimed. Raw phone/map coordinates stay
  unchanged; Pi room-frame results are independent diagnostics, not steering.
- Receiver caches ordered type6 history (600 frames), clock offset and identity
  separately from unfiltered raw logs/legacy fusion. Binding records transform,
  phone identity/frame, capture time and wheel baseline. Separate pure-wheel
  trace starts at tag16 and ignores later tag15/localizer corrections. Log each
  aligned comparison and alignment state; status includes state/separation.
  Session/map/wheel-epoch reset invalidates for rest of run; tracking gaps pause
  then resume same binding. Unexpected diagnostics cannot interrupt robot drive.
- Add local tools/plot-trek-anchor.py for matching next-run log/binary/sensor CSV:
  interpolate raw wheels at phone capture times, use recorded tag16 transform,
  export PNG/PDF/CSV/metrics without early-departure/full-path/scale fits. Reject
  missing/mismatched anchors and clock discontinuities. Synthetic matching traces
  agree within float32 rounding and all exports generated successfully.
-676 full local tests pass, including frame/offset math, pivots, timing, capture
  stability, tracking gaps, identity/reset invalidation, independent wheel trace,
  mission hooks and diagnostic isolation; JSON/whitespace/SCCS checks clear.
  Pi uploads remain user-owned: main/mission/wall/NavLink, new trek_anchor module,
  autonomy.json. No Pi deployment, physical run or new map/phone command. New
  documentation: roomberry/docs/roomtrek-alignment.md. Await next-run logs to
  assess actual disagreement from this common tag16 reference.


### 2026-11-09 — Dashboard iPhone mount replaces old clip calibration (3.2)

- User corrected physical mount: dashboard holder looking approximately20deg
  left and15deg up; active lens10mm forward and180mm left of Roomba centre.
  Update roomtrek_alignment to optical_forward basis, additive camera-to-body
  yaw−20deg, pitch15deg metadata and lens(+10,+180)mm. Old(+Y93.6deg,
  −145/−22mm) calibration no longer applies. Disable legacy type1 phone_position
  soft aiding so obsolete mount values cannot affect later operation.
- Generalize quaternion projection to optical camera−Z for new mount; horizontal
  projection handles upward pitch without adding it to yaw. Preserve explicit
  camera+Y basis for historical anchor records/plots. Anchor metadata records
  basis, pitch, yaw and lens offset; transforms/plot filtering use each recorded
  basis rather than current defaults. No AR scale or absolute camera-height
  calibration, raw-packet change or iPhone update required.
-217 focused anchor/wall/NavLink/mission/legacy-position tests pass. New tests
  cover actual20-left/15-up dashboard quaternion, correct forward/left sign,
  90deg pivot lens-arc cancellation, optical yaw at0/15/35deg upward pitch and
  historical record compatibility. Plot smoke passes for both legacy and new
  dashboard records, exporting PNG/PDF/CSV and matching known synthetic traces
  within float32 rounding. All679 complete-suite tests pass. JSON, source
  whitespace and SCCS checks clear.
- Update alignment/wall docs and mark old12:38 plot's clip-mount assumption as
  obsolete, not a validated current robot-centre comparison. Next run should
  use fixed tag16 calibration with the new mount. Pi uploads remain user-owned;
  no deployment, remote commands or physical run performed during this update.


### 2026-11-09 — 16:33 run: dashboard tag16 alignment and 1.5m bypass abort (3.2)

- Latest run stops16:35:37.046: left obstacle bypass exceeded1500mm/90s.
  Started16:34:59.610, elapsed37.436s, so distance bound triggered; wheel path
  3545.58mm. Three contacts, two ordinary wall-loss searches. Wall signal rejoined
  but bypass heading never resumed: entry44.19deg vs final91.88deg (47.69deg
  gap), IR10 below20. No tag15 validation; estimated remaining range at stop
  1532mm wheels /2244mm phone. No control/limit changes.
- New fixed dashboard tag16 alignment established with capture pairing25.36ms;
  correct lens(+10,+180)mm, optical basis−20deg and pitch15deg metadata. Initial
  live mismatch0.50mm/0.053deg.990 contiguous type6 packets,983 normal /7 init.
  Reusable plot uses828 post-anchor normal frames, no fitting/scale adjustment.
  At stop:760.43mm separation /−11.91deg; final767.19mm /−11.84deg, max769mm /
  abs13.61deg. Phone trails wheel roomX by722mm at stop. Neither is ground truth;
  old clip-mount plot is not an apples-to-apples baseline.
- Speed response remains above commands: stable≥0.5s, duration-weighted50mm/s
  gives69.25/65.23 left/right encoder mm/s;80 gives91.20/92.13. No firmware/body
  speed conclusion or calibration change. kitchen-261109 save verified16:35:38.349.
- Save plot PNG/PDF, CSV, metrics and report under
  output/tag16-comparison-20261109-1633. Supplied runtime/map files untouched;
  no remote commands, deployment or tests/code changes. Report/SCCS/whitespace
  checked. Independent tag15 fix still needed to assess absolute accuracy.


### 2026-11-09 — Bounded tag15 lucky scan and map lifecycle review (3.2)

- At the 1500mm/90second obstacle-bypass limit, stop and attempt one tag15
  acquisition at current heading, +10degrees, then -10degrees. Two distinct
  agreeing captures are required to resume approach; exhausted views abort
  stopped. Look bounded by75seconds,25mm translation and +/-15degree envelope;
  each pivot8seconds. Safety/time/envelope guards also run during camera pauses.
- Dedicated stationary tag15 solver permits2.5m acquisition, retaining normal
  localizer1.2m gate, decision-margin/reprojection/room checks. Final approach
  retains100mm segments, fresh scans,300mm two-capture completion and180second
  limit, now at most24 steps. Global8m/360second and contact/hazard limits remain.
- Review confirms every automatic mission stops the prior session and starts
  Surveyor with resetTracking and no initialWorldMap. Same kitchen date label
  identifies separate UUID saves; repeated runs do not accumulate old map data.
  Accumulation would require saved-map load, successful relocalization, continued
  mapping and another save; no lifecycle change made. Last run983/990 normal
  tracking packets is continuity evidence, not a saved-map coverage/accuracy
  grade. Reload/relocalization and independent tag checks remain necessary.
- Added seven lucky-scan tests: three views/exhaustion, two-capture approach,
  duplicate/old captures, hazards, time/translation/angle limits, scan interlock
  and isolated expanded-range solver.212 focused tests passed. All686 full-suite tests passed; whitespace and single SCCS
  identification checks clear. No robot movement, iPhone installation or Pi upload performed;
  Pi deployment remains user-owned. Updated wall-mission documentation.


### 2026-11-09 — 17:01 run reaches tag15 with manual assistance (3.2)

- WALL stops17:04:43.933 at wall-loss search limit,4883mm path,11contacts.
  Manual steering then tag-return localizes. First confirmed tag15 capture
 17:07:29.812 gives859mm centre range; last confirmed17:07:59.428 gives646mm.
  Final17:08:23.171 estimate133mm is wheel-projected, no final scan verifying
 300mm goal. Stop17:08:23.373 uses shared close/travel guard; only524mm since
  final fix, below750mm travel cap, consistent with crossing124mm minimum range.
- Offline independent wheel integration from tag16 capture, including manual
  driving, yields448mm/6.77deg error at first confirmed tag15 fix and528mm/7.06deg
  at last: wheels201mm highX/488mm lowY. Local controller correction from its
  more recent tag15 fix is58.3mm/0.30deg. Two final scans agree7.2mm/0.53deg.
- No wheel/iPhone comparison available: initial command failed App must be
  foreground, no normal frame at tag16; first type6 arrives17:05:54.680.728packets
  in six sessions. Final596frames:553normal/6init/37insufficient-feature limited;
  normal features0/median2/max3. Repeated map saves fail Insufficient features.
- Exports/report/reproducible analysis under output/tag16-comparison-20261109-1701.
  Plot visually checked, sample timestamps/epoch continuity and SCCS verified.
  No source/control/config changes, deployment or movement; supplied logs intact.


### 2026-11-09 — Foreground startup warning, tag-return validation, gentler left bypass (3.2)

- Explain missing endpoint scan: manual recovery used standalone Tag15Return,
  whose old finish approached bumper contact; WALL's300mm validation did not
  apply. Add stopped validation in standalone return at estimated<=300mm:
  two distinct fresh agreeing tag15 fixes must measure<=300mm for completion
  and TAG15_VALIDATED speech. No wheel-only success. Three failed captures,
  inconsistent fixes or confirmed range outside300mm abort stopped. Preserve
  safety, close-range and travel guards; disable line handoff during validation.
- Authenticated App must be foreground failure now logs PHONE_BG, exposes
  persistent warning in survey status/local console, and invokes an unhappy
  Roomba beep from the survey worker. No iPhone SPEAK attempt for this warning:
  foreground guard also rejects speech. Offline is not labelled backgrounded;
  successful survey startup clears warning. Robot startup remains asynchronous,
  not gated. Console warning appears on status refresh; auto refresh remains off.
  Catalogue now33 entries. iPhone code already disables auto sleep while active;
  session stop re-enables it. User should unlock/open/leave RoomTrek visible and
  verify live camera, NORMAL tracking and NavLink before the mission. Initial
  rejection was17:01:52, successful survey by17:05:52; later sparse-feature
  failures are separate from foregrounding. No iPhone code/install changes.
- User additionally reports left-bypass overshoot. Logs show repeated20deg then
 90deg pivots. Reduce repeated obstacle-contact left turn90->45deg, preserve
  first20deg and ordinary15deg. Keep distance/time/contact bounds. Requested
  clarification turn-vs-travel; selected turn limit from log evidence. Physical
  behavior still needs next run; no robot movement or Pi upload performed.
- Four new tests cover background warning/beep/recovery vs offline, stopped
  two-fresh-capture validation and failed/out-of-range validation; bypass test
  now checks45deg limit.45 focused tests passed before bypass change. Broader
  network suite required sandbox escalation for local sockets; final result
 690 full-suite tests passed in95.5seconds. Documentation/whitespace checked;
  all15 touched files retain exactly one3.2 SCCS.


### 2026-11-09 — RoomTrek audible tracking heartbeat installed (3.2)

- User cannot see the mounted iPhone screen and requests10second ping with
  different tone for tracking OK/not OK. Default-on persisted switch; short
  high1100Hz tone requires foreground, active session, valid normal tracking,
  AR frame<=1second old and NavLink enabled. Low440Hz double tone indicates
  foreground but idle/stale/limited/invalid tracking or NavLink off. Does not
  assert map quality or Pi receipt. Tones use generated short enveloped PCM
  through the existing audio helper; no undocumented system sound identifiers.
- Main-thread timer; no ARKit or network configuration changes. Defer heartbeat
  during speech without interrupting/stacking missed tones. Cancel tone on
  background/audio interruption. Speech takes precedence over an active tone.
  Silent phone is not proof of health: volume/routing/off/background/speech
  can suppress the ping. Active sessions retain existing idle-timer prevention.
- Swift SpeechChecks pass:10second cadence, foreground/off, idle, tracking loss,
  stale frames, NavLink off, speech deferral, generated WAV decode/duration;
  existing voice preference/fallback/bounds/input checks still pass. Signed
  iPhone Release build succeeds, installed overUSB on Peters10 iPhoneX.
  Headline RoomTrek3.2 2026/11/09 17:25:54. Installation verified100%; actual
  speaker audibility/volume and mounted tracking remain user checks.
- README updated; all six modified app/test/doc/log files have one SCCS line;
  whitespace checked. No Pi upload, robot movement or run commanded.


### 2026-11-09 — 17:39 WALL and commanded tag15 return analysis (3.2)

- User clarifies “shove” means invoking Return to tag15, no physical push.
  Qualified tag16/phone pairing23.27ms. WALL2723type6 packets,2716normal/7init,
  zero seq gaps; frame-age median67ms/p95=89/max204ms. Return new survey848frames,
 842normal/6init, no seq gaps. Saved kitchen-261109 confirmed17:44:03 and17:45:56.
- WALL lucky scan acquires tag15 at1486mm, five100mm advances; stops17:43:59
  on stale/unsafe Roomba sensors. Pi serial poll max3107ms/one failure, mission
  max3621ms; phone telemetry continues. Do not attribute this Pi stall to iPhone.
- Fixed tag16 wheel/phone separation1124mm at WALL stop, final1123/max1126mm,
  heading−8.16/−8.17deg, maxabs11.20deg. At final commanded-return tag15 fix,
  independent pure wheels off735mm/10.45deg (203mm too farX/707mm lowY); recently
  tag-corrected return controller off88mm/0.82deg. New return phone session is
  not joined to original anchor. No trajectory/scale fitting or fake continuity.
- Two final validate captures agree0.48mm/0.075deg, centre range354.8/355.0mm;
  stops outside300mm explicitly. Camera range248mm is not centre range. Map
  jump about530mm at first global tag15 acceptance near17:43:32 corrects aged
  wheel/tag16 pose. Independent phone trace does not use those corrections.
- Read-only iPhone event download confirms heartbeat attempts and40 speech
  completions, no heartbeat setup errors. No measured CPU/thermal/route/volume
  diagnostics; overload unproven, silent audio unresolved despite callbacks.
  Feature median5 WALL/3 return; map save does not prove map accuracy/coverage.
- Plot/report/data under output/tag16-comparison-20261109-1739, filtered on-phone
  events included. No implementation/config/installation/Pi upload/movement.
  Supplied logs preserved; plot/timing/session/SCCS/whitespace checked.


### 2026-11-09 — Cumulative kitchen-map resume and immutable revisions (3.2)

- User requests saving/amending kitchen map across runs. SURVEY_START now
  accepts optional map_id: load initialWorldMap into Surveyor, wait for observed
  relocalization plus1second normal tracking, then continue mapping in the same
  session. No reset after relocalization. Pending operation fails on map load/
  ARKit errors or30second timeout, including missing frames. Fresh command form
  remains available explicitly. Resumed poses carry parent map UUID and existing
  map-valid bit after relocalization; fresh zero-map telemetry behavior unchanged.
- SURVEY_SAVE requires fresh valid normal tracking and extending/mapped status
  both before capture and before atomic write. Optional metadata fields parent,
  lineage, revision and featureCount keep version1 backward-readable. Every
  save creates a new UUID file; previous maps preserved, no independent-map merge.
  Library UI shows revision/features. STATUS capability survey_resume_v1 exposes
  inventory metadata, readiness and unreadable-package errors, filtered before
  limiting to10maps. Worst-case signed10map response5178bytes<8192limit.
- Pi chooses existing revision chain before independent snapshots, prefers
  mapped/extending bootstraps, resumes across date boundaries, and verifies exact
  saved acknowledgement UUID plus expected parent. Resume45second request budget
  covers phone30second timeout. No fresh fallback after resume failure, old app
  or unreadable inventory. Only absent kitchen library starts fresh. Robot
  motion remains independent/asynchronous; failed mapping is not a motion gate.
- Read-only backup of eight existing maps confirms latest short return17:45:55
  had limited mapping; WALL17:44:02 is mapped. Configure bootstrap seed
 0B2FA89D-F7EA-4002-9AC7-92C32AF1D0D5 until first parent-linked kitchen revision.
  Byte-identical840988byte seed copied to output/kitchen-map-bootstrap-20261109;
  SHA2562ee7144dcd60794e21d213a4ebb81a7e98cdb2db2959480ec66a6b41e675376b.
  Original iPhone files untouched. Coverage/quality need subsequent validation.
- Loaded-map tag16 comparison now requires valid flag and localized state,
  avoiding normal-but-not-relocalized binding. Fresh Surveyor gate unchanged.
  Host checks cover policy, old metadata roundtrip and revision fields; Python
  tests cover bootstrap quality/chain priority, next-run parent, date change,
  capability/corrupt inventory, resume failure/no fallback, exact-ID/parent
  verification and loaded-map alignment gating. Initial695full-suite pass;
  final697full-suite tests pass in96.9seconds. Swift map/control checks pass;
  signed iPhone Release build succeeds, installed100% on Peters10 iPhoneX.
  Headline RoomTrek3.2 2026/11/09 18:09:21. Actual map relocalization/extension
  awaits next physical run; no robot command issued.
- Update survey/ARKit/NavLink/alignment docs with format, CLI and limitations.
  Pi uploads remain user-owned: roomberry.py, trek_survey.py, trek_anchor.py,
  autonomy.json (plus previously pending changes). No Pi upload/deployment.


### 2026-11-09 — Local 3.2 pending-work check-in

- User requests local Git check-in. Include accumulated authenticated NavLink
  commands, Australian speech/test console/heartbeat, WALL/tag15 improvements,
  tag16 diagnostic alignment and plots, cumulative kitchen-map revisions,
  tests/docs, supplied map snapshots/runtime map state and kitchen seed backup.
  Preserve established repository practice of versioning run reports/maps.
- Local navlink.key and raw sensor/NavLink/service logs remain ignored; no
  credentials file staged. No remote Git operation or Pi upload requested or
  performed. Final integration validation697Python tests passed, Swift map/
  control/voice checks and signed iPhone build passed in preceding work.
- Pre-commit whitespace/JSON/SCCS checks clear; all195candidate files reviewed
  for scope, applicable source/docs have one identification line. Refresh the
  pending sync-up script's stale SCCS identity to3.2; no runtime logic change.


### 2026-11-09 — 18:21/18:28 runs: resume timeout, late readiness, scan coast (3.2)

- First Pi map resume times out30s at18:21:57 and stops AR; robot continues
  because startup is asynchronous. Tag16 at18:21:46 cannot bind phone. No frames
  for4min19s, later non-coordinator app restart relocalizes2.8s. First WALL has
 14contacts/5wall-loss searches; lucky tag15 found1886mm, six100mm advances,
  last accepted1472mm pre-final advance.180s timeout18:27:03; path5022mm.
  Only12.24s in approach stages, rest scans/confirmation. Ranges vary/increase.
- Second WALL18:28:14: map resume17.4s, readiness18:28:32 after tag16 at18:28:25.
  Another app stop/restart18:28:38/18:29:08; origin not logged; relocalizes3s.
 6contacts/6wall losses. Lucky-view+10deg stop command near+8.4deg coasts to
 +17.6deg, exceeds15deg envelope; abort18:30:22,3723mm path. Translation12mm
  within25mm limit. Save refused on limited mapping; old seed unchanged.
-2553type6 packets in five sessions, zero within-session seq gaps; frame age
  medians57–85ms,max192ms. Low tone30/46heartbeat attempts includes paused AR/
  pending relocalization. No evidence of network/phone-frame stall; CPU/thermal
  not measured. No new map revisions; no qualified wheel/iPhone comparison.
- Read-only phone event download, metrics, tracking timeline and report saved
  output/wall-run-20261109-1821. No robot/control/app/config changes/deployment.
  Pi can already restart AR via SESSION_STOP then SURVEY_START(map_id). Recommend
  bounded startup retry with robot readiness hold/tag16 pairing, settled scan
  pivots, and scan-stability/latency improvements before extending timeouts.


### 2026-11-09 — WALL startup readiness hold, bounded AR retry and settled scan pivots (3.2)

- User authorizes proposed fixes from18:21/18:28 report. With the configured
  RoomTrek survey coordinator, WALL starts in phone_ready and requires a fresh
  acknowledged physical stop. Poll readiness without blocking sensor handling;
  no camera capture or motor drive during pending mapping. Only after successful
  phone startup request new tag16 captures, rejecting pre-readiness results.
  Require two consistent fresh tag16 fixes AND successful stationary phone
  pairing; failed pairing retries fresh captures while held. Current phone
  frame must remain fresh/qualified and match acknowledged session, expected
  map and bound identity before departure. Failures/changed session abort stopped.
- Startup total120seconds, tag16 qualification at most60seconds after readiness;
  existing360second drive budget starts on qualified departure. Sensor/contact/
  lease/path guards remain active throughout. Coordinator-disabled legacy WALL
  keeps tag-only startup. Other mission modes retain asynchronous startup.
- Loaded-map relocalization_timeout/tracking_failure gets one intentional AR
  restart, same saved parent, after acknowledged SESSION_STOP. At most two
  SURVEY_START attempts with separate operation IDs; transport retries retain
  their ID. No new start on map-load errors, unknown outcomes, failed stop or
  cancelled startup before retry. Final failure never falls back to fresh map
  or saves an unlocalized child. Snapshot adds start_attempt/phone_session.
- Lucky-scan +/-10degree pivots reuse SettledTurn through WALL's strict stop/
  lease owner, with optional0.12s pulse budget checked each mission tick and
  measured closing-rate braking. Stop and collect fresh encoder quiet>=150ms,
  rotation<=2deg/s and translation<=5mm/s before next pulse/reversal/camera scan.
  All wheels retain50mm/s floor; +/-15deg/25mm envelope,8second turn,75second
  look,180second validation and1.5second settle bounds unchanged. Pulse budget
  is not a hardware timer; actual braking/coast needs next physical run.
-100 focused survey/WALL/turn tests pass, covering retry order/exhaustion,
  nonretryable outcomes/stop failure/cancellation, no drive during startup,
  stale captures/binding failures, startup timeout, ready release, stale or
  changed current session, pulse braking/coast settling and no forward scan
  motion. All706 full-suite tests pass in99.0seconds. Source/SCCS/whitespace
  checks pass; survey/WALL/alignment docs updated.
- Pi-only update: roomberry.py, roomberry_mission.py, roomberry_trek_survey.py,
  roomberry_wall.py, roomberry_turn_guard.py. Existing iPhone app already supports
  AR stop/resume; no phone rebuild/install needed. Pi upload remains user-owned;
  no deployment, robot movement or live run commanded.


### 2026-11-09 — After-dark RoomTrek low-double investigation (3.2)

- Latest19:42 run2924type6 packets/10sessions:2639loaded-map frames, zero
  localized-valid map frames. Reasons are initializing/relocalizing, not
  insufficientFeatures. Fresh surveys briefly normal with medians207/69features;
  camera/frame pipeline alive. Loaded sessions have zero seq gaps, ages~60–70ms.
- Phone event download confirms31low-double/2healthy heartbeat attempts.
  Saved-map starts time out30s or end Session stopped before deadline. Stops'
  UI/background/other-client origin not logged. First WALL holds, retries once
  and aborts19:43:22; second WALL19:48:18 retries19:48:49, holds at end of copied
  Pi log19:49:04; phone later stops19:49:14. No successful map amendment/save.
- Darkness/changed appearance is plausible, not measured. Recommend normal
  room lighting and same saved starting view; preserve old seed. Apple session
  guidance supports reduced relocalization reliability with changed lighting.
  No evidence here establishes CPU/thermal overload or a dead camera/link.
- Details/events/metrics saved output/roomtrek-dark-20261109-1942. No source/
  configuration changes, AR commands, movement or deployment; read-only logs.
