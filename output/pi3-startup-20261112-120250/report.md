<!-- @(#)report.md 3.2.analysis.5 2026/11/12 12:09:11 -->
# Pi3 startup diagnosis, 2026-11-12

NavLink and authenticated control work: map refresh completed12:03:18.104,
SESSION_STOP and survey commands were acknowledged, speech completed.
Raw recording contains1569type6packets:365normal/no-map,37initializing,
1167limited/relocalizing (778waiting,389map-lock-lost).

At12:03:28.310 WALL started. Its automatic startup deliberately stopped the
existing healthy fresh session and resumed map11CEE584-D76D-4B69-B3AF-2FE1C804BB7C.
First loaded-map packet12:03:29.423; limited(relocalizing) by12:03:30.314.
After30s without a candidate, automatic retry stopped/resumed the same map
at12:03:59.380. The retry remained limited, ending12:04:22.403 with
SURVEY_START: Session stopped. WALL aborted without moving (travelled0mm).
The phone later reported map lock lost while still limited/relocalizing.
The recording proves the fresh→saved-map transition; the reason the saved map
could not match the scene is not established. It is not a NavLink outage.

The stationary scan12:04:48.016 captured a616x820image, then detector worker
failed12:04:51.067: AprilTag 3 Python bindings are required for tag detection.
The required import is `from apriltag import apriltag`; ImportError may mean
missing package, wrong API, or unavailable native dependency. This was a
software dependency failure, not an image with no visible tag. Scan result
speech explicitly announced failure. AprilTag localization cannot repair an
ARKit saved-map relocalization failure; they are independent systems.

No serial write timeout. Startup0/1byte connection retry and one16/80byte
sensor short read12:02:54.303 preceded the scan. No controller changes.

Next: verify/install the correct AprilTag bindings in the interpreter used to
run Roomberry (verify with python3 -c 'from apriltag import apriltag'). Use the
web map controls in idle to start/keep a fresh survey for the next manual test,
or deliberately resume an appropriate saved map and wait for confirmed map
lock before WALL. Merely starting a healthy fresh phone session does not stop
WALL auto-start from resuming the configured saved map.
