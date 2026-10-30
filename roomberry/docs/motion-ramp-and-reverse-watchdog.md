<!-- @(#)motion-ramp-and-reverse-watchdog.md 2.3.10 2026/10/28 17:00:00 -->
# Wheel-speed ramp and reverse current reporting

## Implemented wheel-speed shaping

`autonomy.json` enables `motion_ramp`, with acceleration **100 mm/s²** and deceleration **200 mm/s²**. At 50 mm/s, acceleration takes approximately 0.5 s and an ordinary stop approximately 0.25 s. Ideal additional stopping distance is 6.25 mm, excluding I/O and mechanical delay. At 500 mm/s the same deceleration would require 2.5 s and 625 mm; higher speeds need braking anticipation and calibrated rates.

The I/O worker advances wheel targets without sleeping inside a command. Scheduling waits are capped at 50 ms, though serial I/O can lengthen actual steps. A delayed step caps elapsed ramp time at 100 ms to avoid a large catch-up jump. Left/right velocities advance proportionally, sign reversals stop both wheels first, and repeating a target does not restart acceleration.

Velocity-based `drive`, `drive_direct`, straight and spin commands use the ramp, including web driving. Radius commands are converted to paired wheel velocities. Wheel PWM and native cleaning/docking are separate controllers and are not velocity-ramped; they cancel pending ramps before taking control.

Normal mission stops use `soft_stop` at waypoints, scan setup and completed maneuver stages. Completion means zero velocity has been sent, so stationary detection does not begin during deceleration. Web zero-velocity commands also wait for deceleration. `stop` and `emergency_stop` remain immediate. Safety events, stale/bad sensor packets, mode changes, shutdown and watchdog expiry cancel pending targets. Clearing a hazard never revives a cancelled ramp.

Applied wheel steps and requested targets are logged separately. The analysis tool prefers applied-step records when available. Use `motion_ramp.enabled: false` for a deliberate comparison; rates must be finite and positive. The feature is locally tested, not physically verified for reduced slip or pitching.

## Enabled reverse observer: report only

`reverse_current_monitor.mode` is strictly **report_only**. Other modes are rejected at configuration time. It observes validated packets and the last applied wheel commands whenever both wheels are moving backward. It does not act during forward motion, unknown PWM/native control, or in-place turns.

| Candidate | Rule |
| --- | --- |
| Sustained wheel current | Either wheel exceeds `max(0.40 A, baseline + 0.20 A)` for at least 0.25 s and three valid samples |
| High current / overcurrent | Either wheel reaches 0.65 A or its overcurrent flag asserts, including during startup |
| No encoder progress | Less than 2 mm accumulated encoder travel over a one-second stable reverse interval |

A slowly learned per-wheel baseline is capped at 0.25 A. Learning freezes during changing speeds, high/rising load and lack of progress. The sustained test waits until applied speeds have been stable for 0.15 s. A gap over 0.5 s resets persistence instead of treating missing samples as evidence. New candidate reasons are reported once per reverse episode; total event count and the most recent report remain available afterward.

**A candidate changes no motion, ramp target, beep, mission or safety state.** Existing cliff, bumper, wheel-drop and stale-sensor handling remains separate. There is no reverse-current latch or automatic forward escape in this implementation.

Reports are available in:

- Logs: `[REPORT ONLY] Reverse load candidate: ...; motion unchanged.`
- `http://pi:8080/status.json`, under `reverse_current_monitor`.
- New sensor CSV columns: `reverse_monitor_mode`, `reverse_current_candidate`, `reverse_current_reasons`, `reverse_current_events`, wheel thresholds, and applied wheel speeds. Button source and masks are also recorded.

The earlier run had 1,014 inferred steady reverse samples, with larger absolute wheel-current median 0.144 A, 99th percentile 0.374 A, and maximum 0.584 A. Rear contacts were not labeled. These thresholds are experimental; reporting-only data after ramping must be reviewed before enabling any current-based intervention.

Current monitoring detects resistance after contact. It cannot reliably detect an obstacle before contact, a soft object, or wheel slip. A rear bumper/distance sensor remains the stronger hardware improvement. Active current-based braking, a manual-reverse distance/time cap, and latched operator recovery remain future proposals, not enabled features.

## OI STOP, restart and buttons

Wheel-drop handling sends OI STOP and then suspends queries, wake attempts and actuator commands. The [iRobot OI specification](https://cdn-shop.adafruit.com/datasheets/create_2_Open_Interface_Spec.pdf) defines opcode 173 as disabling the interface until Start. Continuing to query afterward was the source of the previous timeout/wake loop.

Only an explicit `restart_oi` command reopens the interface. It leaves the robot in Passive, resets sensor startup, and invalidates localization from before carrying. It does not resume the previous mission. Safe mode can be selected deliberately after fresh grounded readings; autonomous global navigation requires a newly accepted tag.

Packet 18 is queried independently for button state, and short Schedule/Clock presses are latched. `/status.json` exposes group and dedicated masks plus held-state duration. A firmware-held mask may still need hardware investigation; there are no manufactured button edges or forced mode cycling to pretend a press occurred.
