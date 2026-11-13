<!-- @(#)report.md 3.1.wall.16 2026/11/09 10:40:00 -->
# Almost past the fridge, stopped on search limit at 3.58m

Sources: uploaded application log `roomberry/logs/roomberry.log` and sensor CSV
`roomberry-sensors-20261109-101115.csv`. `events-and-samples.csv` preserves the
WALL telemetry for the 10:11:26-10:14:16 mission. Operator reports the robot
made it almost past the fridge. Tag 15 was moved to the same y as tag 16 so
it will be in view when following the wall. The run is on control build
3.1.wall.15.

## Why the mission stopped

At 10:14:16.069 the exact reason was:

`wall-loss search limit reached`, travelled 3575.19mm, stage aborted.

Clock 10:11:26, tag16 10:11:44, follow 10:12:20 at 75.04deg. Follow ran
340 samples, rejoin 147, contact_left 62. Four wall-loss searches ran
(10:12:55, 10:12:59, 10:13:02, 10:13:07). At 10:13:10 contact in rejoin
started the go-around: `left_obstacle_bypass_started` heading 41.24deg,
`next_left_deg=20`. First bypass: left 39.92 to 58.41deg, right sweep
63.11 to 23.41deg, rejoined at 27.0. Immediate contact in follow
escalated to 90deg left (22.64 to 113.54deg), rejoined at 28.75
(72.30deg). A second both-bumpers contact (10:13:39, retry 3, 90deg)
left to 176.33deg, rejoined at 61.0 (121.09deg). Fluctuation holds fired
8 times (spreads 26-86). At 10:14:16 `wall_ir_lost` signal 6.25 would
have started a fifth wall-loss search and hit the 4-search limit.

Encoder distance reached 2356.92mm by the last follow heading 121.09deg.
That is ~1.24m past the previous 100017 run's 2317mm stop, consistent
with almost past the fridge. No hard hazard, watchdog expiry or
contact-limit (3/42) abort caused the stop.

## Behavior notes

- Wall.15 corner go-around fired as designed (contact in `wall_loss`
  rejoin → 20deg first). The two follow contacts while `detour_active`
  correctly escalated to 90deg. Headings after bypass (23, 72, 121deg)
  show the robot is now sweeping around the fridge front rather than
  facing the dishwasher head-on as in 100017.
- Wall-loss budget, not travel/time, is now the binding limit for a
  longer run. Trial distance was 3575/6000mm and elapsed ~170s of
  the current 240s whole-run bound, so another 1.5m fits within the
  existing 6m/240s envelope for distance but needs more wall-loss
  searches and a higher target.

## Requested next trial

Operator requests continuing another 1.5m (≈ from ~3.5m to ~5.0m
travelled) and then stopping for a tag-15 scan. Tag 15 is now at the
same y as tag 16 so it should be visible while following. Analysis
only for this run; wall.16 will raise the wall-loss budget, set a
total-travel trigger at 5000mm to enter a stopped tag-15 scan stage,
and allow `scan_pause` for tag 15 in that stage before finishing
complete.
