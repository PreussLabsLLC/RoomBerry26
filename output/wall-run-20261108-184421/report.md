<!-- @(#)report.md 3.1.wall.4 2026/11/08 19:00:00 -->
# First WALL drive: IR threshold reached, alignment lost the signal

Sources: uploaded roomberry/logs/roomberry.log and sensor CSV
roomberry-sensors-20261108-184421.csv (395 rows,18:44:21.844–18:45:22.266).
Times are the logged clock. events-and-samples.csv extracts WALL events and
samples. Analysis only; no control changes, deployment or robot commands.

## Sequence

| Time | Result |
| --- | --- |
| 18:44:31.607 | Clock starts WALL; waits for tag16. |
| 18:44:48.533 | Tag16 anchor qualified; begins departure. |
| 18:44:54.130 | Left turn reaches88.05 encoder degrees; forward stage begins. |
| 18:45:00.180 | Forward stage advances199.64 encoder mm; starts right turn. |
| 18:45:03.402 | Right turn ends after47.69 encoder degrees; acquisition begins. |
| 18:45:04.608 | Right light-bumper readings32,33,39 qualify target30. |
| 18:45:04.634 | Begins fixed left45deg alignment, with no reverse. |
| 18:45:07.841 | Alignment ends after44.08 encoder degrees, but IR is now0. |
| 18:45:08.040 | Follow sees1, below usable threshold7.5; stays stopped. |
| 18:45:08.238 | Unrenewed0.6s motion lease expires while already stationary. |
| 18:45:08.245 | Guard reports generic unsafe/stale/unavailable sensor abort. |

Acquisition forward travel was30.96 encoder mm from its stage boundary. Overall
accumulated absolute encoder travel at abort was289.15mm; net session distance
was242.49mm. These include measured translational effects during pivots and
must not be interpreted as surveyed floor-path accuracy. Powered departure
lasted about19.7seconds after a roughly17second anchor wait.

## Why it stopped

Operator follow-up: the robot was still more than200mm from the intended
board. Reaching30 units therefore qualified an IR candidate; it did not
establish arrival at that board. Alignment then failed: signal35–40 early
in the left turn dropped through20,14,12,9,6,3 to0 as the turn continued.
A fixed45degree pivot therefore did not leave the right sensor tracking a wall.
The readings establish loss of usable wall visibility; they do not distinguish
sensor angle, actual gap, wall geometry, or wheel/pose error as the sole cause.

No WALL drive commands were issued in follow stage. It never began regulated
forward wall following. This was not a trial distance/time-limit stop, bumper
collision, cliff event or dropped sensor stream. Near the abort, CSV reports
ready=1, hard_hazard=0, safety_latched=0, bumpers=0 and continuing fresh polls;
applied wheel speeds were already zero by18:45:07.891.

There is a separate software bookkeeping defect: the last moving command renewed
the lease at18:45:07.64. The alignment transition stopped the wheels but did
not end that lease. The follow stage correctly stopped on low signal and did
not renew a moving lease. After0.6seconds the arbiter latched lease expiry;
WALL guard then aborted before its intended1.5second wall-loss wait finished.
The generic sensor error masks this cause. The log calls the shared watchdog
"GridRunner" even though the active mission was WALL.

## Next changes indicated

- Replace unconditional completion of the45degree alignment with bounded,
  sensor-qualified wall alignment/reacquisition. Capture signal against yaw
  and require useful fresh readings before entering forward follow. A peak
  alone is not proof of being parallel to the wall or having a safe gap.
- End the motion lease on deliberate stopped transitions/wall-loss waits;
  begin a new lease only when the coordinator deliberately resumes safe motion.
  Keep the independent deadman effective for all actual movement.
- Report wall loss and lease expiry separately rather than calling either
  an unspecified sensor failure. Add a replay of this signal/yaw sequence to
  tests: the prior idealized simulation did not represent this physical loss
  of signal while aligning.

The30-unit target was reached; this run does not test whether it can be held
while driving parallel. There is no evidence here that changing target alone
would fix the alignment problem.
