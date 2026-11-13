<!-- @(#)report.md 3.2 2026/11/09 22:30:00 -->
# WALL run, November 9 at 12:14 — stop and phone data

WALL stopped at **12:16:55.243 Pacific** with the recorded result:
`aborted: left obstacle bypass exceeded 1500 mm/90 second bound`.

The bypass began at12:15:46.340 after right-bumper contact following a wall-loss
search. It ran68.902 seconds before the stop, so the **1500 mm cumulative bypass
travel limit**, rather than the90-second timeout, caused the abort. Total run
travel was3525.17 mm by wheel odometry (not independently measured distance).
The log contains three contact-recovery attempts and seven wall-loss searches.

Wall reacquisition occurred during recovery, but the bypass remained active.
The controller clears it only after at least200 mm and three fresh samples with
right-wall signal≥20 and heading within20° of the original bypass heading.
There is no `obstacle_bypass_heading_resumed` event. The reference was40.69°;
the last sample was73.72° with signal11.25, outside those heading/signal gates.
The distance bound remained active and the controller stopped and returned idle.
No limits or robot-control logic were changed for this analysis.

## iPhone

The log confirms eight SPEAK acknowledgments and eight completed utterances.
That establishes working authenticated bidirectional command/response traffic
and successful synthesis, independently of the user's audible confirmation.
There was one unavailable-peer result at startup, followed by successful speech.

However, `roomberry-navlink-20261109-121400-0000.bin` is16 bytes: recording header
only, **zero recorded binary telemetry packets**. No RoomTrek poses or raw IMU
samples were recorded for this run. Signed heartbeat/challenge/speech responses
are handled separately and are not binary pose records. Working speech alone
does not establish a running AR session; the supplied log cannot establish the
phone's selected mode, whether Start was pressed, or another ARKit failure.

For map-relative navigation, use **Navigator**: select/import a saved room map,
press Start Navigator, keep NavLink enabled and wait for LOCALIZED (candidate)
and Valid YES. Use **Surveyor** first to scan and save a room map if none exists;
Surveyor pose packets are diagnostic and never set the map-relative validity bit.
RoomTrek sends ARKit camera poses, not the raw acceleration/gyro health stream.

The Pi recorder supports type6 poses, but deliberately does not feed them into
legacy localization fusion. This WALL mission is driven by Pi sensors/encoders
and its tag anchor. Changing RoomTrek mode will not bypass this WALL stop limit.
