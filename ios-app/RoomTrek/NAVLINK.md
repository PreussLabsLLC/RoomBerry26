<!-- @(#)NAVLINK.md 3.2.imu.1 2026/11/12 15:16:02 -->
# Experimental RoomTrek NavLink extension

Supported by the RoomTrek sender and Pi recorder. Existing types
1–5 are unchanged. Never send this as type 1: its frame and map semantics differ.
All integers little-endian, floats IEEE float32; exactly 128 bytes, UDP port 5010.

| Offset | Type | Meaning |
| --- | --- | --- |
| 0 | 4 bytes | NVLK |
| 4 | u8 | Version 1 |
| 5 | u8 | Type 6 |
| 6 | u16 | Length 128 |
| 8 | u64 | Nonzero attempt/session ID |
| 16 | u32 | Sequence, wraps modulo 2^32 |
| 20 | u16 | Flags: bit 0 valid map-relative camera pose; all others zero |
| 22 | u8 | Tracking: unavailable 0, limited 1, normal 2, interrupted 3 |
| 23 | u8 | Reason: none 0, initializing 1, motion 2, features 3, relocalizing 4, interruption 5, failure 6, other 7 |
| 24 | u64 | Frame timestamp, phone uptime microseconds |
| 32 | u64 | Assembly timestamp, phone uptime microseconds |
| 40 | 16 bytes | Map UUID, canonical UUID byte order; zero for fresh Surveyor; parent UUID for resumed Surveyor |
| 56 | 3 floats | Camera position metres, mapped world (AR.x, -AR.z, AR.y) |
| 68 | 4 floats | Quaternion x,y,z,w: native camera axes into mapped world |
| 84 | float | Optical forward heading radians; atan2(mapped forward y,x) |
| 88 | u32 | Capture age microseconds; UINT32_MAX if unknown |
| 92 | u16 | Feature count |
| 94 | u8 | Relocalization: not needed 0, relocalizing 1, candidate localized 2, lost 3 |
| 95 | 33 bytes | Reserved, zero |

Validity requires a loaded-map session (Navigator or resumed Surveyor) with nonzero map ID, observed relocalization then
normal tracking for at least one second, normal current tracking, usable
horizontal heading, capture age 0–250 ms, no interruption or failure. Invalid
packets are diagnostic history only. Fresh Surveyor never sends map-valid navigation data. Resumed Surveyor uses the same relocalization/validity gate as Navigator.
Pose is camera pose even when a mount transform has been configured; robot pose
must be derived separately using the documented rigid transform.

Receivers must reject invalid lengths/enums/reserved fields/nonfinite
values and inconsistent validity, qualify freshness, deduplicate sequences,
and bind the full map UUID before navigation use. Phone uptime is not Pi time.
No acknowledgment, clock synchronization, robot control or fusion is included.

## Bidirectional control (3.2.navlink.1)

RoomTrek keeps its connected IPv4 `NWConnection` to the configured host
(default `pi`, existing `pi.local` fallback) and UDP port **5010**. The OS assigns
an ephemeral local port that remains stable for the life of that connection.
Previously each AR session start recreated it; now AR start/retry/stop retains
it while the NavLink switch is on. Disabling NavLink closes it. Network failure
may recreate it with a different source port. Commands and replies use that
same connection. There is no second listening port or discovery service.

The existing 128-byte v1/type-6 telemetry, timing, pose validity rules and
latest-only send queue are preserved. The Pi now validates, records and exports
type 6, without passing these camera/map observations into legacy localization
fusion. Types 1–5 and the recording format remain compatible. Original binary
telemetry remains unauthenticated and cannot authorize a command endpoint.

### Provisioning

Generate a random secret, for example `openssl rand -hex 32 > NavLink.key`.
Use the same file on the Pi (configured here as `roomberry/navlink.key`) and in RoomTrek's **Documents/NavLink.key** (Files /
Finder file sharing), then relaunch the app. Its nonempty trimmed UTF-8 contents are the HMAC key; hex text is used as text, not hex-decoded. Protect
the Pi copy with `chmod 600 NavLink.key`. Do not commit real secrets. Missing or
empty phone keys disable control and signed heartbeats; binary telemetry still
works. An invalid configured Pi key fails configuration rather than falling
back to unauthenticated control. Use a separate key for each independently
controlled phone; this receiver controls one authenticated phone at a time.

