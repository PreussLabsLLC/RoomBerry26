<!-- @(#)report.md 3.1.wall.13 2026/11/09 09:40:30 -->
# Short run stopped after 90-degree left bypass in front of dishwasher

Sources: uploaded application log `roomberry/logs/roomberry.log` and sensor CSV
`roomberry-sensors-20261109-092328.csv`. `events-and-samples.csv` preserves the
WALL telemetry for the 09:23:39-09:25:39 mission. Operator reports the robot
was in front of the dishwasher close to the fridge. The run is on control
build 3.1.wall.12.

## Why the mission stopped

At 09:25:39.117 the exact reason was:

`wall rejoin reached 90 degree bound without target signal`, travelled
2518.42mm, stage aborted.

Clock 09:23:39, tag16 anchor 09:23:57, follow entered 09:24:29 at heading
66.83deg after one alignment retry. One ordinary right contact at 09:24:35
was followed by a 15deg left correction and a quick rejoin with signal 33.
Three wall-loss searches then behaved differently:

- 09:25:09 wall-loss search 1: right 14.5deg, rejoined at signal 90.
- 09:25:13 wall-loss search 2: right 15.2deg, rejoined at signal 72.75.
- 09:25:17 wall-loss search 3: contact during the right-search advance,
  `contact_preempted_drive` 09:25:19.466, `left_obstacle_bypass_started`
  heading 37.74deg, `next_left_deg=90`. Reverse 36.56mm, contact-left to
  126.12deg, bypass rejoin `detour=true, max_right_deg=90`.

Bypass corner search advanced four 50mm steps with 15deg right pivots:
heading 130.28 to 39.27deg (~91deg right), encoder distance 2023 to 2266mm
(~243mm), averaged IR 0.5-7.0 (samples 09:25:26-09:25:39). It passed through
the previous follow headings 72deg and 56deg without ever reacquiring 30.
No terminal contact, hard hazard, watchdog expiry or contact-limit abort
(2/42) caused the stop.

## Behavior notes

- The two high-signal wall-loss rejoins (90, 72) show the recessed
  dishwasher front is visible to the right IR from the headings the robot
  used before contact. The bypass then turned the robot 88deg left in one
  step, facing it away from that recessed front. The subsequent 90deg right
  sweep advanced ~243mm while turning, but never saw enough IR from the new
  position/orientation. This repeats the 22:37:29.972 pattern on 223448
  (44.85 to 135.74deg, IR 0.0-2.5 over ~246mm).
- Operator hypothesis matches the telemetry: the robot was close to the
  fridge/dishwasher junction, where a single large left turn overshoots the
  small gap. A smaller left attempt first keeps the robot nearer the
  recessed front so the following right search can still see it, and only
  escalates if contact repeats.
- Map session `roomberry-maps-20261109-092328-508551` recorded seven PNGs
  through 09:25:39. Map/coverage handling is on wall.12 (clear on start,
  dead-reckoning trail). No map topology is extracted here.

## Requested next trial

Operator requests trying a smaller left turn first for the obstacle bypass
in front of the dishwasher. Analysis only for this run; wall.13 changes the
first bypass left step to 20deg and escalates to 90deg only if contact
repeats while the bypass is active.
