# November 4, 23:02–23:07 — threshold reached; recurring pivot guard blocks recovery

Analysis only. Sources: roomberry/logs/roomberry.log, sensor CSV and NavLink
binary from session 20261104-230159. Build behavior matches 3.1.grout.12.

## Progress and tracking

First outbound began 23:02:11.625. Line loss at 807 mm entered 30 mm/s recovery;
a pivot began around 877 mm and cruise reacquired around 881 mm. Another loss
at 1517 mm lasted over five seconds with intermittent weak readings. Recovery
pivoted at 1721 mm, overshot and reversed; abort at 23:02:29.154 was
“pivot wheel heading moved opposite the commanded turn.” Last moving sample
1733 mm from that run's origin. Sensor odometry was -1732 mm at the second start.
This was not a line-loss timeout or heading-envelope failure.

Second outbound began 23:02:35.649 without returning to the original position.
It had short recovery at 1297 mm, reacquired at 1355 mm, and lost the line again
at 2802 mm. It reached the user-observed threshold while slow at 2955.8 mm from
this second origin; settled at 2959.0 mm. Global wheel odometry at settled
threshold was -4690.9 mm, total accumulated center travel 4695.4 mm. Thus the
rough full outward progress from the original start was 4.69 m, rather than
only the second run's 2.96 m. These are wheel estimates, not independent floor
measurements; the repeated grout start also reseeds its assumed absolute pose.

Recorded GridRunner samples: 141 at -150 mm/s base, 48 at -30, 7 pivot samples
with zero translation, and 2 at +30 return. Actual I/O logs show the intermediate
30 -> 150 steps. No +150 return segment occurred. Lost-line readings were fresh
but absent/low confidence, rather than a phone telemetry timeout. Floor images
are not included, so lighting, feature selection or occlusion cannot be assigned
as the visual cause from telemetry alone.

## The transient filter worked, but the return impact was later

Six phone-bump increments were logged and ignored during outbound within
19–116 ms of actual wheel-speed changes. Immediate launch false-threshold
classification from the previous session was avoided.

Threshold event #9 was at ~23:02:57.460, first/final peak 4344 mm/s².
It occurred after the line had been absent for ~3 seconds, with -30/-30 requests,
well beyond the last speed-change window. The mission braked and waited one sec.

Forward +30/+30 was issued at 23:02:58.709. Event #10 occurred at estimated
23:02:58.923, ~214 ms later. First reported peak was 3731 mm/s², subsequently
updated to 7405 (~0.76 g). The 150 ms window had expired, so the code treated it
as a return impact and stopped at 23:02:59.056. No physical bumper flags appeared
in these threshold/return windows. Sensor odometry advanced only about 12 mm
before stopping. This agrees with the user's roll-off report, but phone motion
alone cannot distinguish ramp descent from drive/handling shock.

Extending a generic ignore window would also suppress real impacts. A bounded,
explicit threshold-exit phase with separate roll-off handling is better targeted
than labeling every return impact as an obstacle. It should keep bumper, drop,
cliff, stale-data and bounded travel/time stops active.

## Why Return to tag 15 did not bring it home

| Request | What it did | Stop reason |
|---|---|---|
| 23:03:51 | Search turns and four scans, no reliable mapped tag | Phone impact during search at 23:04:30.708 |
| 23:04:41 | Search; found tag 16, confirmed two poses; began route alignment | Pivot wrong-direction guard at 23:05:21.933 |
| 23:05:46 | Reused valid tag-16 wheel trace; drove about 76 mm | Same pivot guard at 23:06:01.808 |
| 23:06:30 | Reused trace; drove about 13 mm | Same pivot guard at 23:06:46.411 |

All four button requests returned HTTP 200 and entered homing. It was not an
entry refusal. An intervening Clock start at 23:03:13 timed out without a usable
line and replaced the previous grout object, losing that object's pose as the
initial homing fallback. Tag search therefore had to establish a new position.
A later grout request at 23:07:16 also timed out waiting for a usable line.

Tag 15 was roughly 4.57 m away at the confirmed tag-16 pose, beyond the homing
localizer's 2.5 m range; its absence initially is expected. Finding tag 16 is a
valid localization path. Confirmed poses were (3163.233,1169.216,-97.729 deg)
and (3163.283,1169.230,-97.739 deg), agreeing extremely closely. The later
requests correctly reused that pose plus continuous wheel/pad motion even with
no new tag in view; their logs show tag_fix_applied false because that refers to
a fresh fix in the new homing instance, not absence of a retained valid trace.

## Primary recurring blocker: pivot reversal

The same turn guard now interrupts both ordinary grout recovery and tag homing.
First grout: after overshoot, right correction issued 23:02:28.965, wrong-way
abort 23:02:29.154. Tag homing: reversing commands issued at 23:05:21.929,
23:06:01.796 and 23:06:46.399; respective guard aborts followed only 4, 12 and
12 ms later. The guard anchor predates completion of stopping/reversal. Coast
and delayed wheel counts can therefore trip it as the old turn is finishing.
Stepped translation and the phone-bump filter do not fix this guard, because
it is an encoder-heading guard, not an acceleration event.

This is the priority fix before more speed or grout-gain tuning: brake and
verify settling before opposite pivots; anchor the guard after the new direction
is established, with a bounded startup/progress check. Do not simply remove the
guard or widen its heading limits indiscriminately.

## Secondary observations

One serial sensor write timeout at 23:05:15.022 and one display-write timeout at
23:06:37.756 occurred. Communication resumed; neither is the logged stop reason
for those homing attempts. They remain worth monitoring, especially for blank
LED observations. The current-mode display refresh cannot repair missing serial
communication. No wheel-drop/OI rearm refusal caused these returns.

No code or robot changes made during this review. Priority order: pivot settle/
reversal guard, explicit bounded threshold-exit handling, then retained-pose
handling for unsuccessful fresh grout starts. The previous grid-route shortcut
work remains separate.