Enable the existing NavLink switch on the foreground phone. It now opens the
connection while idle too, so a remote start is possible. Camera permission
must already have been granted locally. The Pi's normal NavLink configuration
accepts `command_key_file` in addition to its existing options. Or run the
standalone receiver (only one receiver may bind the port):

```sh
PYTHONPATH=roomberry python3 roomberry/roomberry_navlink.py \
  --directory /var/log/roomberry-navlink --command-key-file /home/pi/Projects/Roomberry/roomberry/navlink.key
```

No key is embedded in the app or transmitted on the network. HMAC authenticates
messages but does not encrypt them. The phones and Pi need clocks agreeing
within 30 seconds. An optional `allowed_source` IP restriction applies to phone
control and binary telemetry; update/remove that restriction if the phone IP
must migrate.

### Datagram format and peer authentication

Control datagrams are UTF-8 JSON, at most 8192 bytes:

```json
{"payload":"BASE64_OF_UTF8_JSON","mac":"BASE64_HMAC_SHA256"}
```

The MAC covers the exact decoded payload bytes. No JSON reserialization is
involved in verification. Each payload has `v:1`, Unix seconds `ts`, and `kind`.
Messages outside ±30 seconds or with invalid MACs are dropped. Unknown peers
receive no acknowledgments. The connected phone socket additionally filters
traffic to the configured Pi IP and port.

Every two seconds the phone sends signed telemetry alongside binary poses:
`kind:"hello"`, `target` (a random UUID for this app process), and `operation`
(the controller status snapshot). The Pi captures the full incoming source
IP/port and sends a signed `kind:"challenge"` with that target and a random
`nonce` to the observed endpoint. The phone answers `kind:"peer"` with the
same nonce and target. Only this authenticated round trip, within five seconds,
updates the command endpoint. Replaying a hello or forging binary telemetry
cannot redirect commands. Authenticated telemetry resuming on a new IP/port
therefore replaces the old peer after the round trip. Peers expire after ten
seconds without a successful proof. Signed responses must come from the current
peer and match a pending ID and target. Late responses from an old endpoint
are dropped; retrying the ID retrieves the cached result on the new endpoint.

The Python CLI sends signed `kind:"command"` requests over loopback to the
existing Pi receiver port. The receiver accepts CLI requests only from
127.0.0.1, pins them to the authenticated phone target, and forwards them from
its bound 5010 socket. Responses return through that socket to the CLI's
ordinary ephemeral client socket. The CLI never binds a second service port. The Pi receiver must bind
`0.0.0.0` (the existing default) to accept both LAN and loopback traffic.

Example decoded command (the receiver fills `target` if omitted by the CLI):

```json
{"v":1,"ts":1794247200,"kind":"command","target":"APP-PROCESS-UUID","id":"COMMAND-UUID","command":"NAV_START","map_id":"MAP-UUID"}
```

| Command | Arguments | Completion |
| --- | --- | --- |
| `STATUS` | none | Controller state and first 20 library map IDs/names in JSON `detail` |
| `SURVEY_START` | optional `map_id` UUID | Fresh survey starts immediately; with map_id, load and relocalize before completing, then continue surveying; fails if active |
| `SURVEY_SAVE` | optional `name` | New atomic revision saved; JSON detail includes map_id, parent_map_id, revision; requires fresh normal, extending/mapped, localized state; capture timeout20seconds |
| `NAV_START` | required `map_id` UUID | Map loaded and localized candidate observed; fails if active |
| `NAV_RETRY` | none | Existing Navigator map reloaded and localized candidate observed |
| `SESSION_STOP` | none | Session paused; NavLink stays available |
| `SPEAK` | required `text`, 1–500 characters | Speech synthesizer finishes; fails if busy, interrupted, backgrounded or audio setup fails |

