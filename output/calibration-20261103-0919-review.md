<!-- @(#)calibration-20261103-0919-review.md 3.1.review.1 2026/11/03 09:30:00 -->
# Review of 50 mm/s retries, November 3

| Start | Result | Last outbound wheel travel / turnaround |
|---|---|---|
| 09:19:39 | Continuity 0→1 abort at 09:20:56, after 76.7 s | Last motion sample 4489 mm; phone X -4252 mm |
| 09:21:08 | Bump turnaround, completed 09:21:13 | 61 mm |
| 09:22:43 | Continuity 9→10 abort at 09:22:57 | Last motion sample 780 mm |
| 09:23:08 | Bump turnaround; new return impact aborted 09:23:43 | 1939 mm |
| 09:23:51 | Continuity 10→11 abort at 09:24:20 | Last motion sample 1770 mm |
| 09:24:27 | Bump turnaround, completed 09:24:31 | 52 mm |

Distances are wheel estimates relative to each fresh baseline, not surveyed
threshold positions. Last motion samples precede stopping/settling. No run
reached the 5000 mm wheel-distance limit. The first long run's stop was tracking
continuity loss, not the distance limit or a detected impact. User reports it
was about 5 cm before the physical threshold; that observation is not an
independent scale calibration in the log.

Three reverse events are marked threshold-stop by the software:
- 09:21:10, count 1, peak 5062 mm/s² (~0.52 g).
- 09:23:41, count 6, peak 5463 mm/s² (~0.56 g).
- 09:24:28, count 8, peak 6389 mm/s² (~0.65 g).

The two later events match the expected repeated threshold hits. The earlier
one is another candidate contact; acceleration alone cannot identify what was
hit. All three caused a stop and one-second hold. The 09:23 return encountered
a new event (count 7), initially 3120 mm/s² and refined to 9619 mm/s² (~0.98 g),
which exceeded the return-impact threshold and aborted the run. Its cause
(contact, crossing the edge, vibration, or handling) is not identifiable here.
The other two short runs completed their returns, ending at wheel distances
-12 and -9 mm from their respective restart origins.

Every restart captures a new local origin at its current location. It neither
scans tag 15 nor remembers the previous run's origin. A restart near the
threshold therefore returns only to that nearby restart point. Carrying the
robot invalidates any attempt to sum local runs into a surveyed world distance.

The first reverse leg is much longer than the recent 75 mm/s attempts, but a
controlled repeated comparison is still needed to assign causation to speed.
Its last wheel/phone X disagreement remains about 237 mm (~5.3% of wheel travel);
no scale change is justified without overhead reference.

Sources: roomberry/logs/roomberry.log; sensor and NavLink recordings with
prefixes 20261103-091931 and 20261103-092233. Raw health packets confirm all
three reverse impact counts/peaks and the refined return-impact peak.
