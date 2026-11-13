<!-- @(#)report.md 3.1.wall.8 2026/11/08 19:00:00 -->
# Large correction was commanded; later contact caused a recovery race

Sources: uploaded application log and sensor CSV
roomberry-sensors-20261108-194434.csv. events-and-samples.csv preserves extracted
WALL telemetry for subsequent regression work. User reports excessive turn away
from the wall followed by a later stop.

## Why the large turn happened

-19:45:23.103: first right bumper during initial alignment, owner brakes.
- Retreat37.01 encoder mm, then left17.28deg for the nominal15degree correction.
  IR40 qualifies while stopped; following starts19:45:26.765.
-19:45:28.487: another right bumper after61.69mm of resumed forward odometry.
  The two contacts are less than200mm apart in accumulated encoder path.
- The wall.8 `nearby_repeat` rule treats this as an obstacle bypass, even though
  this alone cannot distinguish side-wall contact from a fridge obstruction.
  It explicitly selects90degrees left. After retreat30.28mm, the turn measures
  88.49degrees (yaw64.86→153.36). The large correction is therefore a commanded
  maneuver, not an unexplained90degree motor overshoot.
- The right corner search then advances150.29 encoder mm while turning right
  71.10degrees. Signal32 qualifies19:45:44.583; follow resumes at yaw82.26deg.
  The heading handoff returns to ordinary tracking19:45:45.188.

For the reported same-wall correction, escalation based only on proximity of
contacts is too eager. A more selective policy is needed: keep small corrections
for ordinary side-wall bumps, reserving the90degree left bypass for contact
encountered specifically during wall-loss searching (or separately established
frontal blockage). No visual fridge identification exists in this code.

## Why it stopped later

After resuming, following advances another363.62 encoder mm before the terminal
mission sample. At19:45:53.695 another right bumper is detected. The I/O owner
brakes and latches contact at53.698; the CSV's first contact row53.699 already
shows both applied wheel speeds zero. Hard hazards are absent.

A mission tick began with a pre-contact snapshot at53.660 and tried to send its
next forward drive. By execution, the contact latch was set, so the arbiter
correctly rejected that command with:
`WALL contact stop latched; back clear before rearming`.

The exception propagated through WallDrive.drive and tick into the generic
mission error handler. At53.875 the mission aborted with `mission update error`
instead of handling the newly arrived contact with its normal retreat/turn.
This is a contact-arrival race in mission recovery. The safety brake worked;
the command rejection must not be bypassed or relaxed.

## Next fixes indicated

1. Remove nearby repeated contact alone as a reason to command90degrees away
   from a wall; retain the small side-contact correction and the explicitly
   triggered obstacle-search bypass.
2. On a drive rejected by a freshly latched WALL contact, reread controller
   state and enter normal contact recovery. Other exceptions/hard hazards remain
   aborts. Add a regression that injects contact after snapshot but before drive
   execution, as happened here.

Analysis only. No runtime changes, deployment or robot commands.
