<!-- @(#)calibration-20261102-2036-analysis.md 3.1.scan.2 2026/11/02 21:20:00 -->
# Short calibration run, November 2 at 20:36

Sources: `roomberry/logs/roomberry.log`, sensor CSV
`roomberry-sensors-20261102-203605.csv`, and NavLink recording
`roomberry-navlink-20261102-203605-0000.bin`.

- 20:36:23.869: first Clock press is visible in both button packets, OI Passive.
- 20:36:24.028: calibration enters OI Safe.
- 20:36:24.224: local baseline captured; configured leg distance is 1850 mm.
- 20:36:24.424: first reverse command, approximately 50 mm/s.
- 20:36:25.292: GroundHog seq 614, continuity 1, 1338 accepted / 51 rejected.
- 20:36:25.387: GroundHog seq 615, continuity 2, 1339 accepted / 52 rejected.
  Session and calibration identities stay unchanged. Both transmitted packets
  report valid tracking and reason 0. A rejection and recovery happened between
  reports, so the exact rejection reason is absent from this recording.
- 20:36:25.426: calibration correctly aborts on continuity change, then stops.
  The final sensor distance is -35.6 mm. No tag scan is logged in this session.
- OI stays Safe after abort. Both button masks stay zero through the end of the
  sensor recording at 20:36:35.276. The application log ends at 20:36:45.266.
  There is no logged second Clock edge. Safe mode preventing this firmware from
  reporting Clock is consistent with the observed first press in Passive and
  absence of subsequent button input; the data does not prove a second physical
  press time or a hardware fault.

## Development changes

Returning from calibration to idle now restores OI Passive after stopping, so
Clock input is available again. Explicit OI stops are never automatically
rearmed: the mission checks the stop state and the arbiter checks its stop latch
again when executing the mode command. Failure to restore Passive is logged.
Calibration cancellation, completion, and tracking abort retain their results.
Continuity-abort text now includes old/new identities, sequence, flags, tracking
state, reason, and rejected-frame count.

208 calibration, mission, controller, web, and camera archive tests pass.
No deployment or process restart was performed. The underlying one-frame
GroundHog rejection is not fixed by the Pi mode change; calibration still aborts
on such a reset, as required by the heading-control design. Further diagnosis
needs the transient failure reason from GroundHog itself.
