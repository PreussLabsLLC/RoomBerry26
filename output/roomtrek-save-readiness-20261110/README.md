<!-- @(#)README.md 3.2.maps.2 2026/11/10 11:00:27 -->
# Save readiness and steering preservation

A read-only Pi phone refresh confirmed a running fresh Surveyor session with
normal tracking (`2:0`), `mapping: limited`, `can_amend: false`, no phone error,
and no saved-map parent. Thus mapping qualification, rather than the old-map
lock, disabled Save survey. No live survey, selection or motion was changed.

The fix keeps console fresh/resumed surveys through manual steering and idle,
adds Keep current survey for steering for an existing Surveyor, blocks replacing
an unsaved kept session with an autonomous mission, and explains the specific
save blocker in the panel. Save policy remains strict. Collecting viewpoints
does not guarantee sufficient ARKit coverage.

Validation: 44 focused map/survey/steering tests pass; all 722 Python tests pass
in 103.279 seconds. The actual four-direction pad fixture returns to idle with
zero phone commands or automatic lifecycle jobs during movements. Desktop and
mobile browser simulation verifies limited mapping disables Save with the
specific reason, the Keep action preserves ownership, and extending coverage
enables Save. Updated screenshots and rendered test HTML are in
`../roomtrek-map-controls-20261110/`; the browser script lives at
`/tmp/roomberry-maps-browser-check.py`. JavaScript syntax and whitespace checks
pass. This is a Pi/web change; installed RoomTrek3.2.maps.1 already supports it.

After syncing/restarting the Pi and reloading the console:

1. Keep Rosie Stop / idle.
2. Click Keep current survey for steering, or Start fresh survey.
3. Use measured pad steps to collect additional camera viewpoints.
4. Stop / idle, then Refresh maps & phone.
5. Once mapping is extending/mapped and tracking qualified, save, select the
   saved map and Use for next run before starting WALL.

No live survey adoption/start/stop/save, selection, Pi upload, phone install
or robot movement was performed during this investigation/fix.
