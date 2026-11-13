<!-- @(#)report.md 3.2 2026/11/09 21:00:00 -->
# Roomberry speech and iPhone telemetry check — 2026-11-09

The supplied 11:33 run has **no recorded iPhone telemetry or IMU samples**.
`roomberry-navlink-20261109-113345-0000.bin` and the preceding 11:27 file
are each16 bytes, containing only the recording header. All seven supplied
November9 NavLink recordings are header-only. This establishes zero valid
recorded packets, not whether malformed/unrecorded UDP datagrams arrived.
The run log confirms the receiver bound `0.0.0.0:5010` at11:33:45.058.

Older iPhone IMU data does exist. The newest nonempty supplied recording is
`roomberry-navlink-20261106-125709-0000.bin`, containing1703 type5 GridRunner
packets and1709 type3 phone-health packets. The last type3 packet with its IMU
validity bit set was received **November6 at12:59:59.272957 Pacific (UTC−08)**.
RoomTrek's current type6 packet carries ARKit camera pose and relocalization;
it does not carry raw acceleration/gyro samples. Those are in type3 health
telemetry from the other phone apps.

The supplied `roomberry/autonomy.json` enables the receiver but has **no
`command_key_file`**. That configuration does not construct the authenticated
relay or speech sender. The current run contains no `Speech delivery` entries,
consistent with disabled speech. Telemetry can still be received without a key;
its absence is separate from the missing speech authentication configuration.
No evidence in these files identifies a specific Wi-Fi/hostname/phone fault.

## Changes

The existing Python console now has a Speech section with a500-character input
and Test Speech button. The existing authenticated SPEAK command already accepts
free text, so no additional UDP message type or service port was introduced.
A JSON POST queues the command; the UI polls its ID and distinguishes queued,
phone-accepted, completed, unavailable, failed, dropped and unknown outcomes.
It reports missing key configuration and peer/worker/receiver state explicitly,
plus telemetry counts and the latest phone-health IMU flag and age.

Startup logs explicitly report missing command-key configuration. Pi delivery
logs now include the command ID and phone acceptance/final result. A missing
configuration/peer is rejected before the web request is queued; the button
cannot make an unauthenticated phone speak. Free-text tests use STATUS as their
log category, leaving the16-phrase catalogue intact.

## Run requirements

Sync the changed Python modules and `roomberry/web` assets to the Pi and restart
the service. Provision matching Pi and iPhone Documents/NavLink.key files,
configure `navlink.command_key_file` with the Pi file path, and relaunch the
updated RoomTrek app. Keep it foreground with NavLink on, destination `pi:5010`
(or the existing configured host/port), and Wi-Fi able to reach the Pi. Check
speech readiness in the new panel, then submit the test phrase. A local iPhone
Test Voice distinguishes synthesis/audio problems from the network path.

No Pi deployment, service restart, iPhone installation or live audio playback
was performed during this check. No runtime log/map archives were modified.
