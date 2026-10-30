<!-- @(#)web-controls-cheat-sheet.md 2.3.17 2026/10/28 21:10:00 -->
# Web controls cheat sheet

For a stuck robot: press the red stop button, select **Seguro / Safe (2)**,
set speed to **40 mm/s**, then briefly reverse or turn and press Stop again.
Any web drive command takes manual control and cancels the current autonomous mission.

| Control | Effect |
| --- | --- |
| Red minus-sign button / Enter | Zero wheel speed and cleaning motors; also takes manual control. Resets the speed setting to zero. |
| Up / Up arrow | Forward at the selected speed. |
| Down / Down arrow | Reverse at the selected speed. |
| Left / Left arrow | Spin left at the selected speed. |
| Right / Right arrow | Spin right at the selected speed. |
| Speed | Start with 40 mm/s for recovery; reset it after pressing Stop. |
| Seguro / Safe / 2 | Mode for manual driving, with onboard safety protection. Selecting it also takes manual control. |
| Pasivo / Passive / 1 | Interface remains available, but direct wheel driving requires Safe. |
| Completo / Full / 3 | Disables onboard safety protections; avoid for this recovery. The backend requires Safe for movement. |
| Telemetry green play button | Starts telemetry refresh; the adjacent number is the interval in seconds. It does not start robot movement. |
| Clean / Spot / Max / Home | Native Roomba cleaning/docking routines, not Roomberry discovery or its surveyed return route. |

Arrow controls send movement commands, not timed nudges. Keyboard key release
does not send Stop. Explicitly press Stop/Enter after each short movement.
If the keyboard seems inactive, use the on-screen arrows and stop button.

## Direct browser URLs

The configured backend is `http://pi:8080`. Substitute the robot's IP
if that name does not resolve. These URLs send commands immediately when opened.

| Action | URL |
| --- | --- |
| Stop wheels and take manual control | `http://pi:8080/roomba/?op=drive&velocity=0&radius=32768` |
| Select Safe | `http://pi:8080/roomba/?op=_change_mode&mode=2` |
| Reverse at 40 mm/s | `http://pi:8080/roomba/?op=drive&velocity=-40&radius=32768` |
| Forward at 40 mm/s | `http://pi:8080/roomba/?op=drive&velocity=40&radius=32768` |
| Spin left | `http://pi:8080/roomba/?op=drive&velocity=40&radius=1` |
| Spin right | `http://pi:8080/roomba/?op=drive&velocity=40&radius=-1` |
| Live telemetry | `http://pi:8080/roomba/roomba.xml` |
| Live map | `http://pi:8080/map.png` |
| Recent scans | `http://pi:8080/cam/scans.json?limit=5` |

The direct Stop URL zeros the wheels; the red web button also zeros the brushes
and vacuum. A blank response is not confirmation that the wheels moved: check
telemetry and any error response.

## Limits of the current interface

There are no web controls for starting Roomberry discovery, explicitly selecting
its wall-follow survey, or requesting its surveyed return-to-dock routine.
The native Home button is not an equivalent replacement for the Clock action.

After wheel-drop OI STOP, polling and automatic wake are suspended. Movement,
mode changes and beeps cannot rearm it. Once the robot is safely set down, open:

`http://pi:8080/roomba/?op=restart_oi`

This is an explicit command, not a status page. It restarts in **Passive**, clears
the old location estimate and does not resume discovery. Wait for fresh startup
readings (normally about two seconds), then deliberately select Safe or start
discovery. Do not select Full to bypass a rejected motion request.

Read-only diagnostics: `http://pi:8080/status.json` shows `oi_stopped`, `ready`,
sensor age/errors, button masks/source, applied wheel velocities and the
**report-only** reverse-current monitor. Candidate reverse-load reports do not
stop or change movement. Short physical presses are now latched, but firmware
button reporting in Safe mode still needs a physical retest.

### Robot display

The four-character display shows `IdLE` (waiting), `dISC` (discovery), `WALL`
(wall following), `SCAn` (stationary tag scan), `HOME` (return/dock approach),
`bACK` (retreat), `turn` (avoidance turn), `CLn` (cleaning), or `rEM` (manual).
Characters are approximations on the seven-segment display. After wheel-drop OI
STOP the display is no longer updated, so its last label may remain visible.

Discovery transit is now 60 mm/s and wall following 50 mm/s; turns, reversing,
and 25 mm/s proximity creeping retain their previous speeds. Fine-grained wheel
ramp logs use level 5 (below DEBUG); sensor CSV still records applied wheel speeds.

The next configured run uses `roomberry/map-state-reset-20261028-02.json`, starting
with a clean learned map. The previous `roomberry/map-state.json` remains available
for recovery. Surveyed and discovered landmark files are retained. Tag 15 faces
-X into the room, so the corrected 500 mm approach is `(7230, 1520)` facing +X.