Commands route through the existing UI/session controller on the main queue,
including ARSession run/pause, delegate callbacks and map-capture completion.
Mutations require the app in the foreground. Starting a new session requires
stopping the old one; a pending save prevents competing starts/saves/retries.
A navigation operation already pending must finish, time out or be stopped
before a remote retry. Local retry terminates the previous pending operation.

`kind:"response"` includes `id`, `target`, `command`, `status`, `detail`, and
`operation`. The phone first replies `accepted`, then `completed` or `failed`.
`accepted` acknowledges authentication/dispatch, not successful ARKit work.
The snapshot reports running/mode/session/map, tracking, interruption, failure,
relocalization and the latest operation error. Tracking failures explicitly fail
pending navigation; map-load errors and missing/corrupt maps return `failed`.
Navigation times out after 30 seconds without a localized candidate, including
when no AR frames arrive. A timeout marks poses invalid until retry. Candidate
localization still requires observed relocalizing then ≥1 second normal tracking;
it does not prove map accuracy. Later tracking failure is visible in `STATUS`
and signed heartbeat snapshots even after the start command has completed.

IDs are retained for the entire app-process target lifetime: duplicates return
the latest acknowledgment and never execute again. Reusing an ID with different
content is rejected. At 10,000 unique commands the phone refuses new work until
relaunch, rather than evicting IDs and risking duplicate execution. Relaunch
creates a new target, so old commands addressed to the previous target fail.
The relay limits pending routes to 1024, expiring unused routes after 90 seconds.
Use `--target` from the prior response when retrying across CLI invocations;
the running CLI pins this automatically after its first response. Use retries
within the same target; commands are not queued for an offline phone.

### CLI examples

Run on the Pi, alongside its existing configured receiver:

```sh
export ROOMTREK_KEY_FILE=/home/pi/Projects/Roomberry/roomberry/navlink.key
python3 roomberry/roomberry_trek_control.py STATUS
python3 roomberry/roomberry_trek_control.py SURVEY_START
python3 roomberry/roomberry_trek_control.py SURVEY_SAVE --name Kitchen
python3 roomberry/roomberry_trek_control.py SESSION_STOP
python3 roomberry/roomberry_trek_control.py NAV_START --map-id '<UUID from STATUS>'
python3 roomberry/roomberry_trek_control.py NAV_RETRY
python3 roomberry/roomberry_trek_control.py SESSION_STOP
# Reuse the printed command ID to retrieve a result after a response timeout:
python3 roomberry/roomberry_trek_control.py SURVEY_SAVE --name Kitchen --id '<same command UUID>' --target '<target from response>'
```

The CLI retries the same ID every ~1 second, prints JSON acknowledgments and
waits up to 45 seconds (`--timeout`). Exit status: 0 completed, 1 failed or no
fresh peer, 2 response timeout (outcome unknown; do not assume failure or create
a new ID for the same intended operation). `--port` must match the existing
receiver port. A dead receiver or lost response cannot establish execution
outcome; retry the same ID while the same app process remains alive.

### Host validation

```sh
PYTHONPATH=roomberry:roomberry/irobot/tests .venv/bin/python -m unittest \
  roomberry_trek_control_test roomberry_navlink_test
swiftc -module-cache-path /tmp/roomtrek-swift-cache \
  ios-app/RoomTrek/RoomTrek/TrekControl.swift \
  ios-app/RoomTrek/tests/ControlChecks.swift -o /tmp/roomtrek-control-checks
/tmp/roomtrek-control-checks
```

These exercise authenticated envelopes, asynchronous acknowledgments, duplicate
suppression, changed-content rejection, endpoint challenge/migration, peer
filtering, timestamp expiry, malformed datagrams, type-6 validation/CSV and a
real loopback relay using the receiver's bound UDP socket. ARKit-independent
Swift checks use an injected executor. Actual camera permission, tracking
failure, map capture/load, relocalization timeout/retry and Wi-Fi endpoint
changes still require device trials; a host build does not establish ARKit
runtime behavior.


## SPEAK voice settings

