<!-- @(#)queued-control-changes.md 2.3.19 2026/10/28 22:00:00 -->
# Implemented control changes

The changes queued after the 2026-10-28 14:20 run are now implemented locally:

- Wall-contact avoidance clears 180 mm along the avoidance heading before boundary seeking resumes. Boundary acquisition then advances to the next map edge instead of returning immediately to the blocked projection. Clearance has a progress/time bound; stationary scan time is excluded.
- Lost localization starts a bounded sequence of stationary scans and encoder-relative in-place viewpoints on a 30-degree grid, covering one full circle at most. The total search is limited to 180 seconds and each turn to 12 seconds. It allows no blind forward transit, preserves hard safety checks, and stops after exhausted viewpoints or a timeout.
- Physical buttons are independently queried through packet 18, with brief Schedule and Clock presses latched until consumed. Group/dedicated masks, mismatches and held-state diagnostics are logged and available in status/CSV. Real Safe-mode button behavior still needs a physical retest; the software cannot manufacture a press that firmware never reports.
- Wheel-drop OI STOP suspends sensor polling and automatic wake, blocks actuator/mode commands, and requires explicit `restart_oi`. Restart stays in Passive, requires fresh startup samples, and invalidates pre-carry localization. Malformed packets are rejected before publication, odometry, buttons, safety processing or CSV recording.
- Soft wheel-speed ramping is enabled at 100 mm/s² acceleration and 200 mm/s² deceleration. Safety braking remains immediate.
- Reverse-current monitoring is enabled in **report_only** mode. It writes candidate reasons, thresholds, applied speeds and event counts to logs, sensor CSV and `/status.json`. It issues no stop, motion, beep or autonomous recovery command.

No deployment or live robot commands were performed for this implementation. See [operator controls](web-controls-cheat-sheet.md) and [ramp/monitor details](motion-ramp-and-reverse-watchdog.md).

## Targeted scan and localization safeguards

Periodic discovery scans during transit or wall following first aim at a surveyed
tag on a plausible visible mounting side, within 250–4000 mm. Selection favors
short range and small camera turns, accounting for the camera optical-axis yaw.
The camera callback only defers capture; the mission coordinator stops and turns.
The first view is centered on the predicted bearing, then retries at +30 and -30
degrees. With 54 degrees horizontal field of view, adjacent planned views overlap
by 24 degrees. A successful localization ends the search immediately. Three
unsuccessful targeted views resume the route with a 20-second search cooldown;
existing planned tag visits retain their bounded lateral repositioning retries.
A lost pose invokes the larger sweep and never permits blind forward transit.
Bumper contact inhibits viewpoint turns and hard hazards retain priority.

The configured localization lifetime is 900 seconds (15 minutes). Fresh tag poses outside
the room rectangle or behind their mounting plane are rejected. Large corrections
after the 30-second jump-reference window require another consistent fresh scan
within 90 seconds (250 mm and 0.35 rad agreement). The pending hypothesis advances
with wheel odometry between views so an intentional camera turn does not itself
prevent confirmation. Initial acquisition still requires one physically valid
scan. These checks do not replace camera calibration or establish pose accuracy.

Sensor CSV now includes `ir_char_omni`, `ir_character_left`, and
`ir_character_right`, taken from the already-polled group 100 with no extra serial
requests. These are raw decoded IR characters, not range or signal strength.
They are recorded for evaluation only; dock IR does not currently alter pose or
motion. A good accepted tag takes priority over rejected duplicate detections in
the scan summary, matching the actual localizer decision.

The four-digit drive display is optional: failures do not terminate the mission
loop, and its discovery stage is initialized before the first idle tick. Display
writes and all other OI traffic remain suspended after a wheel-drop STOP.

## Corrections following the 21:15 run

Scan aiming has its own continuously updated pose; it no longer depends on the
coverage pose, which intentionally clears outside cleaning mode. Each stationary
scan logs its target tag, stage, view number, planned heading, and current pose.
Search retries log their angular offset and encoder target. Explicit camera
requests wake captures after every scan, including requests made during archival;
shutdown also wakes the waiting camera thread. Periodic scans do not accumulate.
When a valid large relocation needs confirmation, recovery holds that view for
one immediate second scan before proceeding to the next angle.

Button-mask disagreements still warn. An unchanged nonzero mask produces one
informational message until the mask changes, explaining that it may be a held
button or firmware-latched state. It does not assert that a physical button is
stuck. This firmware has retained Schedule in Safe mode throughout entire runs.

The installed driver's group-100 omni accessor reads reserved byte 9. CSV now
reads packet 17 from raw byte 10, falling back to the accessor for sensor objects
without a raw group. No installed `irobot` update is required. Earlier omni-zero
CSV values cannot establish that the dock beacon was absent.
