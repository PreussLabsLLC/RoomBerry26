<!-- @(#)report.md 3.2.maps.4 2026/11/10 11:27:28 -->
# Healthy manual survey; tag-return request rejected

The phone tracking result improved substantially. A fresh web survey starts
11:17:48–49 and remains session14180529187437353947 through11:22:26, across all
manual moves.2778packets contain2775normal/3initializing states, with no sequence
gaps, median frame age67ms and median7features. The prior loaded-map session
remains limited before this fresh start. Fresh normal tracking does not prove
saved-map matching or room-coordinate accuracy.

Return to tag15 is requested at11:21:00 and11:21:53. Both commands returnHTTP400:
Save the current phone survey or Stop phone session before starting a mission.
The guard blocks entry to the homing mode before its scan/approach begins.
At11:21:32 the Pi camera independently accepts tag15. The localizer logs
camera translationZ0.707m; this is not a robot clearance measurement. Idle
navigation then logs no active mission. Seeing tag15 does not itself initiate
an autonomous approach.

The new unsaved-survey guard was too broad for this standalone homing command.
Fixed locally: the robot still executes Tag15Return through its existing
gridrunner machinery, but the phone guard/lifecycle receives a distinct
return_to_tag15 intent. That intent preserves an existing phone survey and is
allowed without saving it first. This exception does not relax the ordinary
WALL/GridRunner unsaved-survey restriction, the map-job exclusion, or homing's
fresh stationary tag fix, sensor, route, odometry and contact requirements.

61focused tag-return/map/survey tests pass. Integration tests start real homing
with an unsaved survey, qualify stationary fixes before forward motion, return
idle without any phone command/job, and verify WALL remains blocked. There is
also coverage for homing with no adoption/phone lifecycle ownership.
All726Python regression tests pass in100.164seconds. JavaScript syntax,
whitespace and SCCS checks pass.

Pi-only deployment: sync roomberry_mission.py, roomberry_trek_survey.py and web
help, restart Roomberry and reload the console. The installed iPhone app already
supports it. Then Return to tag15 may start with the fresh survey kept running;
actual approach remains subject to its existing physical-run checks.

Per-session metrics in metrics.json. Read-only supplied-log investigation;
no live movement, phone/AR/map commands or deployment performed.
