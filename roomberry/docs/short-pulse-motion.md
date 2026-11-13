<!-- @(#)short-pulse-motion.md 3.2.pulse.1 2026/11/12 16:09:50 -->
# Minimum wheel velocity and short tag-approach pulses

User instruction: do not request nonzero wheel speeds below42mm/s; use shorter
pulses instead. The previous run's20mm/s approach measured about42mm/s, and
opposite pivot corrections repeatedly crossed the heading target.

## Explicit velocity floor

`roomberry_wheel_speed.wheel_speeds` normalizes each nonzero wheel target to at
least42mm/s, preserving signs and stationary wheels. Zero remains zero. Input
must be finite and within500mm/s. This applies to explicit velocity operations
through RobotCommandArbiter, normal ramps and discrete speed steps. PWM and
firmware-owned clean/dock routines do not express a wheel velocity in mm/s and
are outside this normalization. The floor is a command policy, not a claim
that measured physical velocity exactly matches the requested value.

Low curved targets may become straighter when both wheels hit the floor;
waypoint footprint checking uses the normalized values. Discovery at minimum
proximity speed aligns first, then advances straight, rather than pretending
it can turn by slowing one wheel below the minimum. Pad turn targets use42mm/s.
The shared ramp keeps its internal acceleration state, but every serial velocity
write is either zero or at least42mm/s in magnitude. Deceleration ends with a
zero command instead of sending ineffective subminimum intermediate commands.

## Tag15 homing pulses

- Final straight approach:42mm/s,100ms nominal pulse, then a physical stop and
  fresh encoder settling before another pulse. Long return transit stays50mm/s.
- Homing/search/aim pivots:42mm/s per wheel in opposite directions,100ms maximum
  pulse, followed by existing measured pivot settling.
- The I/O thread owns the brake deadline; it does not rely on the200ms mission
  tick noticing that100ms elapsed. Ramping is bypassed for these pulses.
- Deadline is checked before queued operations and after sensor polling, and
  bounds the command-queue wait. It is not a hard real-time hardware timer:
  an in-progress serial operation or scheduling delay can postpone the brake.
- Stops, safety brakes and controller cancellation clear the pending deadline.
  Pulse duration must be20–250ms, with a nonzero velocity target and no speed
  steps. Normal motion leases remain active and independent.
- Straight settling requires fresh advancing sample timestamps, speed<=5mm/s
  and yaw rate<=2deg/s over at least150ms;1.5s without quiet aborts. Three
  completed pulses without1mm encoder progress abort instead of masking stall.
- Heading continuation uses2degrees only during the same active direction.
  After a pulse or before reversal, return/approach corrections must exceed
 5degrees again. Search/aim retain their2degree scan-facing requirement.

The300mm tag15validation gate, tag confirmation, bump/cliff/wheel-drop checks,
bounded travel, scan guard and phone diagnostics remain in force. This trial
does not automatically move closer after a rejected final tag fix.

`control_version` is3.2.pulse.1; status JSON includes minimum_wheel_speed_mm_s
and pulse_active. Tag-return decision logs include pulse_seconds. No phone
rebuild is required. Sync the new wheel-speed module plus roomberry_control.py,
roomberry_mission.py,roomberry_manual_step.py,roomberry_tag_return.py and
roomberry.py, then restart Roomberry on Pi3. Test short left/right corrections
and the final approach; confirm both delivered speeds and gyro-measured motion.

## Speech transcript logging

Every Pi-originated announcement logs its exact text in roomberry.log:

```text
Speech transcript code=STATUS phase=queued id=... text="..."
Speech transcript code=STATUS phase=attempt id=... text="..."
Speech delivery code=STATUS status=completed detail=... (id=...)
```

The shared speech ID joins the phrase to acceptance/completion/failure or
queue-drop records. Text is JSON-quoted so embedded line breaks are escaped.
An attempt is recorded once per speech job, not once per transport retry.
Idle battery reminders bypass the queue but still log their exact attempted
text. Catalogue messages, dynamic scans and web-entered announcements share
this path. Job snapshots retain the text through state transitions. A queued
or attempted phrase is not proof that it was heard; completion is the phone's
reported outcome. Transcript records explicitly disable speech announcements
to avoid a logging/speech feedback loop. Sync roomberry_speech.py as well.
