# Pit-stop proposal — 2026-11-04

Design record. Implementation and operating instructions: pit-stop.md.
The first implementation uses only a bounded 20-minute schedule and smoke test;
the exhaustive sweep below is deferred. No physical tests have been run.
Pending return fixes remain in output/grout-run-20261104-1857-review.md:
settled pivot reversal/guard anchoring, all-candidate scan consensus, and
explicit localization instead of repeated-start tag-origin assumptions.

## Architecture

Start with a standalone Pi CLI utility sharing the existing OI driver and sensor
parsers, with exclusive serial access while the Roomberry service is stopped.
Display `pit` using ASCII LEDs. No iOS, camera, localization, or mission planner.
Separate hardware I/O/sensor/watchdog owner from sequence/report work. Require
explicit bench arming each invocation; never persist or automatically resume it.
Later the web UI can launch the same runner under the existing I/O owner if useful.

## Bench behavior

Wheels hanging means wheel-drop/cliff reports are expected. Safe OI mode cannot
support that setup; explicitly armed bench execution requires verified Full mode.
The current Roomberry control owner additionally sends OI STOP on wheel drop,
so a standalone runner avoids weakening production floor safeguards. Record
wheel-drop/cliff/stasis continuously; do not use them as bench-motion inhibits.
Verify the starting suspended sensor pattern and stop on unexpected changes,
bumper contact, charging, mode loss, overcurrent, stale/malformed sensor data,
serial failure, operator stop, or loss of sequence heartbeat. Keep cleaning
motors off. Short stages, zero-speed transitions, stop-and-settle before reversal.
Use a 600 ms motion lease checked by the I/O owner; sequence renews every 100 ms.
This software watchdog cannot guarantee stopping after process death, total
serial loss, or power failure; keep physical power cutoff accessible and robot
stable with wheels clear of the box. On normal/error exit send wheel zero,
verify encoder speed decays, restore Passive, clear pit indication, release port.

Stasis packet 58 describes caster-based forward progress, and is expected false
on the stand and during reverse/turning. Log its raw bits, including validity
where provided. Do not infer actual chassis motion from derived wheel distance
or wheel heading while suspended.

## Sequence

1. Dry-run prints exact stages and estimated duration without opening serial.
2. Armed baseline: 3 s stopped; validate packets/mode/battery and suspended setup.
3. Smoke test +/-20 mm/s on each wheel individually, then both, with zero and
   measured settle between stages. Verify encoder signs and inactive-wheel motion.
4. Default targeted sweep magnitudes 5,10,15,20,25,30,40,50,75,100,150,200,300,
   400,500 mm/s. For each magnitude test left-only +/-, right-only +/-, both
   +/+, -/-, +/- and -/+. These are commanded linear wheel velocities.
   Every stage: stopped baseline, 0.5 s startup, 2 s hold, zero command and
   settle until encoder speed remains low for 0.5 s (bounded 3 s).
   High speeds reached only after lower-speed stages pass. Reverse only after
   settling, never by instantaneous sign swap. Optional down-sweep/repeats.
5. Exhaustive option tests every integer magnitude 1..500 with the same eight
   patterns. About 267 minutes at a 1 s rest plus 3 s powered stage per pattern,
   longer with settling; print actual schedule duration. Full Cartesian pair
   matrix is unnecessary. Optional asymmetric 20/30,30/20,30/50,50/30 and
   45/54,54/45 patterns reproduce recent navigation demands in both directions.
6. Separate transition profile at 20/30/50 mm/s reproduces start, stop, and
   braked reversal timing. A later separately armed direct-PWM profile could
   distinguish motor/PWM behavior from firmware velocity regulation; not default.

## Telemetry and reports

Aim for 20 Hz group-100 polling, measure achieved intervals, fall back to 10 Hz
if needed without overlapping serial queries. Log requested and send-completed
monotonic timestamps, command arguments/bytes, phase, sequence id, OI mode,
raw uint16 encoders with wrap-safe deltas, wheel speed in ticks/s and nominal
mm/s, requested-speed sensor fields, left/right motor currents, overcurrent
bits, battery voltage/current/charge/temperature, charging source/state,
bumper/drop/cliff flags and signals, stasis raw bits and sensor age/errors.
Keep raw packets if practical; missing fields are missing, never synthesized zeros.

Write session manifest with firmware/startup text, wheel conversion parameters,
profile and build; sample CSV; event JSONL; Markdown summary and static plots.
Compare each wheel's mean/error/variability, start delay/deadband, stop delay,
coast ticks, reversal delay, current peaks, inactive-wheel movement, direction
asymmetry and paired-wheel imbalance. Distinguish firmware-reported requested
speed from measured encoder speed. Verify packet semantics on this firmware.
Motor encoders alone cannot prove tire/chassis travel or floor traction.

## Implementation validation

Mock serial tests for exact stages/order/zero transitions, speed bounds,
encoder wrapping/signs, missing packets/unsupported fields, mode loss, watchdog,
stop/interrupt/error cleanup and bench-only permission boundaries. First physical
run should be a short low-speed smoke profile before a full sweep. Do not run
Roomberry and the bench utility concurrently.
