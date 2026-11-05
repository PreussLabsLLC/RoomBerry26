<!-- @(#)grout-run-controls.md 3.1.grout.19 2026/11/05 -->
# November 4 run controls and wheel-size adjustment

Pi control build: `3.1.grout.19`. Open the Pi's `/` local console and press
**Check version** (or **Refresh all**). The page displays the running Pi control
version, wheel-size factor and Roomba firmware release when available.

## Wheel-size adjustment

Using the requested provisional reference:

| Quantity | Value |
| --- | ---: |
| Tag 15 to threshold | 4799 mm |
| Roomba body radius | 174 mm |
| Assumed actual travel | 4625 mm |
| November 3 threshold checkpoint odometry | 4583.020565923183 mm |
| Actual / odometry factor | 1.0091597743 |
| Adjustment | +0.915977% |
| Equivalent nominal wheel diameter | 72.659504 mm instead of 72 mm |

The Pi applies this common factor once to encoder-derived left and right wheel
distances, so cumulative distance, travel, heading and subsequent map integration
use the adjusted wheel size. The fallback OI distance/angle path uses the same
factor. Wheel-speed commands are unchanged. Raw sensor packet values and encoder
counts remain raw; archived runs are unchanged. The factor is reported in
`/status.json` and defined in `roomberry_control.py`.

This uses the first threshold-stop checkpoint, not total out-and-back path.
The reference is approximate and assumes the requested start/contact geometry;
it does not establish an independently measured wheel diameter. A 20 mm error
in the assumed distance changes the factor by about 0.00436 (0.44 percentage
points). The map's start offset below is separate from this requested formula.

## Grout out-and-back mission

Align the robot at tag 15, facing it, over the single grout stripe. Keep the
GridRunner phone set to **Reverse** and streaming throughout the whole mission.
Update/restart the Pi, verify build **3.1.grout.19**, then press Clock or the web
**Start grout out-and-back** button once. Clock again or web Stop cancels.
No iPhone rebuild or direction change at turnaround is required.

1. **Outbound:** reverse at 100 mm/s with existing bounded steering. The first
   fresh explicit no-line report brakes immediately. Confirm the stripe end
   while stationary for at least one second and three distinct no-line frames.
   Three consecutive fresh high-confidence line frames instead cancel the
   check and resume travel. No distance gate: this also works after a mid-route
   restart. Ambiguous checks time out stopped after three seconds.
2. **Turnaround:** record the confirmed line-end distance and settled distance,
   then move forward 150 mm at 30 mm/s with equal wheel speeds in Safe mode
   to put both phone scan bands over grout. Allow up to one additional second
   stopped for three good line frames before tag recovery. There is no in-place
   turn or native dock seeking. Phone impacts are safety stops, not successful
   threshold markers. The one-second stationary confirmation replaces the old
   post-impact hold.
3. **Return:** stop for stationary Pi AprilTag scans at estimated robot-center
   distances of **2000, 1500, 1000 and 500 mm from tag 15**. These are distances
   to the surveyed tag point, not remaining distances to the initial center.
   Prior to a tag fix, wheel odometry uses the provisional initial alignment.
   Each accepted scan updates world pose and the map anchor. Bounded forward
   heading feedback steers toward the contact point one robot radius before
   tag 15; desired heading is limited to ±0.2 rad around the tag normal.
4. **Final approach:** the 500 mm checkpoint must produce a reliable tag-15
   fix. Up to three stationary attempts are allowed. Then approach at 30 mm/s
   until the front bumper contacts near the predicted tag position. Success
   requires center-to-tag plane gap within radius−100 to radius+75 mm,
   lateral error at most 75 mm, and heading error at most 0.2 rad. Contact
   elsewhere aborts. Further phone impacts on return abort, except a coincident
   verified final front-bumper endpoint, which completes the mission.

Pi tag-15 return scans reuse the existing pose quality, Hamming, margin,
physical-plane and room-bound checks. A separate checkpoint solver allows
camera range up to 2.5 m, so the 2 m stop can work; normal navigation's 1.2 m
per-tag gate is unchanged. Scans inconsistent with predicted position by more
than 500 mm or heading by more than 0.35 rad are rejected. A failed far scan
is recorded and return proceeds to the next checkpoint using wheel estimates;
a failed final scan stays stopped and eventually aborts. Steering remains
heading-only near the final 50 mm of longitudinal approach, rather than
spinning in place to chase small lateral noise.

### Bounds and diagnostics

Only a fresh explicit line-loss packet permits slow continuation. Stale phone
frames/health, phone stop, camera/IMU errors, hazards, unexpected bumper contact,
reset/session/configuration changes and invalid odometry still stop. The
outbound no-line allowance is at most **30 s or 750 mm**, and the outbound
travel cap remains **5000 mm** even if no bump occurs. The total mission timeout
is 600 s. Three seconds without wheel progress aborts. A scan has a 20 s timeout.
Final approach aborts if it passes radius−50 mm estimated range or travels more
than 650 mm beyond its final tag fix without bumper contact.

The independent 600 ms motor lease remains active while moving and is ended
while intentionally stopped for turnaround/scans. It is restarted before
resuming; scan duration never extends a live moving lease. All four scans are
stationary. Periodic or manual scans during other moving stages are declined.

The phone overlay continues to display its original correction. Pi samples
show the applied correction, stage, slow/locked tracking state, wheel distance,
heading and speed. `/status.json` includes threshold onset/settled distance and
checkpoint results. Use Refresh all for snapshots. Physical validation remains
pending; the full software model includes line losses, drivetrain yaw bias,
real tag projection/pose solving, checkpoint scan callbacks and bumper finish.

## Visited cookies and map

Calibration and grout runs now integrate wheel motion into a separate map trace
and mark visited cookies green. They use the existing cookie storage's `mowed`
state for visits even though experiment cleaning motors remain off.

The provisional start is one body radius in front of surveyed tag 15, facing the
tag (+X in the current survey). This is an assumed manual alignment, not a tag
measurement. `/status.json` exposes `run_map` and `run_map_reference`; `/map.png`
labels the estimated run trace. Coverage checks only nearby footprint cells;
active experiment map updates never write/fsync the map to disk. Persistence
occurs when the run ends. Reload `/map.png` to monitor progress. Accepted return
tag scans replace this provisional anchor. The whole automatic out-and-back
shares one continuous map origin. This map
trace never supplies a localization fix to autonomous navigation. A measured
center-to-tag offset is needed to refine absolute placement; relative movement
is recorded regardless. Normal clean/discovery navigation localization is unchanged.

## Local controls and reset

The local console provides grout out-and-back, calibration, discovery, clean,
manual mode and stop controls. **Seek charging dock** is the separate native
Roomba docking operation, separate from the grout mission's return to tag 15.
The page also provides **Reset Roomba**, using the standard queued driver
reset. Commands only run when pressed. Manual mode selects the existing
manual-control pathway; it does not itself move the robot.

The raw serial wake/reset bypass was rolled back: neither it nor the separate
version.py experiment reliably woke an undocked sleeping robot. Startup again
uses its original separate START, delay, and RESET sequence. Reset does not
claim to wake the robot from sleep in the field.

Deployment: update/restart the Pi service using the usual local workflow, then
verify `3.1.grout.10` in the console. No iPhone rebuild is required for these
changes. No deployment or physical robot motion was performed during development.

### Return to tag 15 from the current position

**Return to tag 15** now stops/takes over any current mission and starts an
independent homing operation. It does not require a threshold event, a previous
run, the same phone session, a grout lock, or an active phone stream. It can also
be requested while a Pi scan is active; a fresh stationary result is queued.
See the build 3.1.grout.10 section below for localization and route behavior.
Hard safety stops still require explicit recovery; after a wheel drop, ground
the robot and use **Restart OI**, then wait for Sensors Ready.

### Return steering, scans and bump indication (build 3.1.grout.6)

Before the final approach, a usable grout observation now controls return
steering with the forward-travel angle sign. Before any accepted tag fix,
wheel-estimated world pose cannot override the observed stripe. After a tag
fix, steering combines 75% grout correction and 25% bounded tag-heading
correction. At the final approach, the accepted tag pose controls the endpoint.
Logs include both steering components and whether a tag fix has been applied.
Without a final tag fix, return travel with an absent line is bounded by the
same 30 seconds / 750 mm allowance as outbound travel.

AprilTag detection runs in a persistent spawned worker process, separate from
serial polling and phone reception. Native detector calls cannot hold the
control process's Python GIL. A 10-second detector timeout terminates its worker;
telemetry freshness and scan safety guards are unchanged.

Checkpoints remain pending until their results are processed. If a scan aborts,
**Return to tag 15** retries that checkpoint instead of skipping it. A failed
final scan remains pending, and an additional distance gate always requires a
successful final fix before approach, even if the checkpoint list is empty.
An in-progress camera scan must finish before a stopped mission can resume.

The blue dirt/debris LED latches when a new phone impact or physical bumper
contact is detected. It clears on mission mode changes, including entry to idle.
A held bumper does not repeatedly relight it after that reset. Outbound to return
is a stage change within GridRunner, so the threshold indicator stays lit until
a mode change. LED serial writes remain owned by the I/O thread.

Build 3.1.grout.6 raises line-loss slow travel to 30 mm/s in both directions.
Cruise remains 50 mm/s; the tag-guided final approach remains 20 mm/s.

### Steering pad and startup preview (build 3.1.grout.7)

The local console's steering pad provides robot-relative left/right turns of
5 degrees and forward/backward moves of 50 mm. Each click pauses the current
mission, enters Safe manual control, measures progress from wheel odometry,
then brakes and returns to idle. It does not restart the mission automatically.
Actual measured movement is shown beside the pad and recorded in the log.
Sampling, braking and wheel slip limit physical precision.

Only one step runs at a time. Other pad movement buttons lock during a request;
the central Stop and main Stop / idle remain available. Sensor freshness,
bumper/cliff/wheel-drop guards, odometry continuity, wrong-direction detection,
a 1.5-second no-progress guard, a 6-second overall timeout, and the independent
600 ms motion lease bound each move. Scans must finish before a step can start.
This uses the existing measured turn/distance counters, not a timed drive.

Intentional pad motion updates a retained grout pose while moving, so normal
small adjustments do not create the discontinuity caused by unobserved pushing.
After a threshold run, **Return to tag 15** can resume using that updated pose.
If earlier unobserved movement or a reset already invalidated the trace, the
pad permits positioning but does not invent a replacement return pose. Phone
mount/configuration checks and return heading limits remain in effect.

Startup now logs the first 80 decoded boot-stream characters with escaped
control characters before attempting firmware-version parsing. The parser and
serial startup sequence are unchanged; inspect this preview when the firmware
release still reads unknown.


### Camera-centered grout target and full startup text (build 3.1.grout.8)

Align the downward camera over the grout, with the robot facing tag 15.
The desired robot-relative grout offset now equals the phone's measured
`lens_left_mm`. For a +26 mm rear-left mount, the robot center runs 26 mm
robot-right of the grout. Both outbound and return line steering subtract
this target before computing correction. The physical mount calibration stays
unchanged. The provisional start pose, map and tag-guided contact point also
include this lateral offset. Physical contact and heading limits are unchanged.
Phone and Pi logs retain raw robot-relative offset; Pi samples additionally
record `target_offset_mm` and `tracking_error_mm`. The local console displays
the latter. The updated iOS app shows the camera-centered cyan target and
error and rotates the preview plus overlays 90 degrees clockwise. Detection
and packet coordinates remain unchanged by the display rotation.

Startup logs the complete boot read with binary/nonprinting bytes removed,
preserving printable ASCII, tabs and line breaks, before version parsing.
The escaped 80-character prefix remains available for byte-level diagnosis.
The original boot message and firmware parser are preserved.

A pit-stop wheel-compliance mode is deferred. The current controller sends
OI STOP on wheel drop and requires explicit rearm, so simply lifting the
robot would interrupt such a test. No guard override is introduced here.
A future plan should distinguish floor-loaded response from free-running
wheel response; a roller fixture would need to keep the suspension loaded
and retain the independent stop/watchdog behavior.

### Changes for the next two runs (Pi build 3.1.grout.9)

**Restart OI** is now a main local-console button. Put the robot on the floor,
press it after a wheel-drop stop, and wait for Sensors Ready. The console polls
readiness briefly after this explicit command. Restart cancels the mission,
discards the old grout trace because the odometry epoch changes, and enters
Passive; it never resumes motion. The existing fresh-grounded startup
qualification remains required. Stop and ordinary Reset are not rearm commands.

Below cruise speed, heading correction now uses in-place pivots at 30 mm/s
opposite wheel speeds followed by equal-wheel straight travel. It no longer
asks an unreliable 15/25 or 22/37 mm/s pair to steer. Alignment begins above
5 degrees of error and ends within 2 degrees. Pivot wheel progress counts as
motion; a pivot that initially moves the wrong way by more than 1 degree aborts.
Final approach retains 20 mm/s nominal straight travel. Cruise steering stays
at 50 mm/s. Actual pivot/straight wheel commands, steering mode and heading
error are logged. All contact, frame freshness, heading and motor-lease guards
remain active.

After the first accepted tag fix, later fixes must agree with its wheel-projected
pose within 200 mm and 8 degrees, in addition to the original quality, range,
room and straight-envelope checks. An inconsistent far checkpoint is tried
once more, then rejected without replacing the last pose. Final approach needs
two stationary final poses agreeing within 75 mm and 4 degrees, within three
attempts total. A failed final check leaves the robot stopped. Scan results now
play happy/unhappy tones; a final pose awaiting confirmation plays neutral.
A short stationary pause lets the tone finish before another song replaces it.
The serial owner continues polling during that pause; the moving lease starts
afterward. Stationary scan time no longer consumes the moving line-loss timer.

Pad braking now begins 12 mm or 3 degrees before the nominal endpoint, based on
observed extra movement after braking. This is provisional compensation: check
the measured result in the console/log. A mode change refreshes the cached OI
sensor sample before the next drive, addressing the first-press Safe-mode race.

The threshold/roll-down phone-impact stop remains active. Use the forward pad
and explicit Return to tag 15 if needed. These are Pi-only changes; the already
installed GridRunner build 2 remains compatible. Pit-stop mode is still deferred.


### Independent tag-15 homing and lost-line fixes (build 3.1.grout.10)

Return to tag 15 first brakes and cancels the previous mission, including an
interrupted outbound, manual step, waiting state, or discovery/cleaning mode.
It starts fresh stationary localization using any surveyed tag with existing
quality/plane/room checks and a 2.5 m range limit. Two poses must agree within
75 mm and 4 degrees. A still-continuous saved pose can bridge a missing distant
or out-of-view tag; an epoch reset or an unobserved wheel jump cannot reuse it.
No unlocalized return is seeded at tag 15 on the map.

With no usable pose, the robot searches up to eight stationary camera views,
45 degrees apart, using measured in-place turns only. There is no translation
until a position is established. If no mapped tag is found, it stops and asks
for repositioning where a tag is visible. Ordinary stale sensors, low battery,
bumper/cliff/wheel-drop and motion-lease stops remain active. Restart OI is
explicit, not an automatic part of homing.

Once located, homing plans a mapped route to a staging point 400 mm before the
normal robot-center contact point. It uses pivot-then-straight motion, checks
known-map clearance, refreshes localization at approximately 400 mm intervals,
and aims the camera at tag 15 before acquiring two final fixes. Later fixes
must agree with wheel-projected pose within 200 mm and 8 degrees. After a
confirmed fix, 1200 mm without another fix stops travel. The final tag-15
corridor and front-contact heading/position checks still apply. Close approach
has bounded travel and independent contact stops. Phone health is optional;
new phone-impact events are still honored if that stream is present.

For ordinary grout following, pivot decisions now use the uncapped geometric
heading error, not the capped wheel correction. Entering line-loss recovery
freezes the last reliable heading until stable reacquisition. Motion requires
line confidence at least 65%; restoring cruise requires three distinct usable
observations at 75% or higher. Isolated weak detections cannot move the anchor.
The console explains the confidence requirement while waiting.

These changes affect the Pi only; GridRunner iOS build 2 remains compatible.
Homing availability is no longer tied to a threshold leg, but successful travel
still requires a valid pose, a clear mapped route and safe sensor state.

### Higher-speed grout experiment (build 3.1.grout.11)

Normal grout-run base speed is now 150 mm/s, slow/reacquisition and final
approach 30 mm/s; pivots remain 30 mm/s per wheel. Existing differential
steering adjusts individual cruise wheels around the base speed. No calibrated
wheel deltas are applied in this experiment.

Grout movement commands explicitly bypass the shared acceleration/deceleration
ramp. Changes between cruise and slow speeds are direct; command changes that
require stopping use immediate braking instead of soft-stop ramps. The I/O
owner retains motion qualification, hard safety and the 600 ms lease. Other
missions retain their configured ramp behavior. Independent Return to tag 15
homing retains its separate speeds. Historical speed notes above describe older
builds; use the values in this section for the current grout experiment.

Update/restart the Pi and verify **3.1.grout.11** before testing. No iPhone
rebuild is required. The higher speed is experimental; line freshness checks,
slow-mode limits and threshold impact handling remain active.

### Stepped speeds, transient phone bumps and persistent mode display (3.1.grout.12)

Grout starts use 0 -> 30 -> 150 mm/s, holding the intermediate step for
200 ms. Normal scan/action stops use 150 -> 30 -> 0 with the same dwell.
Cruise steering still adjusts the final wheel pair; the intermediate travel
step uses equal 30 mm/s wheel magnitudes. Slow travel/final approach remain
30 mm/s and pivots use opposing 30 mm/s wheels. No continuous low-speed
ramp is introduced. Emergency, hard-hazard, bumper and real phone-impact
stops remain immediate. Pending acceleration is canceled by a hard stop.

Every actual changed wheel-velocity pair starts a 150 ms phone-impact-ignore
window, including steering retunes and stops. Identical reissued commands do
not extend the window. The event's phone timestamp is mapped to Pi receipt
time and compared against actual serial-write history, so delayed processing
does not replay a launch bump after the window. Network latency remains an
approximation. Ignored events are consumed, logged with count, peak, stage,
before/after wheel speeds and elapsed time, and do not set the phone-bump LED
or change mission stage. Physical bumper/cliff/wheel-drop responses remain
active. The same transient filter covers standalone tag return.

Mode text is rewritten at least once per second while sensor polling and OI
communication are available, and immediately refreshed after OI/beep mode
transitions. Scans retain the current mode label instead of replacing it with
SCAn. Display recovery never rearms an OI wheel-drop stop. These measures
address firmware LED clearing that a changed-label-only cache cannot detect;
they cannot illuminate a powered-off/disconnected robot.

Verify **3.1.grout.12** after Pi sync/restart; no iPhone rebuild is needed.
Earlier build sections record prior experiment behavior.

### Settled pivot verification and 100 mm/s cruise (3.1.grout.13)

Current grout cruise base speed is 100 mm/s, slow and final approach 30 mm/s.
Starts step 0 -> 30 -> 100 and normal stops reverse that sequence. Cruise
steering still adjusts individual wheels around the base speed. The existing
150 ms phone-impact filter and mode display refresh remain active.

Both grout recovery and standalone tag homing now share SettledTurn in
roomberry_turn_guard.py. Before entering a pivot, reversing one, or translating
after a pivot, it brakes immediately and waits for fresh post-stop encoder
samples showing <=2 degrees/s yaw and <=5 mm/s center travel for at least
150 ms. Waiting is bounded at 1.5 seconds; stale/repeated snapshots cannot
qualify. The mission keeps its 600 ms motion lease alive while stationary.

Direction verification is armed only after pivot dispatch, and the reference
heading comes from a subsequent sensor poll. Polls predating that command
are never evidence of a wrong-way response. Sustained wrong motion (>3 degrees
on two distinct samples, after startup) or a large >8-degree wrong excursion
still aborts. These replace the old immediate 1-degree check anchored before
braking. Observed turn rate also prompts earlier braking near the target,
followed by a fresh assessment after settling. Sensor/motion/settling limits
remain active and the log records brake, settle, dispatch and reference events.

The status sample uses steering_mode=settling while holding zero. Sync the new
roomberry_turn_guard.py along with the modified modules, restart the Pi and
verify **3.1.grout.13**. No iPhone changes required. Threshold-exit impact policy
and map-route shortcut changes are separate from this turn-control fix.

### Record weak impacts, follow visible grout, recover with tags (3.1.grout.14)

Pi reaction cutoff is **0.5 g (4903.325 mm/s²)**, doubling the former lowest
0.25 g branch for grout/tag-return decisions. The phone still records its
original lower-threshold episodes and acceleration peaks; no iPhone rebuild
is needed. Weak events are logged record-only. If the same episode's updated
peak later reaches 0.5 g it can react then. Speed-transient suppression remains
150 ms, and suppressed events are not replayed. Unknown peak strength is not
silently suppressed. Physical bumper/cliff/drop protections remain immediate.

A fresh usable grout observation exclusively controls return steering, including
the 30 mm/s final approach. Accepted tag poses update position without adding
a steering bias to a visible line. The old return heading envelope cannot
steer away from an otherwise valid visible stripe.

After one second without a usable return line, stop and enter mapped-tag
localization/search rather than continuing blind for 30 s/750 mm. Failed final
checkpoint localization or a predicted contact-plane overrun also gets a fresh
tag recovery attempt before idle. This does not authorize driving past an
unverified contact bound; up to three recovery handoffs are permitted.

Tag homing (automatic recovery or the explicit Return button) holds zero while
confirming three distinct good line frames and then hands back to grout following
when homeward orientation is known. A retained original heading can establish
that orientation despite a biased tag yaw; an arbitrary backwards-facing robot
is not sent away from home merely because it sees a line. Position/odometry,
phone identity and current bump policy are transferred across the handoff.
Tag-only routing shortcuts cell zigzags only when the entire straight segment's
swept footprint checks clear. Failed/ambiguous localization, blocked routes and
hard safety conditions still stop.

Cruise remains 100 mm/s, slow/final grout travel 30; standalone tag-only travel
keeps its own 50/20 settings until a line handoff. Sync the new
roomberry_phone_bumps.py as well as the modified modules, restart the Pi and
verify **3.1.grout.14**. Raw weak-bump logging requires no app installation.

### Completion after explicit tag-to-line handoff (3.1.grout.15)

A GridDrive created during explicit tag homing may have no outbound leg.
Its outbound_mm result field is now initialized to null/None, rather than
raising AttributeError after valid bumper arrival. Actual outbound missions
continue to report their measured leg distance. This fixes the Nov 5 09:18
arrival-report crash; other tracking/provenance findings are in the run review.

### Bump cutoff and longer steering steps (build 3.1.grout.16)

The Pi phone-bump reaction cutoff is now **0.6 g (5883.99 mm/s²)**.
Weaker events remain logged without stopping the mission; the existing 150 ms
speed-change suppression still applies. This supersedes the .14 cutoff above.
The blue bump indicator clears after 10 seconds, or sooner on a mode change.
A new bump restarts its timer.

The steering pad has **Forward 500 mm** above the arrows and **Back 500 mm**
below them. These robot-relative, wheel-odometry moves request 100 mm/s with
a 15-second motion timeout and retain the existing safety checks, motion lease,
predictive braking and Stop cancellation. The original 50 mm and 5° steps remain.
Routes are `step_forward_500` and `step_backward_500`; movement controls lock
until completion while Stop remains available. Actual floor distance depends
on wheel calibration and slip. Sync the Pi code and web assets, restart and
verify .16. No iPhone update is required.

### Threshold sensitivity and confirmed relocation (build 3.1.grout.17)

After 4000 mm of outbound encoder travel, the Pi reacts to phone events at
**0.5 g**, with speed-change suppression disabled in that approach window.
It logs entry into the window and rechecks a pending weak event without resetting
the event counter. Outside that window, **0.6 g** and the 150 ms suppression
remain. This is a Pi reaction policy; the phone continues detecting/logging its
original events. The 5000 mm outbound limit and other safety checks remain.
The 4000 mm window assumes the established tag-15 start; slip affects its timing.

Normal grout-return tag corrections retain the 500 mm outer gate and the
200 mm / 8° gate after an applied fix. A quality/map-valid fix outside those
gates now starts stationary relocation confirmation. Two fresh consecutive
scans agreeing within **75 mm / 4°** can replace the odometry prediction.
The straight-approach heading envelope remains required. Missing/invalid scans
clear the candidate; disagreement does not update the pose. Unconfirmed
relocation at a grout checkpoint hands off to stopped tag recovery.
Explicit tag return also allows confirmed relocation instead of rejecting
every disagreeing fix; it stays stopped if its bounded confirmation fails.
Final corridor, map-route clearance and hard-safety checks remain.
Logs identify confirmed relocation and include prediction innovations.
Sync Pi modules, restart and verify .17; no iPhone rebuild is needed.

### Grout-line end replaces threshold bump (build 3.1.grout.18)

The outbound behavior above supersedes .17 threshold bump re-arming: all stages
use the normal .6g phone reaction cutoff and existing transient suppression.
The first fresh explicit missing-stripe packet causes a hard stop with the
motion lease ended. Neither confirmation nor reacquisition moves the wheels.
Only new sequence numbers count. Stale phone/robot telemetry, stopped phone,
configuration changes and hazards still abort rather than being called a line
end. Confirmed loss enters return without waiting for a bump. Weak-confidence
visible-line readings alone cannot confirm the endpoint.

A prolonged unrelated dropout can also end the outbound leg early; this is
intentional in preference to driving blindly onto the ramp. Start aligned on
the stripe and keep phone streaming. The 5000mm outbound cap remains.
New logs distinguish line-end braking, cancelled checks and confirmed endpoint
metadata. No return-localization tolerances changed in .18. Sync the Pi grid,
control and web modules and restart; no phone update is needed.

### Threshold clearance and scan display (build 3.1.grout.19)

After endpoint confirmation, a dedicated `threshold_clearance` stage moves
150 mm forward at 30 mm/s before normal return tracking. It suppresses neither
robot hazards nor phone safety handling. Fresh phone/robot telemetry is required;
wrong-direction travel, no wheel progress for 3 seconds or 12 seconds total
aborts. No automatic tag scan or pivot interrupts this bounded clearance.
At 150mm the robot brakes; three distinct fresh good stripe frames release
normal return. Otherwise it waits stopped up to one second, then invokes tag
recovery. The wheel-based distance is approximate if the wheels slip.

The robot's four-character mode display shows `SCAN` while a camera scan is
active, even if the mission loop is occupied. It restores the current mode
afterward and retains the existing periodic refresh against firmware clearing
the display. Scan duration/acceptance rules are unchanged.

Sync `roomberry_gridrunner.py` and `roomberry_control.py`, restart and verify
.19. No iPhone rebuild is needed.
