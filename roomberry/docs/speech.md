<!-- @(#)speech.md 3.2 2026/11/09 17:18:03 -->
# Roomberry speech (3.2)

`roomberry_speech.py` owns the language catalogue. The `en-AU`
dictionary has33 mnemonic-to-text entries: the original16 plus16 run-feedback phrases and PHONE_BG. Mission and sensor code
refer to mnemonic codes; translations belong only in the catalogue. A voice's
accent/character still comes from RoomTrek's installed voice settings.

| Code | Australian English phrase |
| --- | --- |
| `IDLE` | Righto, Captain. Standing by. |
| `REMOTE` | You're at the wheel now, Captain! |
| `DISCOVER` | Let's have a squiz around, Captain! |
| `CLEAN` | Time to tidy up, Captain! |
| `HOME` | Heading back to base, Captain! |
| `RECOVER` | Hang on, Captain. I'll get my bearings. |
| `CALIBRATE` | Just checking my moves, Captain! |
| `GRID` | Off along the grid, Captain! |
| `WALL` | Following the wall, nice and steady, Captain! |
| `LOW_BATT` | G’day, Captain! I’m running a bit low on juice! |
| `CRIT_BATT` | Captain, my battery's nearly flat. I've stopped to save juice. |
| `CHARGING` | On the charger, Captain. Topping up the juice! |
| `SCAN` | Hold tight, Captain. Just having a look around. |
| `STATUS` | Righto, Captain. Here's the latest update. |
| `SAFETY` | Steady on, Captain! Safety stop. Please check around me. |
| `ERROR` | Something's not quite right, Captain. Please check the log. |
| `ANCHOR_OK` | Tag sixteen's lined up, Captain. Off we go! |
| `WALL_FOUND` | Found the wall, Captain. Nice and steady. |
| `WALL_LOST` | Lost the wall for a tick, Captain. Having another look. |
| `SEARCH_WALL` | Easy does it, Captain. Looking for the wall again. |
| `WALL_BACK` | There's the wall, Captain. Back on track! |
| `FRIDGE_AROUND` | Bit of a corner here, Captain. Going around to the left. |
| `CONTACT_CLEAR` | Touched something, Captain. Backing clear before turning. |
| `BYPASS_DONE` | Around that bit now, Captain. Carrying on! |
| `IR_UNSTEADY` | The wall reading's a bit jumpy. Holding still for a tick. |
| `NEAR_TAG15` | Let's check tag fifteen, Captain. Stopping for a proper look. |
| `TAG15_APPROACH` | Tag fifteen's in sight, Captain. Moving a little closer. |
| `TAG15_VALIDATED` | Within thirty centimetres and tag fifteen checked, Captain! |
| `RUN_DONE` | All done, Captain. That's the validation run wrapped up. |
| `RUN_STOPPED` | I've stopped the run, Captain. Please check the log. |
| `MAP_READY` | Kitchen map saved, Captain. Ready for the next outing! |
| `PHONE_LOST` | Can't reach the phone, Captain. Please check RoomTrek. |

All records emitted through the server's Roomberry logger carry `speech_code`
and `speech_text`, and the normal formatted log message starts with `[CODE]`.
Detailed original diagnostics, interpolation arguments and tracebacks remain.
Mode-change logs use their specific mnemonic. Stationary scans, battery
low/critical/charging transitions and safety-sensor stops use specific codes.
Other status/debug messages use `STATUS`; other warnings/errors/exceptions use
`ERROR`. These two codes deliberately group detailed diagnostics to keep the
catalogue compact; each diagnostic does not consume a new slot.

Speech announces effective mode changes (including navigation recovery), scan
starts, battery transitions, safety stops and other warnings/errors. Ordinary
STATUS/debug logging does not narrate the stream. Per-code announcements have
a 30-second cooldown; all log entries remain recorded. Transport-result logs
carry the originating code and never trigger more speech. An event may request
speech explicitly using `extra=dict(speech_code='LOW_BATT', speech_announce=True)`.
Use `phrase(code, language='en-AU')` for catalogue lookup; unknown codes/languages
raise an error rather than speaking a raw identifier. The filter safely tags
unknown event codes as ERROR.

## Connection and lifecycle

The existing NavLink receiver must be enabled, listening on `0.0.0.0` (so it
accepts LAN and loopback), with `command_key_file` pointing to the same secret
provisioned in RoomTrek Documents/NavLink.key. Enable NavLink in foreground
RoomTrek. See [RoomTrek protocol/key setup](../../ios-app/RoomTrek/NAVLINK.md).
The server automatically enables the speech worker when the authenticated
NavLink relay is configured. Without a command key it still tags logs and
performs no speech I/O. The reported `control_version` is now `3.2`.

The background worker submits `SPEAK` requests with `text` containing the
catalogue's Australian English string and `speech_code` containing the mnemonic.
It uses a signed ephemeral loopback UDP client to the existing Pi receiver's
configured port (default5010). The receiver forwards from its existing bound
socket to the authenticated phone endpoint; no second service port is opened.
The existing phone-side voice, pitch and rate settings apply without changes.

Delivery uses one speech command at a time, at most four queued announcements,
a 10-second queue expiry and a 45-second response deadline. Retries reuse one
UUID; the phone's target is pinned after its first acknowledgment. Completed,
failed, unavailable, dropped and unknown outcomes are logged with the event's
code. A full queue drops normal new announcements. Higher-priority confirmations can replace the oldest lower-priority queued phrase; queued safety phrases are preserved. Offline/busy speech is not
retried under a new ID, and an unknown execution outcome is never assumed to
mean success. No network call runs on a mission/sensor/logging thread.
Shutdown stops the worker before closing the receiver and removes its logging
filter after resource cleanup. Speech delivery is advisory; motion and safety
decisions remain in their existing controllers.

## Checks

```sh
PYTHONPATH=roomberry:roomberry/irobot/tests .venv/bin/python -m unittest \
  roomberry_speech_test roomberry_mission_test roomberry_control_test \
  roomberry_queued_control_test roomberry_server_test roomberry_map_log_test \
  roomberry_trek_control_test roomberry_navlink_test
```

Tests check the32-entry inventory, mode/battery mappings, original log details,
structured codes, repeated-message suppression, bounded queues, no delivery-log
feedback loop, unavailable-peer handling, text payload, stable retry ID and
pinned target, plus existing mission/safety/control and real UDP relay checks.
No speech audio is emitted by these tests. Pi/phone deployment and live speech
require a separately configured running receiver and phone.


## Web speech test

Open the existing local Python console `/` and use **Speech → Test Speech**.
The text box accepts 1–500 characters and starts with the Captain low-battery
phrase. Free text uses the existing authenticated `SPEAK` payload; it does not
consume a seventeenth catalogue entry or require a new UDP message type/port.
It is tagged `STATUS` in Pi logs. No request changes robot motion.

- `POST /speech` with JSON `{"text":"G’day, Captain!"}` queues a request and
  returns HTTP202 with its command/job ID. Unsupported content type returns415,
  invalid/oversized input400, full queue429, and a missing key, receiver/worker
  or fresh authenticated peer503 with an explanation.
- `GET /speech.json` reports configuration, worker and peer readiness, peer
  age/endpoint, packet counts and the latest health snapshot's IMU flag/age.
- `GET /speech.json?id=<UUID>` also returns the retained job result. The browser
  polls only while its test is pending. `accepted` is a phone acknowledgment;
  only `completed` confirms synthesis finished. Failures, drops and uncertain
  timeout outcomes are displayed explicitly. The last64 jobs are kept in
  memory, and resetting the Pi service clears this history.

The startup log now explicitly says when speech is disabled because
`navlink.command_key_file` is missing. A button cannot bypass authentication:
provision the same key on the Pi and in the phone's Documents/NavLink.key,
configure its path, restart, and enable NavLink in foreground RoomTrek.
Never commit the real key. Retain `pi:5010` or the configured existing destination.
Deploy changed Python modules and `roomberry/web` assets and restart the Pi
service to make the new controls available. The legacy `web-app` is untouched.


## Key file upload

The configured Pi key path is `/home/pi/Projects/Roomberry/roomberry/navlink.key`.
Upload the local ignored `roomberry/navlink.key` separately; normal Python sync
patterns do not include key files. Also upload `roomberry_trek_control.py` with
short-key support and the updated `autonomy.json` before restarting Roomberry.
The matching iPhone file is `Documents/NavLink.key`; relaunch the updated app
and enable NavLink. Both loaders use trimmed nonempty file bytes verbatim.
The key file is credential data and contains no SCCS identification/comment.
