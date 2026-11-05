# November 4, 18:57–19:03 — return tracking and homing stops

Analysis only; no control changes or robot commands. Source: roomberry/logs/roomberry.log.
The matching raw sensor/NavLink recordings are named in the log but are not present
in this workspace, limiting independent motion reconstruction.

## Confirmed homing reversal fault

At 19:01:50.656 the second standalone homing attempt confirmed a tag pose.
At 19:01:55.488 it commanded a right pivot at 30 mm/s wheel speed, aiming to
remove 20.22 degrees of heading error. Wheel heading moved from -1.20 to -19.03
degrees by 19:01:56.934; remaining error was -2.06 degrees, just outside the
2-degree exit threshold. The next sample overshot to -25.16 degrees and +4.06
degrees error, so the controller commanded a left reversal at 19:01:57.118.
The dispatcher stopped the old turn and issued spin_left at 19:01:57.299.
Only 19 ms later the controller aborted with “tag return pivot moved opposite
commanded heading.” The guard anchor was taken before the stop/reversal had
completed, making coast/encoder latency sufficient to trigger the guard. This
is a software control/guard timing fault, not evidence of reversed motor wiring.
No forward homing segment followed this turn.

## Other standalone homing attempts

Attempts ending 19:01:29, 19:02:47 and 19:03:16 deliberately stopped after three
inconsistent stationary tag poses. The code compares each pose only to the
immediately preceding candidate. At 19:01:18/23/28 the first and third poses
agree within 77.8 mm and 0.66 degrees (just beyond the 75 mm position cutoff),
while the middle pose differs substantially. At 19:02:37/41/46 the first and
third agree within 69.9 mm and 1.34 degrees, but the intervening candidate
replaces the first, so this agreeing pair is never considered. At 19:03:05/10/15
first and third agree within 32.6 mm and 1.06 degrees and are likewise missed.
A three-scan consensus over all candidates would have confirmed these last two
attempts without relaxing the existing agreement limits.

## Automatic return never accepted a tag correction

There were two outbound starts. First threshold event: 18:57:48, 1711.6 mm;
its return aborted at 18:58:11 on serial write timeout / sensors not ready.
Second start: 18:58:23; threshold event at 18:59:17, 3005.9 mm, settled 3014.2 mm.
These are separate origins, not additive surveyed tag-to-threshold distances.
A fresh mid-floor start seeds an assumed tag-origin pose, so that assumption
is invalid unless the robot was physically realigned there.

All 11 automatic-return checkpoint scans in the session were rejected. In the
second run the 2 m and 1.5 m checkpoint headings were implausible (-50 to -68
degrees), or failed quality checks. At 1 m and 500 mm, tag positions differed
from wheel prediction by >500 mm. Thus tag_fix_applied remained false and the
controller used grout tracking without a measured tag heading update. It stopped
at 19:01:02 after the final three rejected scans.

At the last moving sample the wheel-projected tag range was 514.6 mm, whereas
stationary detections reported about 1694–1705 mm camera-to-tag distance. These
are different reference points, but the roughly 1.2 m discrepancy is much too
large to treat as a small lateral steering error. Repeated start origin, wheel
slip/odometry and camera pose calibration need separating before relaxing gates.

During the main return the line detector mostly reported high-confidence lock,
with wheel heading ranging -5.36 to +2.08 degrees. Near the end offsets were
4–7 mm against a 26 mm target: approximately 19–22 mm camera-line error, despite
high confidence. This supports persistent offset or following a different image
feature; it does not prove the true floor position or sunlight as the cause.
No slow-mode pivots were selected in this session; no large wheel-yaw runaway
like the preceding run is visible in these samples.

## Next fixes justified by this evidence

1. Brake and settle before reversing a pivot; anchor the wrong-direction guard
   after the new command is established, allowing bounded coast/encoder lag.
2. Compare all stationary scan candidates for a consistent pair, rather than
   discarding an earlier valid candidate when an outlier intervenes.
3. Remove the implicit tag-origin assumption on repeated outbound starts, or
   explicitly require/obtain localization before treating wheel range as absolute.
4. Inspect stationary tag image/camera calibration and record actual line feature
   images before attributing the residual return offset to wheels or sunlight.
