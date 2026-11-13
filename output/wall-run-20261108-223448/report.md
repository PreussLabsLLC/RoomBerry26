<!-- @(#)report.md 3.1.wall.11 2026/11/08 22:45:40 -->
# Longer run reached the fridge bypass but lost the corner wall

Sources: uploaded application log `roomberry/logs/roomberry.log` and sensor CSV
`roomberry-sensors-20261108-223448.csv`. events-and-samples.csv preserves the
WALL telemetry. Operator reports the robot passed the dishwasher in front of
the fridge; the dishwasher front is somewhat recessed from the cabinets, and
the map currently lacks a trail. The run is on control build 3.1.wall.11.

## Why the mission stopped

At 22:37:29.972 the exact reason was:

`wall rejoin reached 90 degree bound without target signal`, travelled
3081.24mm, stage aborted.

Clock 22:34:56, tag16 22:35:13, follow 22:35:46. Six ordinary right contacts
retried 1-6, three wall-loss rejoins at signals 108-147, then contact retry 7
at 22:37:10.845 (`left_obstacle_bypass_started` heading 44.19deg,
`next_left_deg=90`). Reverse 30.95mm, left 44.85→135.74deg, bypass rejoin
`detour=true, max_right_deg=90`.

Bypass corner search advanced four 50mm steps with 15deg right pivots:
heading 137.38→47.03deg (~90deg right), encoder distance 2065→2311mm (~246mm),
averaged IR 0.0-2.5 throughout. No terminal contact, hard hazard, watchdog
expiry or contact-limit abort (7/42) caused the stop.

## Behavior notes

- Wall.11 averaging and the 42-contact budget worked: the run travelled
  3.08m with seven recoveries versus 0.88m/four on 221411. Wall-loss
  re-joins turned 9-11deg right to reacquire at high signal.
- The recessed dishwasher front is plausibly why IR dropped at ~1.9-2.1m
  while the robot still had cabinets/dishwasher on its right. Localizer
  dead-reckoning shows pose heading rotating 66→44deg during the final
  search, consistent with a right sweep across a recessed/cornered front.
- Map trail has only 11 points in the latest session (`trail=252,
  trail_session_start=241`) while wheel travel was 3.08m. After leaving
  tag16, `localized=False` stopped `mapper.update_pose` from recording.
  This is a recording gap, not evidence the odometry failed.

## Requested next trial

Operator requests a right turn on IR loss to seek the recessed
front line/wall/obstacle, and a visible map trail during the run. Analysis
only for this run; wall.12 implements a deeper 60deg/10deg right sweep for
wall loss and records the dead-reckoning trail.