The foreground RoomTrek UI offers an Australian voice menu, persisted preferred
voice identifier, pitch and speaking-rate sliders, and **Test Voice**. Initial
pitch is **1.08**, rate **0.52** (AVSpeechUtterance rate units). Values persist
in UserDefaults with the preferred identifier and apply to both SPEAK and Test
Voice. Test Voice says exactly:

> G’day, Captain! I’m running a bit low on juice!

Audition the installed options to choose a young-sounding Australian English
female character. The app does not infer age or gender from a voice name or
quality, nor require a particular named voice. It enumerates installed `en-AU`
voices at launch, foreground return and speech requests, logging every name,
identifier, language and quality (default/enhanced/premium with numeric raw value)
as `speech_voice` events in the existing JSONL log. Export Log + Pose CSV to
inspect them. Higher quality is a fidelity preference, not an age/gender claim.

Selection order: saved identifier if still in the installed Australian inventory;
otherwise another installed Australian voice, ordered by descending quality and
then identifier for stable choice; otherwise `utterance.voice = nil` to use the
system default. Automatic selection uses that same Australian-first order.
A missing preferred identifier is retained so it can be used if restored later;
the UI labels its unavailability. Speech logs the actual selected identifier
(or system default), pitch, rate and final result. Installation of voices remains
an iOS setting; the app never assumes a voice is downloaded or downloads one.

```sh
python3 roomberry/roomberry_trek_control.py SPEAK \
  --text 'G’day, Captain! I’m running a bit low on juice!'
```

The command uses the existing authenticated socket, IDs and duplicate suppression.
It returns `accepted` immediately and `completed` after speech finishes.
A second utterance while busy fails explicitly rather than adding an unbounded
queue. Backgrounding or audio interruption cancels speech and reports `failed`.
Pitch is limited to 0.5–2.0, rate to Apple's supported min/max; invalid persisted
numeric settings fall back to the initial values. Actual accent/character and
audibility must be checked on each phone with Test Voice.

Speech settings/fallback checks (no audio is spoken):

```sh
swiftc -module-cache-path /tmp/roomtrek-swift-cache \
  ios-app/RoomTrek/RoomTrek/TrekSpeech.swift \
  ios-app/RoomTrek/tests/SpeechChecks.swift -o /tmp/roomtrek-speech-checks
/tmp/roomtrek-speech-checks
```


### Short operator-supplied key support (3.2)

Both key loaders accept any nonempty trimmed file contents, including the
operator-supplied short key. Empty files are rejected. HMAC uses the exact UTF-8
bytes without hashing, padding or interpreting numeric/hex strings, preserving
compatibility with existing longer keys. The Pi configuration points to
`/home/pi/Projects/Roomberry/roomberry/navlink.key`; the phone reads
`Documents/NavLink.key` at app startup. Relaunch RoomTrek after changing its file.
The local `roomberry/navlink.key` is ignored by git and must be uploaded separately
from the normal Python/config sync (which does not include `.key` files).

### Cumulative kitchen maps (3.2)

`STATUS` advertises `capabilities:["survey_resume_v1"]`, `can_amend`, mapping and
relocalization. `maps` returns up to10 newest entries, including created timestamp,
parent_map_id, lineage_id, revision, features and mapping status. Optional command
`map_prefix` filters the library before limiting results. `map_inventory_errors`
reports unreadable packages instead of presenting a misleading empty library.
These additions fit the existing signed datagram; type6 remains128bytes.

```sh
# Resume a stored map and keep surveying in its coordinates:
python3 roomberry/roomberry_trek_control.py SESSION_STOP
python3 roomberry/roomberry_trek_control.py SURVEY_START --map-id '<kitchen map UUID>' --timeout 45
python3 roomberry/roomberry_trek_control.py STATUS
# After the run, capture the amended revision without replacing its parent:
python3 roomberry/roomberry_trek_control.py SURVEY_SAVE --name kitchen-261109
python3 roomberry/roomberry_trek_control.py STATUS
python3 roomberry/roomberry_trek_control.py SESSION_STOP
```

