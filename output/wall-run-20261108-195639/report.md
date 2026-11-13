<!-- @(#)report.md 3.1.wall.9 2026/11/08 19:00:00 -->
# Rejoin reached its distance limit without turning enough

Sources: uploaded application log and sensor CSV
roomberry-sensors-20261108-195639.csv. Operator reports improved corrections
but an early stop. events-and-samples.csv preserves the WALL telemetry.

## Earlier fixes worked

- Initial alignment required two failed probes before qualifying19:57:39.422.
- Right bumper19:57:42.996: immediate owner stop, retreat31.18 encoder mm,
  small left correction14.66deg. Rejoin qualified signal32 while stationary.
- Another right bumper19:57:54.558 interrupted a drive submission. The new
  `contact_preempted_drive` event appeared54.568, followed by normal contact
  recovery54.583 rather than mission error. Retreat30.06mm, left14.11deg.
- No90degree escalation or active obstacle bypass occurred. The small-correction
  policy and contact-arrival race handling behaved as intended.

## Why the mission stopped

At19:58:00.586 the exact reason was:
`wall rejoin reached 100 mm/15 degree bound without target signal`.

It reached the distance bound, not the angle bound:

| Quantity | At rejoin entry19:57:57.361 | Final mission sample19:58:00.583 |
| --- | ---: | ---: |
| Encoder distance, mm | 744.738 | 845.006 |
| Encoder yaw, degrees | 107.633 | 107.086 |
| Right signal | first sample23 | 17 |

Net advance100.27mm, net right turn0.55deg, elapsed3.22seconds. The target is30;
all final rejoin readings stayed17–24. No terminal contact, hard hazard,
watchdog expiry or software exception caused this termination. Zero applied
wheel speeds are first recorded19:58:00.759, after the commanded stop.

Post-turn settling initially increased yaw to110.15deg (another2.52deg left),
then the right arc recovered only3.06deg from that peak. The last successful
follow heading was92.21deg, so the final heading remained about14.88deg left
of it. The distance-limited fixed wheel split never restored even that heading.

The software sent right15/left25mm/s; applied-command fields agree. Firmware
requested-speed fields report right14/left28 for most of the arc. These are
command reports, not independent measured wheel velocities. The logs establish
weak realized steering at these commands; they do not by themselves identify
firmware speed-floor behavior, motor friction or wheel slip as the sole cause.

## Recommended next change

Make recovery heading-controlled. Use bounded measured right-turn steps to
restore the last successful follow direction (monitoring fresh IR and all
contact guards), then use a short inward approach if needed to regain30 units.
Record commanded versus measured yaw and separate turn/advance limits. Preserve
bounded travel/time, bumper/stall and hard-hazard handling. Increasing the100mm
limit alone would allow more forward travel at an ineffective heading.

This is a rejoin-control limitation, not evidence that the target30 is too high
or that the safety limits should be removed. No runtime changes, deployment or
robot commands were made during this analysis.
