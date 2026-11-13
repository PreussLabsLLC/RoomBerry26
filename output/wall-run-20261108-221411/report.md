<!-- @(#)report.md 3.1.wall.10 2026/11/08 22:25:25 -->
# Contact-recovery budget stopped a longer wall follow

Sources: uploaded application log `roomberry/logs/roomberry.log` and sensor CSV
`roomberry-sensors-20261108-221411.csv` (756 rows). events-and-samples.csv
preserves the WALL telemetry. Operator reports the map looked okay, the IR
signal seems unsteady, and bumps are acceptable as definite wall locations
once position is known. The run is on control build 3.1.wall.10.

## Why the mission stopped

At 22:15:32.086 the exact reason was:

`contact recovery limit reached`, travelled 883.14mm, stage aborted.

Clock start 22:14:20; tag16 anchor 22:14:36. Departure completed, acquire
candidates 37 and 66, two alignment losses (signals 7 and 15) using 2 of 4
reapproaches, then five right-bumper contacts. The four-event contact budget
allowed four recoveries; the fifth contact at 22:15:32.029 latched after
`contact_retries=4`, so no further release was entered. No hard hazard,
cliff, wheel drop, watchdog or exception caused the stop.

| Contact | Time | Stage | Recovery |
| --- | --- | --- | --- |
| 1 | 22:15:07.769 | acquire | retry 1, reverse 30.51mm, left 15deg, measured rejoin 30mm/8.1deg, signal 35, follow |
| 2 | 22:15:14.205 | follow | retry 2, reverse 30.06mm, left 15deg, measured rejoin, follow |
| 3 | 22:15:20.624 | rejoin | retry 3 during rejoin advance, reverse 36.12mm, immediate rejoin signal 30, follow |
| 4 | 22:15:26.703 | follow | retry 4 after contact_preempted_drive, reverse 31.40mm, left 15deg, immediate rejoin signal 38, follow |
| 5 | 22:15:32.029 | follow | latched at retries 4/4, finish aborted contact recovery limit reached |

The wall.10 measured rejoin behaved as intended in all four recoveries:
30mm/s minimum-wheel floor, 3-frame settle before turning, 5deg/30mm
turn/advance steps, 3-frame stopped confirmation. The contact race path
`contact_preempted_drive` at 22:15:26.693 recovered without abort.

## Behavior notes

- Follow IR rose through the target during each follow leg (for example
  37, 43, 48, 54, 58, 65, 66) before the next right contact. The
  proportional/derivative steering on the single-frame signal is sensitive
  to that unsteadiness and to derivative spikes.
- Alignment consumed retries but did not stop the run. The terminal stop
  is the separate contact budget, not acquisition.
- No obstacle bypass was active and no wall-loss search was used; all
  contacts used the ordinary 15deg left correction. The upcoming-fridge
  left path remains untested.

## Requested next trial

Operator requests a longer run to approach the fridge and evaluate moving
left around it, with bumps retained as usable wall fixes, a four-frame
average for the unsteady IR signal, and a raised contact-recovery limit.
Analysis only for this run; the wall.11 change implements the average and
the raised budget.
