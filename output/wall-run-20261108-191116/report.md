<!-- @(#)report.md 3.1.wall.6 2026/11/08 19:00:00 -->
# WALL follow and successful bumper recovery, then unnecessary realignment

Source: uploaded application log and
roomberry/logs/sensors/roomberry-sensors-20261108-191116.csv. User reports about
30mm remaining to the plank and a final lost-position indication. The physical
gap is operator measured; encoder displacement is not a perpendicular gap.

## Sequence

| Time | Observation |
| --- | --- |
| 19:11:46.427 | Tag16 anchor qualified. |
| 19:12:02.874 | First stopped alignment check loses signal; retry1. |
| 19:12:08.117 | Second check loses signal; retry2. |
| 19:12:16.897 | Third candidate passes full alignment; fresh readings40/39/39. |
| 19:12:16.903 | Follow begins, encoder distance401.98mm, yaw75.04deg. |
| 19:12:20.632 | Right bumper latches owner-side stop. |
| 19:12:20.748 | Mission receives bumper event; recovery is retry3. |
| 19:12:22.359 | Retreat34.10mm qualifies clear bumper/safety and stopped wheels. |
| 19:12:23.577 | Left turn14.33deg completes at yaw100.74deg; right signal32. |
| 19:12:26.380 | Code has re-entered acquisition and advanced another91.07mm; signal32. |
| 19:12:28.398 | Additional left alignment loses signal5; retry4. |
| 19:12:33.837 | Another alignment failure aborts at the four-retry limit. |

First follow segment issued18 drive commands over approximately3.7seconds and
advanced155.23 encoder mm to the contact transition. Signal ranged40–70
(median51) before the collision, above target30: steering was correcting away
from the wall but did not prevent this first contact. The log alone does not
establish exact body heading relative to the plank or a distance conversion.

At19:12:20.634 the first CSV row asserting the right bumper already shows both
applied wheel speeds zero. The event remained latched across switch release.
The reverse and left-turn recovery then worked. This differs from the prior
DIN snag, where no bumper asserted and a two-second stall timeout ended the run.

## Cause of termination

The final reason is exactly `wall alignment failed after four bounded
re-approaches`. WALL does not depend on continued global tag localization after
its start anchor. The recorded termination is not a lost-global-position abort.
Two initial alignment retries, one bumper recovery and one later alignment
retry consumed the shared budget; the next failure stopped the mission.

More importantly, after the successful bumper recovery, signal32 was already
near target30. The `contact_left` transition unconditionally entered `acquire`,
which led to another approach and another nominal45degree alignment sequence.
The robot was repeating initial wall acquisition after it already had a usable
post-recovery wall observation. The ensuing left probe dropped the reading to5.
A larger retry limit would leave this incorrect state transition in place.

## Recommended next increment

1. Preserve the working owner-side bumper latch,30mm retreat and15degree left
   correction. Preserve the stalled-drive fallback for non-bumper snags.
2. After the left correction, stop and collect three distinct fresh readings.
   If usable (initial criterion>=15 units, as in current alignment qualification),
   resume following from that heading. Keep target30; skip the extra approach
   and45degree alignment. Record the successful heading for recovery diagnostics.
3. Reacquire only when that stopped check actually loses the wall. Keep motion,
   time, distance and contact-retry bounds; preserve hard-hazard priority. Track
   initial acquisition retries separately from established-wall recovery in status
   so the termination reason is clear rather than appearing to be lost position.
4. First physical check should be a short parallel follow segment. Stop and
   inspect readings/heading/contact records after roughly300–500mm; then extend
   only if target tracking and post-contact resumption are repeatable. The target
   remains raw intensity, not a guaranteed30mm stand-off.

The observed30mm gap could be consistent with the commanded short retreat at
some point, but final gap cannot be derived from the wheel distance log after
the additional turns and approaches. No physical distance calibration is claimed.

Analysis and recommendation only; no runtime changes or robot commands.
