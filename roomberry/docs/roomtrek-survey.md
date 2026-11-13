<!-- @(#)roomtrek-survey.md 3.2.scan.2 2026/11/10 13:25:00 -->
# Pi-controlled RoomTrek surveys

Pi AprilTag scans now include three configurable one-second cool-offs and
spoken tag IDs/camera ranges/read quality through RoomTrek. See
[scan timing and spoken results](tag-scan-pipeline.md). These stationary Pi
scans are separate from the continuously running iPhone AR survey.

## Web controls for a mounted phone

Open the normal Pi console and choose **RoomTrek maps**. Keep RoomTrek open
in the foreground on the iPhone with NavLink enabled. Phone actions do not move
the robot. Map changes require **Stop / idle** and completion of any pending
mission survey save. A map mutation reserves the console against Clock/web
mission starts until it finishes; Stop remains available. Read-only inventory
refreshes may run during missions and are serialized with the survey lifecycle.

- **Refresh maps & phone** reads the full paginated library, file sizes,
  revisions, feature counts, mapping quality at capture and current session.
  The active phone map and next-run selection are shown separately. The
  displayed status is a snapshot; refresh to inspect tracking again.
- **Start fresh survey** stops the existing phone session first, preserving
  saved files, and starts Surveyor without a parent. A separate coordinate
  frame is intentional; unsaved changes in the stopped session are discarded.
  The console keeps this survey through steering-pad/manual-mode moves and
  Stop / idle, without any automatic AR restart or save at each step.
- **Keep current survey for steering** adopts an already running Surveyor
  session, including one started locally on the phone or before a Pi restart.
  It only records ownership on the Pi; it does not stop/restart AR or move Rosie.
  Resume on phone also keeps the resumed survey for manual steering. The normal
  pad controls retain their sensor/bumper/motion-lease guards and measured stops.
  Start WALL/other mapping missions are refused while this kept survey has
  not been saved, before robot commands are issued. Save successfully or use
  Stop phone session to release it. After saving, Use for next run still selects
  the exact saved UUID; the next mission resumes that file as usual.
  With3.2.maps.3, manual steering from idle always leaves the phone session alone,
  including after a Pi restart when Keep has not been pressed. Keep is optional
  for steering, and additionally blocks autonomous missions from discarding an
  unsaved survey. Manual takeover from an active automatic mission retains the
  existing run's save/stop boundary when Rosie returns idle; later pad steps do
  not start another automatic survey.
- **Return to tag 15** can run with an unsaved phone survey. As of3.2.maps.4,
  independent tag homing retains its existing stationary localization, sensor,
  odometry, route and contact guards while leaving the phone session untouched.
  It does not need to save, replace or relocalize the AR map. Stopping/finishing
  homing also preserves the kept survey. Ordinary GridRunner/WALL starts still
  require saving or explicitly stopping an unsaved kept survey. A map mutation
  in progress continues to prevent homing startup.
- **Save survey** stores a new UUID-backed snapshot under the supplied name.
  This also works for a fresh survey started locally in the app. Normal fresh
  tracking and extending/mapped coverage are required. The Pi verifies the
  returned UUID/name in the persisted library. Saving leaves the phone session
  running and does not change the next-run selection.
- Select a saved map and press **Use for next run** to pin its exact UUID for
  subsequent mission/Clock starts. This overrides the configured bootstrap seed
  and automatic revision choice, including maps named outside the kitchen prefix.
  It remains pinned until changed; new saved child revisions are not silently
  selected. Missing selected maps fail explicitly instead of falling back.
- **Resume on phone** stops the current session, resumes the chosen saved map
  and waits for a relocalized candidate, while Rosie remains idle. **Stop phone
  session** stops AR without deleting storage. Neither action changes the
  next-run selection.
- **Rename** changes a file's display name without changing its UUID.
  **Delete selected saved map** asks for confirmation and verifies removal.
  Stop a session before deleting its active map; select another mission map
  before deleting the effective mission selection/configured bootstrap seed.
  Deleting a parent does not cascade to child revisions. Keep parents needed
  for rollback. The phone's local delete button also refuses its active map
  and now reports filesystem errors.
- **Use automatic selection** clears the exact-map override and restores the
  configured seed/revision policy below. It does not start a fresh mission.
  If the configured seed was explicitly deleted after choosing a different map,
  restoring automatic selection may require choosing another existing map.

For the daylight diagnostic: Stop / idle → Start fresh survey (or Keep current
survey for steering if it is already running) → use the steering pad to collect
additional viewpoints → Stop / idle → Refresh maps & phone → inspect tracking
and world mapping → save as `kitchen-daylight` → select it → Use for next run.
The save explanation reports the current blocker. Normal tracking with Limited
mapping does not qualify; wait for Extending/Mapped coverage and refresh again.
More movement does not guarantee that ARKit will establish sufficient coverage.
Rosie still requires a fresh tag16/phone alignment before WALL departs.

The override is atomically stored on the Pi in
`logs/roomtrek-map-selection.json` (override with
`roomtrek_survey.selection_path`). A corrupt selection blocks automated mapping
with a visible error, while the console remains available to choose a new map.
The main `autonomy.json` and phone files are not rewritten by selection.

`GET /roomtrek/maps.json` reads cached state without issuing phone commands.
`POST /roomtrek/maps` accepts JSON actions `refresh`, `fresh`, `resume`, `save`,
`stop`, `select`, `rename`, `delete`, `keep` and returns an asynchronous job. Use `map_id`
for a saved UUID, `name` for save/rename, and `confirm:true` for deletion;
`select` accepts `map_id:null` for automatic selection. Poll the GET route
through job completion. Failures/uncertain outcomes are shown explicitly;
mutating commands are not automatically reissued with new IDs.
`operator_survey` in the GET snapshot reports kept-session ownership and the
last verified saved UUID. This ownership is deliberately not restored across
Pi restarts without rechecking/adopting the phone session. Manually kept surveys
are not automatically saved/stopped on Pi shutdown; save/stop explicitly first.

The signed phone protocol adds `MAP_LIST` (six entries per page, inventory
revision checked across pages), `MAP_RENAME` and `MAP_DELETE`, advertised by
`map_library_v1`. Older apps show an update-required message. No map archives
are transferred to the Pi; storage remains in the iPhone library.

## Battery announcements

After **30 seconds without speech**, Rosie announces both Roomba and iPhone
battery percentages through RoomTrek. The timer restarts on speech acknowledgment
and completion, and checks run only when the speech worker/queue is free.
Failed or unavailable delivery attempts are throttled to 30 seconds.
Roomba readings require sensor age at most two seconds; iPhone readings come
from the latest authenticated heartbeat, at most ten seconds old. Missing
readings are spoken as unavailable; if neither is available no report is sent.
Charging is included when known. A fresh/idle phone session can report battery
without a saved-map lock. Heartbeat beeps do not count as speech.

This update needs both the Pi files and the new RoomTrek app. The existing
`tools/sync-up` copies `roomb*.py` and `web`, including `roomberry_trek_maps.py`,
`web/maps.js` and `web/maps.css`. Pi uploads remain user-owned. Install the app
whose headline is `RoomTrek 3.2.maps.1 2026/11/10 10:15:00`, then refresh the
browser. No cloud service or second UDP relay is needed.
The subsequent 3.2.maps.2 steering-preservation/save-explanation fix is Pi/web
only: sync/restart the Pi and reload the browser; the installed 3.2.maps.1
iPhone build already supports it. No phone reinstall is needed for that fix.
The3.2.maps.3 default manual-steering preservation uses the same Pi-only update.
Restart Roomberry after syncing to clear any backlog of starts/saves accumulated
by the previous manual-mode behavior, then reload the console.
The3.2.maps.4 tag-return exception updates roomberry_mission.py and
roomberry_trek_survey.py plus web help; sync/restart the Pi. The installed phone
app already supports this change.

## Automatic mission lifecycle

The Pi owns the phone's survey lifecycle during a run. In `autonomy.json`:

```json
"roomtrek_survey": {"enabled": true, "map_prefix": "kitchen", "seed_map_id": null}
```

The normal Roomberry process starts its existing authenticated NavLink receiver
and a background survey coordinator. No standalone relay or additional service
port is required. Starting an autonomous mission queues the sequence below.
Manual mode entered from idle issues no phone lifecycle commands and preserves
an already running local or web survey. Manual movement alone does not start
the phone camera. If the phone is stopped, start its survey from the map panel.

1. `STATUS` with `map_prefix:"kitchen"`: wait up to12 seconds for an authenticated
   peer, check `survey_resume_v1`, inspect the newest kitchen revisions.
2. `SESSION_STOP`: stop the previous AR session, keeping its saved maps.
3. `SURVEY_START` with `map_id` of the newest kitchen map, across date changes.
   Once a revision chain exists it takes precedence over independent snapshots.
   Mapped/extending snapshots are preferred over limited saves.
   RoomTrek loads that ARWorldMap, waits for observed relocalizing then at least
   1second normal tracking, and completes only after a localized candidate.
   The same session continues surveying; it does not restart tracking after
   relocalization. An explicit relocalization_timeout or tracking_failure gets
   one intentional restart after an acknowledged SESSION_STOP, using the same
   parent. There are at most two start attempts. Map-load errors, unknown results
   and stop failures do not trigger a new start; cancelling before the retry
   leaves the phone stopped. The Pi allows45seconds for the30second relocalization outcome.
   If there are no kitchen maps, it starts the first fresh survey instead.

Changes between active mission modes remain part of the same survey. Returning
idle (including abort/cancellation) queues `SURVEY_SAVE` with `kitchen-YYMMDD`,
then `STATUS` to verify the exact acknowledged new UUID and expected parent,
then `SESSION_STOP`. The save requires fresh valid normal tracking and
extending/mapped status, checked before and after asynchronous map capture.
It is rejected if tracking/relocalization/mapping is no longer ready.

Every save is a new atomic UUID-backed file: parentMapID, lineageID, revision,
featureCount and existing metadata identify its ancestry. Revision numbers
continue on later dates. Earlier files are retained for rollback; no destructive
merge or overwrite of old independent maps is attempted. Legacy packages still
load as version1, becoming revision1 parents. The map stays in RoomTrek's
Documents/RoomTrekMaps library; this does not transfer map archives to the Pi.
A resumed ARKit session can refine its current world map, but saved feature
count and coverage are not guaranteed to increase monotonically. Prior revisions
remain available if one proves worse.

**No silent reset:** existing-map load failure, relocalization timeout, unreadable
map inventory, or an old phone build stops the mapping attempt explicitly.
The Pi never falls back to fresh mapping when a parent exists. It does not save
an unlocalized child. With the RoomTrek coordinator enabled, WALL now holds
stopped until mapping readiness and fresh tag16/phone binding succeed. Other
mission modes retain their existing asynchronous behavior.

Optional `roomtrek_survey.seed_map_id` in autonomy.json selects a known good
bootstrap map instead of the newest independent kitchen snapshot. It applies
until a parent-linked kitchen revision exists, after which the newest kitchen
revision is used. Leave null for automatic newest usable-map selection. Current configuration
seeds from the mapped WALL snapshot of November9 at17:44:02, UUID
`0B2FA89D-F7EA-4002-9AC7-92C32AF1D0D5`; a byte-identical backup is in
`output/kitchen-map-bootstrap-20261109`. To start a
separate lineage deliberately, choose a different map_prefix; old files remain.
For relocalization, begin with the phone seeing a previously recorded part of
the kitchen. A short map saved only near tag15 might not cover tag16. See
[Apple's session/relocalization guidance](https://developer.apple.com/documentation/arkit/managing-session-life-cycle-and-tracking-quality).
The process resumes saved world state, not a surveyed absolute room origin;
independent tag16 alignment and tag checks still assess accuracy.

The coordinator uses the existing loopback relay and signed command format.
Each request retains its ID and target on retry; failed or uncertain save results
are not blindly retried with a new ID. Start/save errors are logged explicitly,
with phone command acknowledgments and map verification. `/status.json` includes
`roomtrek_survey.status`, `map_name`, `parent_map_id`, `saved_map_id`, `start_attempt`, `phone_session` and `error`. Network/map work
remains on its worker. WALL polls readiness without blocking sensor handling;
startup holds at most120seconds total, with at most60seconds for tag16 after
readiness. Failure aborts stopped. On server shutdown the robot is stopped first, then the
coordinator gets up to30 seconds to drain its pending save before closing the
receiver. An unconfirmed save is never reported as a saved map.

## Phone readiness

The updated app starts NavLink enabled when Documents/NavLink.key is provisioned
and no explicit operator setting exists. Explicit On/Off choices persist across
launches; Off still disables remote commands. Host `pi` and port5010 stay as
configured. Keep RoomTrek open in the foreground, with camera permission granted
and the matching key. iOS still requires the user to unlock/open the app; UDP
cannot launch a suspended or closed application or grant camera permission.
No local Surveyor/Navigator start-button action is needed for an automated run.

The RoomTrek headline displays the installed build's SCCS version and timestamp,
from the AppDelegate SCCS identification string, for example
`RoomTrek 3.2 2026/11/09 12:33:06`.

## Deployment

The user handles Pi uploads. Include `roomberry.py`, `roomberry_mission.py`,
`roomberry_trek_survey.py`, `roomberry_trek_anchor.py`, updated `autonomy.json`, and the existing NavLink,
command and speech modules. The local sync script's `roomb*.py` pattern includes
the new coordinator. Upload the ignored `navlink.key` separately if needed.
Restart the normal Roomberry process; do not start a second relay on5010.
Install the updated RoomTrek build, open it and check the headline and NavLink.

## Checks

```sh
PYTHONPATH=roomberry:roomberry/irobot/tests .venv/bin/python -m unittest \
  roomberry_trek_survey_test roomberry_mission_test roomberry_speech_test \
  roomberry_server_test roomberry_web_test roomberry_trek_control_test
```

Tests inject a phone-command executor and cover lifecycle order, dated names,
mode-transition coalescing, resume/capability/inventory failures, parent and exact-ID verification, worker
drain on close and mission callback dispatch. Actual ARKit map quality and the
next physical run remain device checks. Type6 poses remain recording-only;
this does not change WALL steering or its existing stop bounds.

At mission startup, an authenticated “App must be foreground” failure logs
`PHONE_BG`, sets a persistent warning in `/status.json` and the local console,
and sounds the Roomba's unhappy beep. Open RoomTrek, then retry the mission;
the warning clears after successful survey start. Other offline failures are
not mislabelled as backgrounding. Because a backgrounded RoomTrek also rejects
SPEAK, the warning does not depend on iPhone speech. WALL remains stopped on
startup failure; survey networking remains asynchronous. The console displays
the warning when status refreshes (automatic refresh remains off).

The startup hold rejects tag captures made before phone readiness. Two fresh
consistent tag16 captures and a stationary phone-history pairing are required.
Immediately before departure, the latest phone frame must be fresh, qualified,
and match the acknowledged AR session, selected map and fixed binding. A lost
or changed session aborts departure. No tracking-quality gate is silently
bypassed. After departure, the existing360second drive bound applies; startup
gets its separate120second maximum.
