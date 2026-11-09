<!-- @(#)wall-mission.md 3.1.wall.16 2026/11/09 10:40:00 -->
# WALL mission

Control build `3.1.wall.16`. Uses the Python server's `/` console and
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
   Anchor qualification times out after60seconds. No motion begins until accepted.
3. Turn left90degrees, advance200mm, turn right45degrees and approach slowly
   at30mm/s. Wheel-odometry targets have small braking tolerances; actual floor
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
   at30mm/s for30mm, requires cleared bumper/safety and an acknowledged stop,
   then releases the contact latch and turns left15degrees before rejoining.
   Contact during a wall-loss right search, an already active bypass, or
   in follow within500mm of travelled distance after a wall-loss search
   (cabinet corner hit head-on after a right sweep) selects the bounded
   left obstacle tactic. In front of the dishwasher
   close to the fridge a single large left turn overshoots the recessed
   front, so the first bypass attempt turns left20degrees only and keeps
   the contacted object's boundary on the right. If contact repeats while
   the bypass is active, the next attempt escalates to left90degrees. It
   does not identify the fridge by vision or guarantee a mapped route
   around it.
   Isolated side-wall contacts retain the small15degree correction.
   If contact persists, reverse at most50mm or5seconds and abort. Forward/spin
   commands are blocked while the contact latch is set; only bounded reverse
   and stops are allowed. Recovery has a separate forty-two-event limit; acquisition retries do not consume it. Contact during
   initial departure remains an abort, and cliffs/wheel drops always abort.
9. Rejoin uses measured right turns and short straight advances. Every nonzero
   WALL wheel command is at least30mm/s in magnitude; stops remain zero. This
   minimum also applies to approach, reverse, pivots and tracking corrections.
   It is a commanded-speed floor, not independently measured body speed.
   Before a low-signal search, stop and collect three fresh settling frames.
   Then turn right in measured steps using right=-30,left=30, and advance30mm
   using both wheels=30 between turns. On>=20 IR units, stop and confirm three
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
   After>=200mm and three fresh >=20 readings within20deg of entry heading,
   return to normal tracking. This is a heading/IR handoff, not identification
   of the original room wall. Contact/cliff/stall guards remain active.
10. Follow at nominal35mm/s with proportional/derivative control centred on
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
   At 5000mm total wheel travel (about1.5m past the fridge in the 3.5m
   run), follow stops and enters a `tag15_scan` stage: request camera scans
   until two fresh tag-15 fixes agree within75mm/0.1rad, then finish
   complete. Tag 15 is at the same y as tag 16 so it should be in view
   while following the wall.
   A bump or stalled drive during a wall-loss search takes priority and starts
   the left bypass, rather than continuing to push or repeatedly steer right.
   Contact is handled as above; no automatic motion is permitted through a hard hazard.

Each forward approach has a25second stage limit; the cumulative bounds above
cover the entire acquisition/alignment sequence. Trial ends at6metres of accumulated
wheel travel or240seconds; following itself has a180second limit. These are
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
This mission does not start the phone app or save an AR map. The initial tag
anchor qualifies departure; driving does not require continuous tag visibility.

## HTTP and deployment

- `/roomba/?op=wall`: idempotent start; does not rearm an OI stop.
- `/roomba/?op=stop`: stop and cancel the mission.
- `/roomba/?op=wall_capture_100mm`: retired; returns an explanatory error.

For this wall.16 update over wall.15, sync `roomberry_wall.py`,
`roomberry_control.py` and `roomberry_mission.py`,
restart the service and verify version `3.1.wall.16`. No physical trial has been
performed as part of this implementation.
