<!-- @(#)report.md 3.1.wall.15 2026/11/09 10:30:00 -->
# Band helped, but corner bump never triggered go-around

Sources: uploaded application log `roomberry/logs/roomberry.log` and sensor CSV
`roomberry-sensors-20261109-100017.csv`. `events-and-samples.csv` preserves the
WALL telemetry for the 10:00:26-10:02:19 mission. Operator reports the robot
stopped facing the dishwasher after hitting the cabinet corner with the
right bumper, and that go-around navigation needs improvement. The run is
on control build 3.1.wall.14.

## Why the mission stopped

At 10:02:19.996 the exact reason was:

`wall-loss search limit reached`, travelled 2316.99mm, stage aborted.

Clock 10:00:26, tag16 10:00:45, follow 10:01:14 at 80.94deg. Four
wall-loss searches then ran in ~30s, all with detour=false:

- 10:01:49 #1: right 14.44deg, rejoined at signal 66.5 (82.80deg).
- 10:01:54 #2: right 10.28deg, rejoined at signal 73.25 (72.19deg).
- 10:01:59 #3: right 14.99deg, rejoined at signal 24.75 (47.47deg).
- 10:02:03-10:02:12: two right-bumper contacts in follow (retries 1,2,
  `next_left_deg=15`), each: reverse ~35-40mm, left ~15deg, right rejoin
  to ~52/49deg.
- 10:02:09 #4: right 14.99deg, rejoined at signal 31.5 (38.07deg).
- 10:02:17-10:02:19: fluctuation hold (spread 22), then `wall_ir_lost`
  signal 7.0, finish search-limit. Final heading 41.6deg at distance
  ~2009mm, i.e. facing the dishwasher front.

Fluctuation holds fired 5 times (spreads 22,22,91,37,22). Follow sampled
233, rejoin only 60, so the 20-30 band did help forward progress versus
094542, but the cabinet-corner contacts were still treated as ordinary
side-wall bumps.

## Behavior notes

- The go-around (left-obstacle bypass, first 20deg in wall.13) never
  triggered. It requires `detour_active` or contact while already in a
  `wall_loss` rejoin. Both corner contacts were in `follow` (stage follow,
  `detour=false`), so `contact_recovery` chose `next_left_deg=15` and a
  normal 30deg/10s contact rejoin. That re-acquired the same corner
  ~22mm later and bumped again.
- Each wall-loss right sweep turned ~10-15deg right and found a high IR
  (66, 73, 24, 31) — the dishwasher front — then follow dropped to <7.5
  within ~2s. The searches consumed the 4-search budget facing the front
  instead of sliding/go-round toward the fridge side.
- No bypass/trial limit, hard hazard or contact-limit abort caused the
  stop. The stop is the wall-loss budget expiring head-on to the
  dishwasher after corner contact.

## Requested next trial

Operator requests improved go-around navigation after hitting the cabinet
corner with the right bumper. Analysis only for this run; wall.15 will
treat follow-stage corner contacts that occur soon after a wall-loss
rejoin as the start of the bounded go-around (20deg first, 90deg on
repeat), so the corner case enters bypass instead of burning wall-loss
searches head-on.
