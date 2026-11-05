<!-- @(#)README.md 2.3.analysis.7 2026/10/30 18:10:00 -->

October 30, 17:42 run

The iPhone recorded continuously until 17:50:10: 4,727 packets, no sequence
discontinuities, one AR session/alignment. Battery rose from 97% to 98%, charging
throughout. Four limited-tracking intervals reported insufficient features:
17:47:28.8–33.3 (4.5 s), 17:47:42.4–47.8 (5.4 s), 17:48:33.3–34.8 (1.5 s),
and 17:48:42.1–43.4 (1.3 s). Tracking was valid throughout the final stationary
minute, although visible feature counts were often only 2–4.

Phone alignment uses the accepted retreat tag fix at 17:43:19, a camera lever
arm of 145 mm rearward and 22 mm rightward, and mount yaw estimated as 92.79
degrees from 1,355 straight-motion windows. No later tag correction or scale fit
is applied to the phone. Before the accepted tag-1 relocation at 17:48:23, the
wheel-derived position disagreed with the phone by about 885 mm. After that
correction, agreement is 8–17 mm through the final scan sequence; final positions
are robot (1799.5,1982.8) and phone (1788.9,1983.9) mm. Heading differs by roughly
7 degrees at the last scan. These are comparisons between estimates, not surveyed
accuracy. Clock alignment uses minimum receipt delay; Pi queueing added up to
5.74 s, so instantaneous comparisons during turns remain approximate. The largest
adjacent valid phone-center step was 43.7 mm in 100 ms at 17:46:23.

Bump and go ran 17:44:47–17:46:47, then the original tag-16 goal was retried.
Two later contacts caused further bounded retreats. At 17:48:23 the confirmed
surveyed tag corrected the position by about 0.9 m. An obstacle recorded at
17:45:08 near (1725,2019) occupies cell (19,23), now just 62.2 mm from the
corrected center, versus robot radius 174 mm. This invalidates the planner's
starting footprint. The map has 13 obstacle cells, including five inherited
from the preceding run. The old renderer marked all pending cells unreachable
when its start cell lay inside obstacle clearance. This is a map/pose conflict,
not evidence that the entire room is physically inaccessible.

After the bounded aimed searches, tag-16 detections were repeatedly rejected for
high reprojection error and the fallback requested identical stationary scans
every ten seconds. Wheel drop at 17:49:59 later forced the OI safety stop.

Local runtime changes reduce contact retreat to about 35 mm (two-second cap in
bump and go), choose 10–20 degree turns away from the contacted side, and reduce
ordinary detours to 30–40 mm retreat and 60–120 mm forward legs. A blocked-route
viewpoint is limited to two stationary scans until moving 100 mm or turning
15 degrees, with the existing bounded localization searches exempt. Rendering
now labels reachability unknown for an invalid starting footprint and preserves
blocked-cell colors. The planner's footprint checks and saved map remain intact.
Changes have not been deployed and the map has not been cleared.

Artifacts: trajectory.png, pose-comparison.csv, summary.json, metrics.txt and
map-reachability-preview.png. mission.log, map-state.json and map.png preserve the
uploaded inputs; analyze.py reproduces the comparison from the timestamped raw
NavLink and sensor recordings in roomberry/logs.

Validation: 148 focused mission/mapper/map-image tests pass. Full suite: 253 tests,
252 pass; the existing camera annotation exact-white-pixel test fails. Final
turn-tolerance refinements were verified by the focused suite.
