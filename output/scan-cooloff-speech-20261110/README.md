<!-- @(#)README.md 3.2.scan.2 2026/11/10 13:29:55 -->
# Scan pacing and spoken results verification

Implemented three one-second camera-worker gaps: after capture, detection and
archiving. The existing pre-capture one-second settle remains. Robot scan guard
is held, polling continues, waits hold no camera/detection/mission locks, and
shutdown interrupts each gap without publishing or announcing an incomplete
result. A queued spoken summary reports tag IDs, camera ranges and detector
read quality through the existing RoomTrek SPEAK transport.

Warm recorded timing before the change: pause0.141s,settle1.007s,capture0.093s,
detect2.854s,JPEG0.693s; median total5.002s. First total17.804s. The added3seconds
imply approximately8s warm/21s cold under similar conditions. No physical-run
timings or serial-error improvement are claimed yet. Separate detector process
avoids sharing the GIL; single-core CPU capacity remains shared.

Validation: 26 focused camera/scan-speech/catalogue tests pass; all734Python
tests pass in101.313seconds. Tests verify stage order, free locks/held guard,
shutdown interruption at all gaps, deferred publication, speech-callback fault
isolation, clear/marginal/weak/unknown metadata, duplicate observations, mapped
tag preference, no-tags/skipped/failure messages and existing speech queue jobs.

Quality labels are heuristic detector-read bands, not localization confidence
or an AR-map lock. Distances explicitly refer to the camera. No app update is
needed: sync/restart the three Pi modules roomberry.py, roomberry_camera.py and
roomberry_speech.py. Default camera.scan_cooloff_seconds is1.0;0disables extra
gaps. See [complete timing/quality documentation](../../roomberry/docs/tag-scan-pipeline.md).

No live robot movement, scan, AR/map command, deployment or phone installation
was performed. No change to the legacy web-app.
