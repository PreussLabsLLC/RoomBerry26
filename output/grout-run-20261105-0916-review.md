# November 5, 09:16–09:27 — successful contact misreported, stale-frame stops and handoff loops

Sources: roomberry/logs/roomberry.log and matching sensor/NavLink recordings
from 20261105-091626. Physical motor commands were not sent in this investigation.

## Definite regression: success path threw an exception

At 09:18:27.716 both bumper switches pressed during final approach. The return
pose/contact checks passed: execution entered the completion branch. The previous
moving sample estimated range 139.2 mm and camera-line error 8.1 mm. At
09:18:27.729 completion construction threw AttributeError: GridDrive has no
outbound_mm. The mission subsequently reported “mission update error.”

This GridDrive was created by explicit Tag15Return handing to a visible line;
it never had an outbound leg. The field was previously assigned only during
outbound threshold handling. Fixed locally in 3.1.grout.15 by initializing it
to None, representing an unknown/nonexistent outbound leg. Added end-to-end
handoff-to-bumper regression coverage. This fixes reporting/completion, not the
separate pose/telemetry problems below.

## What improved

Weak event #9 (first 3046, later 3331 mm/s²) was recorded-only during outbound;
it did not cause turnaround. Event #14 (peak 4730) was consumed by the speed
change filter. The old wrong-way pivot guard did not abort this session.
Visible-line steering was active after tag handoffs and the robot did meet the
arrival/contact criteria once, despite its completion-report crash.

## An early phone-only threshold remains

At 09:16:44.746 the first outbound marked threshold after 708.4 mm, settling at
729.5 mm. Phone event #6 was 5245 mm/s² (~0.535 g), just above the new 0.5 g
reaction cutoff. The rule behaved as configured. No physical front bumper contact
was recorded there. A generic accelerometer episode still does not establish
that this was the actual kitchen threshold; starting position/physical observation
is required. Threshold plausibility or an independent cue is preferable to
continually raising the cutoff.

## Four “line lost/stale” stops were timing failures with a visible line

Stops at 09:17:21.867, 09:19:25.437, 09:20:01.376 and 09:20:10.027 have nearby
freshly detected high-confidence line packets (roughly .96–.99), not absence of
a stripe. Brief delivery gaps increased the age of the latest image beyond the
250 ms cutoff. Approximate latest frame ages at these decisions were 252, 322,
262 and 336 ms, using receipt minus packet age. New good packets arrived shortly
after some stops. These estimates have normal network/loop timing uncertainty.

The source aborts the mission immediately on that condition, unlike the explicit
line-absent recovery path. The longest second outbound therefore stopped near
3.01 m even though its last moving sample still had confidence .983 and about
7.8 mm camera-line error. A safer improvement is immediate zero motion plus a
bounded fresh-frame reacquisition state, followed by tag recovery if needed;
continuing to drive on stale data is not the proposed remedy.

## Pose provenance can manufacture a near-tag endpoint

New grout requests at 09:19:59/09:20:09 replaced the old trace and seeded an
assumed tag-origin pose, despite starting mid-floor. At 09:20:09.824 the sample
reported tag range 175.9 mm and outbound distance zero. It then aborted on stale
telemetry. Subsequent homing retained that internally continuous pose, even
though it was never a measured absolute location.

The 09:20:51 return request obtained no reliable pose in all three initial scans.
Nevertheless it reused that prior trace and handed to the visible line at
09:21:07.703 with reported range 180.4 mm. Immediately another final 500 mm scan
began. The handoff currently sets tag_fix_applied from prior_valid as well as a
fresh tag fix: continuity of a wheel trace is being promoted to measured tag
provenance. Neither continuity nor an assumed origin establishes actual tag range.
This is a distinct correctness issue, not just camera noise. It is documented
here; the completion-field patch does not purport to fix it.

## Localization sometimes genuinely disagreed

At 09:22:14 the three stationary estimates were approximately:
(5473,1938,-25.7 degrees), (5626,1797,-23.9), (5656,2007,-29.1).
No pair satisfied 75 mm position agreement. Stopping on “no consistent return
localization” was consistent with the quality gate. The logs alone cannot decide
whether tag pose ambiguity/calibration, lighting, movement, or another cause
produced those different poses.

## Final recovery loop: stationary line qualification was not durable under motion

After Restart OI, initial tag poses were confirmed and line following resumed:

| Line resumed | Reported range | Next fallback |
|---|---:|---|
| 09:26:09.135 | 1217 mm | 09:26:11.140 |
| 09:26:32.807 | 1243 mm | 09:26:35.059 |
| 09:26:51.109 | 1116 mm | 09:26:53.122 |
| 09:27:09.062 | 1103 mm | 09:27:11.255 (retry budget exhausted) |

These later losses are real detector “no stripe” packets (flags 2/reason 1),
interspersed with high-confidence detections, unlike the earlier age-only stops.
The line passes the stationary three-frame test but disappears soon after motion.
This supports investigating motion-dependent image quality/feature selection;
blur, exposure, lighting, wrong feature or geometry cannot be distinguished
without phone frames. The one-second loss trigger plus three-handoff budget
then creates repeated scans/restarts and consumes its retries with little reliable
progress. Merely increasing the retry count would prolong this loop.

## Serial failures are another independent problem

Six sensor write timeouts and one display-write timeout occurred. The 09:25:10
Return request was rejected immediately after a sensor fault; its error message
mentions wheel-drop rearming generically, but no wheel-drop latch was the cause.
Restart OI succeeded at 09:25:45. The final return started at 09:27:37, then
aborted after another serial write timeout at 09:27:38.641. These are real I/O
failures; a stronger-looking line or better tag pose does not make motion safe
when sensor polling is unavailable. Hardware/OS/load origin is not established.

## Priorities

1. Completion-field regression fixed in grout.15; sync/restart to apply.
2. Keep assumed origins distinct from tag-measured poses across restarts/handoffs.
3. Stop and reacquire on short packet-age excursions instead of immediately
   discarding the mission; preserve the stale-motion prohibition.
4. Qualify moving line tracking and capture diagnostic phone frames before
   repeating the scan/line/retry cycle or tuning steering gain again.
5. Diagnose intermittent serial write failures separately from visual tracking.

Only the narrowly identified completion-field regression was changed in this
review. No speculative threshold, retry, calibration or freshness changes applied.
