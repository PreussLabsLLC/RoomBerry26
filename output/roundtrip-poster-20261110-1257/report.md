<!-- @(#)report.md 3.2.analysis.2 2026/11/10 13:18:12 -->
# Kandinsky-door round trip: tracking, heading and position

Tracking continuity improved: one fresh phone session,4719packets, all normal,
no reported limited/insufficient-features interval. The preceding full trip had
334limited packets over~33seconds near tag15. Feature median is18now versus5
previously. This is consistent with the poster helping feature availability;
the differing path/turns make it an observational comparison, not a controlled
causal test. Normal tracking still did not ensure accurate metric position.

## Starting tag16 and return check

The initial tag16 capture was12:58:00.654, processed12:58:17.354. We align the
phone robot-centre pose and free wheel integration once to that stationary
tag-derived robot pose, at physical scale1. No later tag pose, path, heading
or scale fitting is applied. This is an offline initial-tag16 alignment, not
an anchor recorded by WALL's live binding code. It uses the configured optical
forward, mount yaw−20deg, lens10mm forward/180mm left.

The return captures at13:05:06.319 and13:05:30.394 agree within2.44mm and0.30deg.
Relative to the first tag16 fix, the last tag16 fix measures25mm position change
and+3.23deg heading change. That gives a substantially better endpoint reference
than the earlier unanchored run.

| Estimate at last tag16 capture | Position difference from tag fix | Heading difference from tag fix |
| --- | ---: | ---: |
| iPhone, robot-centre corrected |520mm|+0.66deg|
| Free wheel integration |196mm|+32.52deg|

Phone heading changes+3.90deg over the loop, modulo360, against the tag-measured
+3.23deg; wheel heading changes+35.75deg modulo360 (395.75deg unwrapped).
The repeated earlier return scan gives the same conclusion: phone heading
differs+0.42deg and wheel+32.21deg. Phone position differs522mm and wheel197mm.
The phone moved<0.5mm between those final captures while Rosie was stopped.

Thus the phone's endpoint heading closes well, while wheel rotation accumulates
a large discrepancy. Wheel position agrees better than phone position with the
tag checkpoints. This does not mean every intermediate phone heading was correct.
Tag/camera calibration and configured mount values remain sources of uncertainty;
these are comparisons to tag-derived poses, not certified ground truth.

## Along the route

Wheel-recorded travel is9.579m:4.619m to the final tag15 validation and the rest
on the manually steered return. The phone and wheel tracks are never corrected
by the intermediate tag measurements in this analysis.

| Confirmed checkpoint | Phone–tag position difference | Wheel–tag position difference | Phone–wheel separation |
| --- | ---: | ---: | ---: |
| First tag15 idle fix,13:00:34 |1053mm|102mm|1095mm|
| Tag15 localize,13:01:08 |1101mm|98mm|1094mm|
| Tag15 localize,13:01:36 |1127mm|158mm|1229mm|
| Tag15 final,13:02:09 |1130mm|197mm|1297mm|
| Tag15 validation,13:02:30 |1220mm|269mm|1374mm|
| Last tag16,13:05:30 |520mm|196mm|342mm|

Maximum phone–wheel separation is1.384m. It shrinks to342mm at the endpoint;
opposing outward/return errors can cancel, so that smaller separation is not
proof that either estimate recovered absolute accuracy. Intermediate confirmed
tag15 heading differences range from−6.6 to−17.3deg for phone and about−3.8 to
+10.0deg for wheels. Endpoint heading closure must not be generalized to every
view or location. Rotation-model calibration and surface-dependent wheel slip
are possible contributors; do not retune wheel constants from this single route.

The live homing controller DOES apply tag corrections, unlike the free wheel
track above. Its final robot-centre range was354mm versus the300mm completion
gate, so it stopped with `tag15 validation outside 300mm`. The two validation
poses agreed closely; this was a repeatable threshold miss, not tracking loss.

## Data qualification

- One phone session9855001675563444002,4719packets,4718unique camera frames;
  two missing packet sequences and no session reset. All report normal/no reason.
- One wheel odometry epoch, no resets during the trip. Battery99.9→97.9%, with
  no low-battery stop. Six sensor-poll write-timeout errors and one display
  write error occur before12:58:06, while stationary; polling recovers before
  the first movement12:58:50. A seventh poll write timeout occurs13:01:14 while
  leaving the stationary tag-fix stage, before homing starts driving13:01:17;
  it recovers. The main log contains19NULbytes; the source
  is preserved, and only timestamped text lines are parsed.
- Initial phone frame pairs8ms from the actual tag capture; final frames pair
  within28ms and17ms. All three stationary windows pass the normal/low-motion
  checks. Early serial trouble makes wheel sampling sparse at the initial scan:
  the nearest recorded wheel sample is357ms away. Bracketing wheel readings
  remain0mm/0deg, and a1.5s stationary window is checked rather than assuming
  simultaneous hardware sampling. Final wheel samples are within69/23ms.
- Pi epoch-minus-monotonic span is<1ms. All comparisons use the detector's
  capture timestamp, not its delayed processing/log-completion timestamp.

[Plot](comparison.png) · [PDF](comparison.pdf) · [Metrics](metrics.json) ·
[Sampled comparison](comparison.csv) · [Tag checks](tag-checks.csv).
Reproduce from the repository root with
`.venv/bin/python output/roundtrip-poster-20261110-1257/analyze.py`.
Script validates single identities, increasing timestamps, and stationary
qualified tag16 pairing. Read-only analysis; no application/configuration
changes, live commands, movement or deployment performed.

## Follow-up: did poll timeouts coincide with scans?

Yes, strongly around the first scan. Six of seven poll failures are inside the
initial tag16 scan window12:57:59.165–12:58:16.942. Failures occur12:58:00.261,
01.353,01.904,03.670,05.080 and05.571. The display write also fails12:58:02.870.
That first scan takes17.777seconds, versus4.3–5.6seconds for subsequent scans.

The seventh poll failure,13:01:14.729, is3.061seconds after a tag15 scan completes
13:01:11.668 and follows the confirmed-pose record13:01:11.810. Encoder readings
and wheel requests remain stationary through that failure; homing starts driving
13:01:17. No poll failure falls inside any of the other eleven scan windows.

These exceptions are `SerialTimeoutException: Write timeout`, on serial command
transmission (including dedicated button polling and a display update). They
differ from the earlier run's zero-byte response reads after Reset Roomba.
The timings establish clustering around initial scan processing and a later
scan-to-homing handoff. CPU/worker startup/IPC load or serial I/O contention are
possible explanations, not diagnoses established by these logs. The detector
already uses a separate spawned process; no direct camera access to the serial
port is demonstrated here. [Full scan-window table](scan-timeouts.csv).