SURVEY_START without map_id still explicitly starts a fresh survey. The automatic
Pi coordinator only uses that form when no kitchen map exists. A loaded Surveyor
map is not treated as relocalized until observed relocalizing followed by1second
normal tracking. Load/ARKit failures and30second timeout fail the pending command;
no fresh-map fallback occurs. Old packages keep version1 and decode without the
new optional metadata. See roomberry/docs/roomtrek-survey.md for Pi lifecycle.

## Type 7 — independent Core Motion diagnostics (3.2.imu.1)

RoomTrek samples processed device motion at50Hz with the gravity-vertical,
arbitrary-heading reference frame `xArbitraryZVertical`. It does not use a
magnetic-north reference or feed these observations into ARKit. This is a
separate measurement path sharing the same physical sensors, not independent
hardware. Apple describes the processed signals and reference frames in
[Getting processed device-motion data](https://developer.apple.com/documentation/coremotion/getting-processed-device-motion-data).

A separate128byte little-endian type7datagram is sent at10Hz while a phone
session runs and NavLink is enabled. It continues when AR tracking is limited
or its pose is unavailable. Device-motion failure/unavailability is flagged;
there is no fabricated AR-based fallback. A final unavailable packet is queued
on session stop. Existing type6and authenticated controls are unchanged.

| Offset | Field |
|---|---|
|0–7|NVLK,version1,type7,length128|
|8|session uint64; shared with type6|
|16|sequence uint32, independent of type6|
|20|flags uint16, bit0=fresh valid motion|
|22|state uint8:0unavailable,1starting,2valid,3error|
|23|reserved zero|
|24,32|sample_us,send_us uint64, phone monotonic microseconds|
|40|attitude quaternion x,y,z,w:4float32|
|56|bias-corrected gyro x,y,z:3float32,rad/s, native device axes|
|68|user acceleration x,y,z:3float32,m/s², native device axes|
|80|gravity x,y,z:3float32,g, native device axes|
|92|integrated vertical rotation float32,radians,unwrapped|
|96|sample_age_us uint32|
|100|motion_generation uint32|
|104–127|zero padding|

Quaternion uses Core Motion's native device/reference convention, not the
mapped camera quaternion in type6. Do not subtract those quaternions directly.
User acceleration excludes gravity; gravity plus user acceleration/9.80665
reconstructs processed total acceleration in g. These are processed device-motion
signals, not uncalibrated raw hardware readings.

Vertical rate is `-dot(rotationRate, gravity)/length(gravity)` so positive is
counter-clockwise about gravity-up even with a tilted/rolled phone. Integrate
with trapezoidal samples, at the sensor timestamps. A gap over100ms, nonpositive
time step, invalid sample or motion restart breaks the integration baseline;
motion_generation changes so the Pi never treats the discontinuity as a turn.
There is no acceleration-to-position double integration and no compass bearing.
Gyro drift and bias remain observable; this channel is not absolute ground truth.

The Pi records type7in the existing144byte receipt+payload binary log and CSV
export. Receiver validates finite values, quaternion/gravity magnitudes,
freshness flags and ordering; retired sessions/generations cannot replace the
current observation. Older receivers reject only this additional type.

`roomberry_motion.MotionComparison` pairs valid motion with a usable same-session
AR frame and fresh wheel sample within150ms. All comparisons are relative to
one shared starting sample. It reports integrated gyro, unwrapped AR optical
heading, wheel turn, AR-minus-gyro and wheel-minus-gyro in degrees. Session,
motion generation or wheel epoch changes create a new baseline. Motion age
must be<=250ms. AR-unavailable samples remain recorded but do not produce a
three-way comparison. Stale/unavailable readings are hidden by the web panel.

The Pi log contains `RoomTrek motion comparison:` JSON, `/status.json` exposes
`motion_comparison`, and the local console shows Turn comparison. iPhone events
include `motion_sample` at2Hz. The feature never changes pose, navigation,
steering, scan quality or safety. Sync the new Pi modules/web assets and restart
Roomberry, and install the updated iPhone app. On first use allow motion access
if requested. Keep the phone rigidly mounted for meaningful comparisons.
