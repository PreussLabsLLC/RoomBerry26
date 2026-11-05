# November 4, 16:26–16:34 — return and steering-pad review

Analysis only. No code, calibration, or robot commands changed.
Sources: roomberry/logs/roomberry.log; sensor CSV roomberry-sensors-20261104-162646.csv;
NavLink binary roomberry-navlink-20261104-162646-0000.bin under roomberry/logs.

## Outbound

Motion began 16:27:01.674. Threshold impact was recorded 16:28:24.615 at
4665.602 mm wheel travel; settled outbound travel was 4675.023 mm. This is
42.396 mm longer than the 13:14 run and 45.761 mm longer than the 12:53 run.
These are wheel path lengths, not independently surveyed tag-to-threshold
separations. There were three outbound slow-mode episodes totaling 4.106 seconds
before impact, about 5% of the 82.941-second outbound. Wheel-command steering
magnitude averaged 17.20%, with 10.45% of moving time near the 25% limit.

All 4313 recorded GridRunner packets still report lens-left −13 mm, lens height
85 mm, and reverse direction. The earlier +26 mm change is not present in this
app's transmitted mount calibration. A rear-left active lens should have a
positive lateral mount coordinate under the current geometry convention;
its measured magnitude should be verified separately.

## Return chronology

- 16:28:25.607: automatic return began. A new phone impact arrived at
  16:28:26.072; the mission aborted at 16:28:26.194. Threshold/withdrawal impact
  peaks were approximately 0.357 g and 0.332 g respectively. The record does
  not identify their physical causes.
- After a forward pad step, return resumed at 16:29:06.463. It again wandered
  and stopped at 16:29:41.092 on the 20-degree wheel-heading envelope. During
  stable slow forward commands requesting a left turn in 16:29:09–16:29:41,
  aggregate measured yaw moved right at about 0.63 degrees/s.
- Left pad corrections permitted a further return at 16:30:04.776, but the
  heading envelope stopped it at 16:30:18.179. Additional pad turns and forward
  moves repositioned the robot without any logged odometry-discontinuity abort.
- Return resumed 16:31:26.364. The 2000 mm and 1500 mm checkpoint results at
  16:31:36.015 and 16:31:52.698 had no detected tags; no tag pose was applied.
  They completed without the old scan-staleness abort. The operator stopped
  the robot at 16:32:08.118 and used the pad again.
- Final return request: 16:32:54.450. The pending 1000 mm checkpoint accepted
  tag 15 at 16:32:59.171: pose (7335.65,1248.95) mm, heading −14.96 degrees.
  Its corrected position was already within the 500 mm checkpoint, so a second
  stationary scan followed. At 16:33:04.511 the 500 mm fix was also accepted:
  (7335.84,1248.80) mm, heading −14.94 degrees, approximately 394 mm from tag 15.
  Both accepted poses were applied, unlike the earlier unsuccessful runs.
- Final approach ran at 20 mm/s. Its heading correction was capped at +0.25
  (left 15/right 25 mm/s) while the wheel heading moved from −9.74 to −14.44
  degrees: a further 4.70-degree right turn, against the requested left turn.
  Left bumper contact appeared at 16:33:12.189; the mission aborted at
  16:33:12.294. This was not reported as successful tag-15 contact.

Integrating sensor increments from the accepted final tag pose estimates the
contact pose at approximately (7598,1169) mm, world heading −19.6 degrees.
Relative to surveyed tag 15 at (7730,1237), that is about 132 mm longitudinal
gap and 68 mm robot-right of the tag line. This is tag-plus-wheel estimation,
not an independent observation of the struck object or physical contact point.
The heading is outside the allowed final ±0.2 rad (±11.46 degrees) envelope,
explaining why the contact could not qualify as successful completion.
Final cumulative absolute wheel travel was 9420.9 mm, including pad moves;
final signed center-path distance was +54.7 mm relative to initial alignment.

## Pad performance

Completed steps:

| Requested | Count | Measured range | Mean magnitude |
| --- | ---: | ---: | ---: |
| Forward 50 mm | 18 | 56.75–68.19 mm | 62.47 mm |
| Left 5 degrees | 10 | 7.22–9.84 degrees | 8.16 degrees |
| Right 5 degrees | 2 | 7.98–8.97 degrees | 8.48 degrees |

The physical run exposes braking/polling overshoot not represented by the
simple no-coast test model. The implementation brakes only once the reported
progress crosses the target, so travel between sensor samples and subsequent
braking increases the final increment. It needs braking compensation or a
better endpoint approach; the nominal increments currently understate movement.

Four initial pad attempts failed with "Open Interface is not in Safe mode";
retries succeeded. This is consistent with a qualification race: mode entry
logs a successful Safe transition, but drive authorization checks the cached
sensor packet, which may still report Passive until the next poll. It needs
explicit fresh Safe-mode confirmation, not weakening the guard.

## Interpretation and follow-up

This run confirms two distinct facts: controlled pad adjustments keep the saved
trace usable, and accepted tag scans now update the actual return pose. The
remaining veering is not explained simply by missing tag updates. In particular,
the tag-guided final approach still drove right against a left-turn request at
20 mm/s. Low-speed asymmetric wheel response remains a leading hypothesis;
logs do not uniquely identify a mechanical or firmware cause. The camera's
unchanged −13 mm mount value is a separate unresolved calibration discrepancy.

Priorities: confirm the actual GridRunner mount settings; characterize actual
wheel/yaw response to small differential commands; revise final-approach
steering where low speed fails; compensate pad stopping overshoot and wait for
fresh Safe-mode confirmation. No automatic recovery or guard changes were made.

## Startup version diagnostic

The new preview worked. It begins with an escaped NUL followed by bl-start,
STR730, a bootloader ID and bootloader revision. The capture contains 231 bytes;
the existing application-release parser still returns unknown. The first
80-character preview does not include an r3_robot/tags/release string. This
identifies the captured prefix as bootloader output, not a firmware release;
it does not establish whether application output was delayed or absent.
