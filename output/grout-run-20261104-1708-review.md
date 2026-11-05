# November 4, 17:08 run — return, missing scan tones, and denied second start

Analysis only; no robot commands or code changes. Sources: roomberry/logs/roomberry.log,
roomberry/logs/sensors/roomberry-sensors-20261104-170802.csv, and the matching
roomberry-navlink-20261104-170802-0000.bin.

The updated mount/target is confirmed: all 3511 recorded GridRunner packets
have lens-left +26 mm and height 85 mm. Pi samples show target_offset_mm=26.
Initial tracking error was −2.78 mm, so the adjusted starting alignment was
close to the new camera-centered target.

Outbound began 17:08:22.739. There were 11 separate slow-mode entries, with no
intervening mission stop. Threshold impact was recorded at 17:09:47.646,
4677.266 mm wheel travel; settled travel was 4684.893 mm (4.685 m). That is
9.870 mm farther than the preceding 16:26 run, on the same wheel scale.

Return began at 17:09:48.676. Phone bump count advanced again at 17:09:49.104,
and the mission aborted at 17:09:49.271. Threshold/withdrawal event peaks were
0.312 g and 0.477 g. This is consistent with the user's threshold-ramp account,
but telemetry cannot identify the physical cause. It was an impact safety stop,
not a no-progress/stuck timeout. The forward pad step completed at 17:10:04.236
with 60.342 mm measured travel for its nominal 50 mm target; the retained trace
remained usable for return resumption.

All four return checkpoints accepted tag 15 and applied the pose:

| Processed | Checkpoint | Tag-derived heading |
| --- | ---: | ---: |
| 17:11:10.861 | 2000 mm | −15.32 degrees |
| 17:11:19.690 | 1500 mm | −10.49 degrees |
| 17:11:30.241 | 1000 mm | −15.01 degrees |
| 17:11:54.036 | 500 mm | +5.68 degrees |

These estimates were not perfectly consistent. Between the 1500 and 1000 mm
fixes, wheel travel advanced 301.3 mm, while the fixes placed the robot at nearly
the same longitudinal coordinate and shifted laterally by 156.6 mm. Between
the 1000 and 500 mm fixes, observed tag heading changed +20.69 degrees while
wheel heading changed +7.32 degrees. The current acceptance checks allow these
changes; a reported accepted pose is not independent proof of physical accuracy.
The final 500 mm checkpoint produced an estimated center-to-tag range of
approximately 620 mm after correction, and final approach began from there.

The final approach exposes the same low-speed response failure with reversed
turn direction. It commanded left 25 / right 15 mm/s throughout, intending a
right turn. Wheel heading instead advanced from +6.23 to +20.02 degrees: a
13.79-degree LEFT turn, against the command. It travelled about 544 mm during
this interval. Right bumper contact at 17:12:08.624 ended the mission; it did
not qualify as verified tag-15 contact. The camera had only intermittent line
observations, and approach uses tag/heading steering rather than grout steering.

Integrating wheel increments from the last accepted pose estimates contact at
(7640,1405) mm, heading +19.47 degrees. Against surveyed tag 15 (7730,1237), that
is about 90 mm longitudinal gap and 168 mm robot-left of its line. The desired
robot center is 26 mm robot-right, so the estimated lateral miss relative to the
intended camera-centered path is about 194 mm. This is a tag-plus-wheel estimate,
subject to the pose inconsistencies above; it does not identify the struck object.

Missing happy/sad scan tones have a software explanation. GridRunner's mission
branch returns before generic localization result feedback, and its dedicated
_scan_tick handler never calls _button_beep for the accepted/rejected result.
Neutral scan-start and unrelated mode/idle tones can still occur. No failing
beeper hardware is established by these logs. Feedback should be emitted by the
checkpoint handler while stationary, before restarting the motion lease.

At 17:12:20.506, both wheel-drop sensors asserted. The controller sent OI STOP
and latched the requirement for explicit rearm. The Reset request at 17:12:41
was rejected: "OI is stopped; use restart_oi explicitly before rearming".
GridRunner starts at 17:12:50 and 17:13:29, and later pad requests, were therefore
rejected. No restart_oi request appears in this log. Once physically grounded,
the intended recovery is explicit restart_oi, fresh sensor qualification, then
a newly aligned run. Ordinary Stop does not clear the wheel-drop latch.

Priorities for subsequent changes: characterize loaded differential wheel
response at 20/30 mm/s (including the final approach); improve tag-pose/odometry
consistency checks; add explicit stationary scan-result tones; make wheel-drop
rearm discoverable in the local UI. No safeguard bypass or control change was
performed during this review.
