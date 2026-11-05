# November 4, 22:18–22:22 — premature threshold detection and rightward homing

Analysis only; no code changes or physical commands. Sources: roomberry.log,
roomberry-sensors-20261104-221835.csv, matching NavLink binary, and archived maps.

## The grout run was trying, at the requested speed

There were six explicit grout starts. Every one issued outbound movement, but
all ended outbound on a phone bump count increment, treated as threshold arrival.

| Attempt start | Threshold marker | Outbound at marker | Settled outbound | Phone bump peak |
|---|---|---:|---:|---:|
| 22:18:44 | 22:18:44.743 | 4.3 mm | 18.6 mm | 4176 mm/s² |
| 22:19:07 | 22:19:13.011 | 715.8 mm | 746.1 mm | 2836 mm/s² |
| 22:19:37 | 22:19:37.775 | 0.0 mm | 31.9 mm | 4476 mm/s² |
| 22:19:57 | 22:19:58.042 | 0.7 mm | 19.7 mm | 3947 mm/s² |
| 22:20:17 | 22:20:17.933 | 0.0 mm | 29.6 mm | 4298 mm/s² |
| 22:21:00 (web) | 22:21:00.914 | 24.9 mm | 35.9 mm | 4645 mm/s² |

Peaks decoded from health packets at the matching bump-count changes. These are
~0.29–0.47 g of reported bump acceleration. No bumper contact was reported in
sensor windows around these threshold markers. Given the user's observation
that threshold was not reached, they are false threshold classifications.

Five markers occurred almost immediately after starting. Direct acceleration,
button/phone handling, chassis vibration or floor features are plausible sources;
the records do not uniquely identify which. The second marker occurred after
~5 seconds/716 mm, so a startup-only exclusion would not necessarily solve all
false triggers. The code currently accepts any new phone bump during outbound,
without verifying threshold position or rejecting motion-command transients.

## Why scans happened at the beginning

Each false threshold classification brakes and enters turnaround, waits one
second, then enters return. Its short wheel-projected tag range is already below
return scan checkpoints. That immediately requests tag scans, often the final
500 mm checkpoint. This was not an intentional outbound startup scan.

Attempt 2 scanned the 2000, 1500 and 1000 mm checkpoints consecutively while
still roughly 0.8–0.9 m from the tag: it was already inside all these distances,
so the checkpoint list drained in successive scans. All three fixes were accepted.
A single forward command followed, then another phone bump stopped it. Attempts
3–6 failed final 500 mm localization, commonly because their fresh assumed
starting pose disagreed with the actual tag pose by >500 mm. Starting a new run
mid-floor recreates the tag-origin assumption; it does not retain a surveyed
absolute starting pose.

## Requested speeds actually recorded

| Operation | Base speed | Wheel requests / observation |
|---|---:|---|
| Grout outbound | -150 mm/s | 31 samples; L -178..-131, R -168..-121, steering applied |
| Grout automatic return | +150 mm/s | One sample; L +119, R +180 |
| Grout slow/final | 30 mm/s configured | Never entered a moving slow/final stage |
| Standalone tag homing | pivots 30 mm/s | L +30/R -30, then reversal |
| Standalone homing translation | 50 travel / 20 final configured | No translation segment was dispatched |
| Manual pad left | opposite wheels at 30 mm/s | Nine explicit left steps between homing requests |

All 32 grout driving samples reported locked tracking; outbound confidence
minimum .863 and frame age maximum .171 s. Thus this is not evidence that the
higher cruise speed outran the line detector before the premature stops.

The command and sensor recordings agree that direct cruise wheel commands were
issued. Example active interval in attempt 2: applied L -178..-133 and R
-166..-121, firmware reported L -178..-135 and R -164..-121 (quantized).
Individual cruise wheel speeds vary with steering; 150/30 are base speeds,
not an instruction to quantize every steered wheel to one of those two values.
Grout motion uses ramp=False; unrelated startup, scan feedback, pad and standalone
homing can still use their original motor paths. The standalone Return button
was deliberately not changed by the grout-only 150/30 experiment.

## Why standalone homing turned right

The first request (22:21:23) confirmed two tag poses by 22:21:31.755. Confirmed
pose: x=6802.5, y=1294.3 mm, heading=-14.47 degrees. Tag 15 is at 7730/1237;
the staging goal is 7156/1211 (radius 174 + staging distance 400, offset 26).
A direct line to staging has heading about -13.3 degrees, nearly straight from
that pose. Nevertheless, its initial commanded heading was -46.42 degrees:
**31.95 degrees right** relative to its localized heading.

Replaying the archived map reproduces the exact waypoint and commanded angle:
path cells (78,14) -> (79,13) -> (80,12) -> (81,12) -> (82,13), first waypoint
6916.5/1174.5 mm. All nearby straight-corridor cells are traversable. A direct
mapped arc to staging checks clear. The shared breadth-first search counts
straight and diagonal neighbors equally and visits negative-y neighbors first;
its first shortest-in-step-count path can zigzag unnecessarily. Homing follows
every cell center without shortcutting. This explains the right turn without
assuming a wildly incorrect tag pose or an obstacle requiring that detour.

The second request (22:22:10) confirmed pose 6815.0/1354.2, heading -21.45
degrees; replay again exactly reproduces a right demand of 20.96 degrees, first
waypoint 6916.5/1261.5. Neither attempt reached translational homing. The large
right motion was an in-place alignment to the first grid waypoint, not a driven
approach aimed far to the right of tag 15.

## Why homing then stopped

Both requests overshot the right pivot, requested a left correction, then
tripped the known wrong-direction guard during reversal. First: spin_left issued
22:21:39.357, abort 22:21:39.377, just 20 ms later. Second: spin_left issued
22:22:31.028, abort 22:22:31.074, 46 ms later. These are consistent with the
previously identified coast/encoder-lag guard fault and the bench stopping times.
That fix was kept on file, not implemented in the speed-only experiment.

## Next work supported by these logs

- Distinguish threshold contact from start/steering/braking/handling transients;
  use bump timing, speed-change context and plausible progress, without simply
  raising the threshold enough to hide real threshold contact.
- Skip already-passed distant scan checkpoints rather than scheduling all of
  them immediately after a short/invalid turnaround.
- Shortcut homing to the furthest clear waypoint or use geometric path costs,
  while retaining swept-footprint clearance checks. Log selected waypoint/goal.
- Implement pending brake/settle-aware pivot reversal and guard anchoring.
- Avoid seeding an absolute tag origin on an arbitrary mid-floor grout restart.

This session did not provide an uninterrupted 150 mm/s threshold run. It exposed
threshold-event classification and route/turn-control issues first. No tuning
or software changes were made during this analysis.
