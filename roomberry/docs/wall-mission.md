<!-- @(#)wall-mission.md 3.2 2026/11/09 18:53:01 -->
# WALL mission

Control build `3.2`. Uses the Python server's `/` console and
`/status.json`. Clock starts WALL and a second press cancels it. Clock also
cancels active calibration or GridRunner; start GridRunner from the console.
No files in the legacy web-app are used or changed.

## Target and LED

WALL controls from **right light-bumper signal, packet51**, in a
**20–30 raw intensity band** (centre 25; documented sensor range0–4095).
Acquisition/rejoin qualifies at >=20, not a single 30. The controller
averages the raw signal over the latest four distinct sensor frames for its
decisions; a single spike therefore does not steer or qualify the wall. The corresponding
physical gap is unknown and can change with surface and angle. No distance
calibration or reference capture is required. The old100mm capture control is
removed from the dashboard/catalog; old requests explicitly fail without
changing the target. This supersedes the earlier100mm-reference experiment.

The four-character LED alternates each second between `WALL` and this same
sensor's live raw reading. For example, `  30` means30 intensity counts, not30mm.
Zero displays as `   0`; unavailable/out-of-range readings show `----`. One
sample is held for each numeric second. SCAN takes priority during scanning.

## First trial

1. Position the robot facing known tag16 and press Clock or **Start WALL**.
2. While stopped, obtain two fresh tag16 fixes agreeing within75mm and0.1rad.
   With the RoomTrek coordinator enabled, first hold stopped for loaded-map
   relocalization (one bounded AR restart permitted). Only then request fresh
   tag16 scans and require successful phone pairing. Total startup is bounded
   by120seconds, with at most60seconds for anchor qualification after readiness.
   No motion begins until both are accepted. With the integration disabled,
   existing tag-only60second startup behavior remains.
3. Turn left90degrees, advance200mm, turn right45degrees and approach slowly
   at50mm/s. Wheel-odometry targets have small braking tolerances; actual floor
   distances and angles still require physical validation.
4. Three distinct right light-bumper samples at or above20 stop the approach
   as an **IR candidate**, not proof of reaching the intended wall. The operator
   reported the first candidate was still more than200mm from the board.
5. Probe the left alignment in steps of at most15degrees toward a total45degrees.
   After each step, stop and require three distinct fresh stationary readings
   of at least15 units. Only enter following after the full turn and successful
   checks. This qualifies usable signal across the turn, not a measured distance
   or independent identification of the intended wall.
6. If a check loses signal, return to the candidate's original approach heading
   and advance at least another50mm before a repeated20-unit signal can qualify.
   Permit at most four such re-approaches, within a600mm net-forward envelope from the first
   approach point and90seconds covering all probes/returns/re-approaches.
   No continued circling or unbounded threshold retries.
7. Bumper contact brakes in the serial owner as soon as a successful sensor
   poll reports it, and latches the stop even if the switch releases before the
   mission tick. The owner also detects forward wheel stalls: both motor currents
   at least350mA and encoder translation below0.5mm per fresh poll for200ms.
   This is scoped to WALL with both wheels commanded forward, not reverse/turns.
   It is a stalled-drive indication, not a fabricated physical bumper reading.
8. During acquisition/alignment/following, either event stops first, reverses
   at50mm/s for30mm, requires cleared bumper/safety and an acknowledged stop,
   then releases the contact latch and turns left15degrees before rejoining.
   Contact during a wall-loss right search, an already active bypass, or
   in follow within500mm of travelled distance after a wall-loss search
   (cabinet corner hit head-on after a right sweep) selects the bounded
   left obstacle tactic. In front of the dishwasher
   close to the fridge a single large left turn overshoots the recessed
   front, so the first bypass attempt turns left20degrees only and keeps
   the contacted object's boundary on the right. If contact repeats while
   the bypass is active, the next attempt uses a limited left45degree turn. It
   does not identify the fridge by vision or guarantee a mapped route
   around it.
   Isolated side-wall contacts retain the small15degree correction.
   If contact persists, reverse at most50mm or5seconds and abort. Forward/spin
   commands are blocked while the contact latch is set; only bounded reverse
   and stops are allowed. Recovery has a separate forty-two-event limit; acquisition retries do not consume it. Contact during
   initial departure remains an abort, and cliffs/wheel drops always abort.
9. Rejoin uses measured right turns and short straight advances. Every nonzero
   WALL wheel command is at least50mm/s in magnitude; stops remain zero. This
   minimum also applies to approach, reverse, pivots and tracking corrections.
   It is a commanded-speed floor, not independently measured body speed.
   Before a low-signal search, stop and collect three fresh settling frames.
   Then turn right in measured steps using right=-50,left=50, and advance30mm
   using both wheels=50 between turns. On>=20 IR units, stop and confirm three
   fresh readings before resuming follow. If already at target, qualify stopped
   without turning. Do not repeat initial acquisition/45degree left alignment.
   Contact rejoin uses5degree steps bounded by30degrees right or10seconds;
   wall-loss (recessed-front) search uses10degree steps bounded by60degrees
   right or20seconds; the former100mm per-rejoin cutoff is removed. The
   larger wall-loss sweep seeks a recessed front line such as the dishwasher
   in front of the fridge, where a wall or obstacle is expected after turning
   right.
   During obstacle bypass, use15degree measured right steps and50mm advances,
   bounded by90degrees/25seconds; the former350mm search cutoff is removed.
   Complete bypass remains bounded by1500mm accumulated encoder path/90seconds.
   At that limit, stop and try one bounded tag15 look: current heading, then
   +10degrees and -10degrees relative to that stopped heading. Each view takes
   two fresh captures without a fix, or up to four with an unconfirmed candidate.
   Pivots use50mm/s opposite wheels, stop within3degrees, and allow8seconds each.
   The complete look allows75seconds, at most25mm centre translation and a hard
   +/-15degree angular envelope. Contact or other safety failures abort it.
   If no consistent tag15 fix is found, remain stopped and abort explicitly.
   Two agreeing captures can resume the bounded approach below. A dedicated
   stationary tag15 solver permits2500mm camera range while preserving the
   normal localizer's1200mm gate and its quality/room-bound checks.
   After>=200mm and three fresh >=20 readings within20deg of entry heading,
   return to normal tracking. This is a heading/IR handoff, not identification
   of the original room wall. Contact/cliff/stall guards remain active.
10. Follow at nominal80mm/s with proportional/derivative control centred on
   25 and a 20–30 deadband. Inside the band the robot drives straight; above
   30 it steers left, away from the right wall; below 20 it steers right,
   toward it, while the wall signal remains usable. Single-frame dips do not
   immediately declare wall loss.
   If the latest four raw IR samples spread by more than20 units, the
   robot stops, records `wall_signal_fluctuating`, and holds stopped for1s
   to collect fresh stationary samples before resuming, rather than
   steering on the fluctuation. A reading below7.5 during following
   first stops and ends the moving lease, then starts the bounded right search
   above instead of aborting after the previous1.5s wait. Permit at most eight
   wall-loss searches per run, in addition to the separate forty-two contact recoveries.
   The goal is a validation scan with the **robot centre within300mm of
   surveyed tag15**, not a fixed wheel distance. A separate wheel pose is
   integrated from the qualified tag16 anchor. At its estimated300mm range,
   or a5000mm checkpoint, park, face the tag using a bounded pivot if needed,
   and request stationary scans. Completion requires two distinct captures
   made after parking, accepting tag15 and agreeing within75mm/0.1rad, with
   measured robot-centre range<=300mm. A wheel estimate alone cannot complete.
   If the stable tag fix remains farther away (up to2500mm), advance toward
   the tag in at most100mm measured segments, then stop and scan again.
   Use50mm/s for those segments/pivots, at most24 steps/180seconds. A missing
   tag, disagreeing fixes, unexpected contact or exceeded bound causes an
   explicit abort rather than assuming arrival. Camera-to-tag range differs
   from the robot-centre radius by the calibrated camera offset.
   Tag validation events record the wheel-predicted pose and tag correction.
   A bump or stalled drive during a wall-loss search takes priority and starts
   the left bypass, rather than continuing to push or repeatedly steer right.
   Contact is handled as above; no automatic motion is permitted through a hard hazard.

Each forward approach has a25second stage limit; the cumulative bounds above
cover the entire acquisition/alignment sequence. Run aborts without claiming success at8metres of accumulated
wheel travel or360seconds after qualified departure; following itself has a180second limit. These are
trial limits, not room-loop completion. Cliff/wheel-drop, stale/failed sensors,
low battery, odometry reset/discontinuity, wrong-way motion and stalled wheels
abort. The I/O owner enforces an independent0.6second motion lease. Stop/idle
and mode changes cancel the run. Removing the short search-distance cutoffs
does not remove no-progress, angle, timeout or whole-mission travel bounds. Deliberate stops disarm the lease only after
an acknowledged stop, and resumed motion starts a new lease. Stopped alignment
checks and signal-loss waits therefore do not falsely trigger lease expiry;
an unexpected moving-lease expiry has its own abort reason. Connector/overhang clearance and survey camera
visibility remain unverified by these low-mounted intensity sensors.

If contact arrives after a mission snapshot but before drive execution, the
serial owner still rejects that move and holds the brake. WALL recognizes that
specific contact-stop rejection, fetches fresh state and rechecks all guards
before entering recovery. An unconfirmed latch, stale state, hard hazard or any
unrelated driver error does not authorize a retreat. The rejected forward
command is never retried.

## Status and records

WALL clears map coverage on start and records the dead-reckoning pose from
the tag16 anchor as a trail polyline, even when no tags are visible.
The console shows stage, right light-bumper target/current value and stop reason.
`/status.json` exposes `wall.sensor`, `sensor_packet`, `target_signal`,
`target_min`, `target_max`, recent
events and the latest sample. No desired or measured physical clearance is
claimed. Robot logs contain `WALL sample`, `WALL event` and `WALL drive` JSON
records including commanded wheel speeds. Sensor CSV retains both old wall
and right light-bumper channels for comparison.

RoomTrek remote survey/save/navigation commands, type6 receiving, IMU fusion
and the full survey-versus-navigation validation circuit remain subsequent work.
This mission cannot launch a backgrounded phone app. The configured Pi survey
coordinator resumes/saves the AR map and WALL holds for startup readiness.
The initial tag/phone anchor qualifies departure; driving does not require continuous tag visibility.

## HTTP and deployment

- `/roomba/?op=wall`: idempotent start; does not rearm an OI stop.
- `/roomba/?op=stop`: stop and cancel the mission.
- `/roomba/?op=wall_capture_100mm`: retired; returns an explanatory error.

For this wall.16 update over wall.15, sync `roomberry_wall.py`,
`roomberry_control.py` and `roomberry_mission.py`,
restart the service and verify version `3.1.wall.16`. No physical trial has been
performed as part of this implementation.


## 3.2 speed and direction-transition changes

The12:38 run's stable30mm/s commands produced median encoder speeds of about
39–42mm/s, and35mm/s commands about40mm/s. This supports avoiding that low-speed
range; it does not prove firmware intent or true body speed. Set the moving
wheel floor to50mm/s and cruise to80mm/s, with the existing35% steering cap
(roughly52–108mm/s before integer rounding). These are provisional commands,
not guaranteed real speeds. Stops remain zero; contact, cliff, wheel-drop,
lease, stale-sensor, odometry and no-progress guards remain active.

After a new wheel-sign pattern or a stopped-to-moving transition, the first
fresh sensor sample establishes a direction baseline. It may include coast
from the previous command and is not judged against the new command. Later
fresh samples must agree with the commanded direction; continuing wrong-way
motion still aborts. All mission-snapshot travel remains counted in path bounds.
This fixes the recorded forward-coast/reverse-transition false abort without
removing the direction guard. The independent movement lease still brakes if
the mission loop stalls.

Additional spoken codes cover anchoring, wall acquisition/loss/search/rejoin,
contact release, fridge bypass, tag15 approach/validation, completion/abort,
map save and unavailable phone. See [speech catalogue](speech.md).

The speed floor, terminal approach and scan quality require a physical trial.
Pi uploads remain with the operator; no deployment is implied by host tests.


## Tag16-aligned phone comparison

The initial qualified tag16 pose also establishes a fixed RoomTrek room-frame
alignment using the dashboard mount’s optical-forward correction (20° left,15° up)
and lens offset(10mm forward,180mm left).
A separate wheel trace and aligned phone robot-centre trace are logged without
steering corrections. See [alignment and next-run plotting](roomtrek-alignment.md)
for pairing, reset behavior, mount assumptions and required Pi uploads.

Explicit **Return to tag15**, including recovery after manual steering, now also
parks at estimated300mm and requests a validation scan. Two fresh agreeing
tag15 captures must confirm centre range<=300mm before reporting completion
and speaking TAG15_VALIDATED. Missing/disagreeing fixes or a measured range
outside300mm stop explicitly; wheel estimates cannot complete the run. Existing
contact, close-range and travel guards remain. This replaces the old bumper
approach endpoint for standalone mapped-tag return.

Lucky-scan pivots use the shared measured-settling controller through WALL's
acknowledged stop/lease owner. A0.12second pulse budget is checked each mission
tick (not a hardware timer); after each pulse, brake and require fresh encoder
samples showing at least150ms quiet, <=2degrees/s rotation and<=5mm/s translation
before another pulse, reversal or camera scan. Measured closing-rate braking
also applies. Moving wheels retain the50mm/s floor. The8second turn timeout,
75second look bound, +/-15degree angular and25mm translation envelope stay
unchanged; excessive coast or1.5second settling failure still aborts stopped.
Actual coast response needs the next physical run.
