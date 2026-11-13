<!-- @(#)report.md 3.1.wall.7 2026/11/08 19:00:00 -->
# WALL following: normal signal-loss stop

Sources: uploaded application log and sensor CSV
roomberry-sensors-20261108-192245.csv. Operator reports roughly20mm physical
stand-off during following. That observation is distinct from raw sensor units.

At19:24:13.407 the mission aborted with:
`wall IR lost; stopped without blind cabinet seeking`.

The following loop uses max(5,30*0.25)=7.5 raw units as its minimum usable wall
signal. Final readings were roughly27–30, then16,12,8,7. The7-unit reading at
19:24:11.796 triggered an immediate commanded stop. The first CSV row showing
both applied wheel speeds zero is19:24:11.851. After stopping, the readings
stayed2–5 rather than recovering. The1.5second stationary wall-loss wait then
expired and ended the mission. Fresh polls continued; no terminal bumper,
cliff/wheel-drop, current-stall or watchdog-expiry event explains this stop.

Earlier events demonstrate improved behavior:

- Initial stepped alignment qualified at19:23:36.875 with readings34/42/36.
- First follow advanced618.45 encoder mm before a right bumper at19:23:51.232.
  The contact latch stopped the wheels and the mission retreated32.97mm.
- Left correction14.33deg finished at19:23:54.119. Right signal already exceeded
  target; rejoin confirmed it stationary at19:23:54.723 (signal73,0.22mm encoder
  drift) and resumed following without extra approach or45degree realignment.
- Second follow advanced741.82 encoder mm over about17seconds of actual
  following, then the final signal-loss stop. Combined forward follow-stage
  encoder distance is approximately1.36m. These are wheel distances, not surveyed
  body-path measurements or perpendicular clearances.

The controller was steering right before the final loss (right/left wheel
commands22/47mm/s at signal16/12/8), but signal fell below its stop threshold
before correction restored it. Data establish loss of usable reflected IR;
they do not distinguish a plank end/gap, a surface change, or increasing physical
stand-off. Physical endpoint geometry needs the operator's observation.

Current code uses the bounded right-arc rejoin only after contact retreat/left
correction. Ordinary follow-stage signal loss still stops and aborts after the
wait. A logical next increment is to attempt that same bounded slow right rejoin
on ordinary signal loss, within its existing100mm/15deg/10s bounds and with
bumper/cliff/stall guards preserved, rather than changing the target or simply
lengthening blind forward motion.

Analysis only; no runtime changes, deployment or robot commands.
