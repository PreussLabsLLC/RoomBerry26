# November 4, 18:13–18:19 — outbound regression and unavailable return

Analysis only. No control changes or robot commands. Sources: roomberry/logs/roomberry.log,
roomberry/logs/sensors/roomberry-sensors-20261104-181351.csv and matching NavLink binary.

## Clear software regression

There were 362 GridRunner driving samples: 195 differential cruise samples,
167 equal-wheel slow samples, and ZERO pivot samples. All were outbound;
there was no actual driven return stage and no threshold event.

The new pivot-entry threshold is 5 degrees. When a usable line observation is
present, its physical_error is derived from direction*correction/4, after the
correction has been capped at ±0.25. Its maximum magnitude is therefore
0.0625 rad = 3.58 degrees, so line-based errors cannot trigger that pivot.

In addition, each usable outbound observation assigns hold_heading to the
current wheel heading, including isolated observations while still in slow
reacquisition. The controller needs three distinct good observations to return
to cruise, but one intermittent observation can still reset its heading anchor.
This permits the held heading to follow a developing drift. These two choices
interact: usable observations cannot trigger a pivot, while lost observations
measure against a repeatedly moved anchor. This is a regression introduced by
the pivot change, not evidence that the pivot motors failed to respond.

First attempt: 18:14:08.701 onward. Initial tracking error was +2.13 mm, confidence
0.994. Tracking was good for about 2.124 m. At 18:14:46.199 it entered slow mode.
Subsequent readings were intermittent, often confidence 0.46–0.54. Both applied
wheel commands were −30 mm/s, while wheel heading progressed from about −4 to
−20 degrees. The last sample was 18:14:59.447, distance −2642.473 mm, heading
−19.69 degrees; the mission aborted at 18:14:59.646 on the 20-degree envelope.
Sensors later settled near −2655.9 mm and −20.56 degrees.

At the last driving sample the computed heading error was only +1.53 degrees,
despite wheel heading −19.69 degrees: a concrete example of the moving anchor.
The logs confirm actual drift with equal requested wheel speeds, but do not
uniquely establish its mechanical/firmware cause. The software failed to correct
that drift because no pivot was selected.

Later outbound attempts armed at 18:15:53.909 and 18:16:45.601. They added about
359 and 469 mm of per-attempt travel respectively before being manually stopped.
They also issued zero pivots. Subsequent starts timed out waiting for usable
line observations. New starts create new experiment origins and replace the
previous GridDrive, so those per-attempt distances are not a surveyed trace
from the original tag alignment.

## Why the return requests did not move

The existing return entry point requires a retained threshold-completed run;
this session never reached threshold. It cannot currently recover an arbitrary
failed outbound from its initial alignment/trace alone. Repeated new starts
also replaced the previous run. Specific requests:

- 18:18:24.997: rejected because the mission was still in GridRunner waiting,
  rather than idle ("requires idle, ready sensors and no safety stop").
- 18:18:38.543: Restart OI succeeded. It intentionally clears the retained run
  and changes the odometry epoch, then requires new sensor qualification.
- 18:18:49.608: return rejected because a stationary Pi scan was still active.
- 18:19:07.408: return rejected because no retained grout run remained.

These requests did not begin tag-homing and subsequently wander; they were
rejected before a return drive. No return checkpoint poses were processed.

## Pad and startup observations

The pad compensation materially improved endpoint increments:

| Step | Count | Mean magnitude | Range |
| --- | ---: | ---: | ---: |
| Left 5 degrees | 15 | 4.966 degrees | 3.281–6.016 degrees |
| Right 5 degrees | 1 | 4.157 degrees | single sample |
| Forward 50 mm | 2 | 52.939 mm | 50.247–55.631 mm |
| Backward 50 mm | 8 | 49.294 mm | 43.742–55.855 mm |

One pad request during a transition was rejected for sensors/safety readiness.
The full sanitized startup log worked. It includes bl-start, STR730, bootloader
IDs/revisions, a 2007-05-14 bootloader date and 2012-03-22 application build date,
"Roomba by iRobot!", battery-current-zero 256 and languages: english (0).
There is no r3_robot/tags/release string matching the existing release parser.

## Conclusion

There are definite software causes to correct: derive pivot decisions from an
uncapped heading-error quantity; preserve the lost-line heading anchor until
stable reacquisition; provide a deliberate, valid return/recovery entry from an
interrupted outbound, without treating a fresh mid-floor start as tag alignment.
Tests must include intermittent near-threshold-confidence observations and the
specific capped-error/5-degree combination that was missed.

A later pit-stop remains useful to measure equal-speed wheel/yaw response, but
this run does not test the new pivot response at all. It is not necessary to
invoke a new physical fault to explain why the correction mechanism failed.
