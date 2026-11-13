<!-- @(#)report.md 3.2 2026/11/09 12:46:33 -->
# WALL run at12:38 — RoomTrek data received and map saved

The Pi recorded **1677 RoomTrek type6 camera-pose packets**, from
12:38:56.231 to12:41:43.816 Pacific:167.584 seconds at10.001 Hz. Sequence
numbers run continuously from0 through1676 in one phone session. All records
pass the current packet decoder.1669 packets (99.52%) have normal tracking;
the first8 are initializing. Maximum reported frame age is163.278 ms.

The stream includes XYZ camera position, quaternion, yaw/heading and tracking
information. It is Surveyor data: map UUID is unset and the map-relative valid
flag is intentionally clear. This does not mean the position stream was absent.
The end position in the survey frame was approximately(-1.951,+0.755,-0.006)m.
Median feature count is3, so normal tracking alone does not establish map
accuracy or coverage. There are no separate raw IMU/type3 packets in this file.

The Pi automatically started Surveyor at12:38:55.916. After the robot stopped,
SURVEY_SAVE completed at12:41:43.538 and the Pi verified a new map entry named
**kitchen-261109** at12:41:43.855. SESSION_STOP completed at12:41:44.167. The
map is in the phone's library; this analysis did not download or inspect it.
Raw decoded poses are in phone-poses.csv and summary values in metrics.json.

## Fridge bypass and final stop

The obstacle bypass began at12:40:26.096 and successfully recorded
obstacle_bypass_heading_resumed at12:41:33.311 after1437.66 mm of bypass travel.
It therefore cleared the original detour before the distance limit. Repeated
wall-signal searches and bumper recoveries explain the controller's hesitant
progress; this is sensor/encoder behavior, not steering driven by phone poses.

Another right-bumper contact occurred at12:41:41.9, beginning another release /
left-bypass attempt. WALL commanded both wheels to−30 mm/s at12:41:42.037 and
aborted at12:41:42.192 with **wheel motion opposite commanded direction**.
Total wheel-derived run travel was3630.82 mm. The stop was not a declared
arrival/completion at the fridge end.

There is evidence of a command-transition accounting problem in that guard:

| Sensor time | Cumulative distance | Latest distance delta | Applied wheels |
| --- | ---: | ---: | --- |
|12:41:41.834|3341.0 mm|+7.6 mm|0 /0|
|12:41:41.997|3345.9 mm|+4.9 mm|0 /0|
|12:41:42.174|3344.6 mm|−1.3 mm|−30 /−30 mm/s|

The guard's prior mission snapshot still held about3341.0 mm. Comparing the next
snapshot3344.6 mm against the newly issued reverse command yields about+3.6 mm
and trips its threshold, even though the latest sensor delta was already−1.3 mm
in the requested reverse direction. Forward roll before the reverse command
appears to be included in the check. This supports a transition-timing hypothesis;
it does not prove physical opposite-direction driving or rule out contact/slip.
No safety thresholds or control code were changed in this analysis.

RoomTrek type6 data is still recorded separately from legacy fusion. It did not
steer WALL during this run. Saved-map accuracy, calibration to the robot frame
and position-aiding integration remain separate validation work.
