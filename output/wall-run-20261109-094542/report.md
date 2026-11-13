<!-- @(#)report.md 3.1.wall.14 2026/11/09 09:55:00 -->
# Follow loop never reached the fridge, chasing the 30 IR value

Sources: uploaded application log `roomberry/logs/roomberry.log` and sensor CSV
`roomberry-sensors-20261109-094542.csv`. `events-and-samples.csv` preserves the
WALL telemetry for the 09:45:51-09:49:51 mission. Operator reports the robot
did not reach the fridge this time and spent too much trial-and-error trying
to catch 30 IR units. The run is on control build 3.1.wall.13.

## Why the mission stopped

At 09:49:51.824 the exact reason was:

`time limit during rejoin`, travelled 3892.60mm, stage aborted.

Clock 09:45:51, tag16 anchor 09:46:09, follow entered ~09:47. 27 contact
recoveries, but only one `wall_rejoined` (09:49:38.897, signal 32.25, right
11.81deg, moved 9.42mm). That single success was after ~24 contact cycles
in the same place. No wall-loss final sweep; the rejoin stage timed out.

Stage totals from events-and-samples.csv (1074 WALL samples): follow 92,
rejoin 497, release 185, contact_left 164. The robot spent ~77% of sampled
time in rejoin/release/contact_left trying to reacquire 30, and only ~9% in
follow. Encoder distance stayed ~1350-1505mm for most of 09:47-09:49 while
total wheel travel climbed to 3892mm, i.e. back-and-forth retreat/left/right
loops at the same spot, not forward progress toward the fridge.

## Behavior notes

- **Too-high single threshold.** Follow averaged IR 13.5-53.2
  (mean 33.5), histogram 10s:20, 20s:13, 30s:29, 40s:12, 50s:18 — large
  fluctuation, max successive jump 15.5 on the 4-frame average. Rejoin
  (post-contact) signals averaged 19.1, min 11.5 max 32.2 over 497 samples:
  only 5 samples (1%) ever reached >=30, but 163 samples (33%) were
  >=20. The loop was: retreat ~32-36mm, left 15deg, right-search 5deg/30mm
  steps, hit the wall again before reaching 30, repeat. A lower
  acceptance (20) would have qualified about a third of those samples.
- **Steering hunts the single value.** Follow PD is `(signal-30)/30*0.3 +
  slope/30*0.35`, clipped +-0.35, with no deadband. Inside the operator's
  proposed 20-30 band the robot still steers ±, and the derivative term
  amplifies the 10-50 swings into repeated contact instead of driving
  straight.
- 27 contacts is far under the 42 budget, so the budget did not stop it;
  the 180s follow / stage deadlines did. No hard hazard, watchdog expiry
  or bypass detour was active (`detour=false` throughout the loop, all
  contacts had `next_left_deg=15`).

## Requested next trial

Operator requests a target **range 20-30** instead of a single 30, and to
**stop for a second if values fluctuate too much** rather than chase them.
Analysis only for this run; wall.14 adopts a 20-30 deadband (centre 25)
for acquire/rejoin/follow and a 1s stopped resample hold when the 4-frame
spread exceeds 20.
