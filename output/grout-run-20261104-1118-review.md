<!-- @(#)grout-run-20261104-1118-review.md 3.1.grout.3 2026/11/04 12:00:00 -->
# Grout tracking and dock-seeking review, November 4, 11:18–11:22

Analysis only. No control changes or robot actions performed.

## Outbound odometry

Sensor counters began at zero and retained odometry epoch 0 throughout the
outbound sequence. Clock restarts reset the per-run logged `wheel_distance_mm`,
but do not reset the cumulative sensor distance. Therefore the total is read
from the sensor CSV, not the final GridRunner leg's relative distance.

| Leg | First drive sample | Stop | Settled cumulative signed distance | Leg travel, rounded |
| --- | --- | --- | ---: | ---: |
| 1 | 11:18:41.968 | 11:19:20.815 | −2192.7 mm | 2192.7 mm |
| 2 | 11:19:27.532 | 11:19:42.256 | −3064.4 mm | 871.7 mm |
| 3 | 11:19:46.823 | 11:19:51.651 | −3351.3 mm | 286.9 mm |
| 4 | 11:19:56.394 | 11:20:12.324 | −4297.9 mm | 946.6 mm |
| 5 | 11:20:16.552 | 11:20:17.769 | −4356.9 mm | 59.0 mm |
| 6, threshold-associated loss | 11:20:21.539 | 11:20:24.781 | −4536.2 mm | 179.3 mm net |
| 7, retry | 11:20:29.404 | 11:20:29.603 | −4539.1 mm | 2.9 mm |
| 8, retry | 11:20:36.581 | 11:20:36.984 | −4546.5 mm | 7.4 mm |

The best threshold-stop wheel result is **4536.2 mm (4.536 m, 14.88 ft)**
from the initial manual tag-15 alignment. Integrated absolute travel is
4537.5 mm, including 1.3 mm of small reverse/forward increments. By the final
retry, signed net travel is 4546.5 mm and absolute travel 4547.8 mm.

These distances already include the wheel-size factor 1.0091597743. The main
stop corresponds to about 4495.0 mm under the former wheel scale. It is 88.8 mm
(1.92%) short of the assumed 4625 mm center-travel reference. This is a visual
line-loss endpoint, not a confirmed physical threshold contact, so that gap
does not justify another wheel-size adjustment. Physical tag-to-threshold
separation also depends on initial center-to-tag and contact geometry; 4536.2 mm
is the robot's wheel-derived travel from manual alignment, not a tag survey.

## Why the stops differed

All eight stops logged the generic line/telemetry-loss reason. Decoding the
binary packets resolves them to explicit invalid detection (`flags=2`,
`reason=1`), rather than stale telemetry or the independent motor lease.

For the first five stops, the immediate packet sequence was valid / invalid /
valid, with approximately 100 ms between packets. Lost sequences were 956,
1170, 1264, 1471 and 1525. The surrounding valid detections had high confidence.
Thus an isolated detector failure is sufficient to brake; Clock resumes after
reacquisition. Wider/combined adjacent-row evidence for the same stripe could
address these detector interruptions without extending blind driving.

At 11:20:24.775, packet 1596 began a sustained failure near the user-reported
threshold. Last commanded offset was −6.45 mm; last commanded angle −2.59°.
The two later Clock presses did arm and briefly command motion, but usable
line detection failed again after 0.2 and 0.4 s. They were not rejected by a
permanent rearm latch. No physical bumper flags were present before this main
stop. A new phone impact appeared before the final retry at 11:20:36.316,
with its recorded peak later refining to 1.72 g; its physical cause is unknown.

## Return-to-base sequence

- 11:21:10: manual tag scan. Tag 15's pose was poor (pose error 63); no world
  localization. Another detected ID 20 had a physically implausible close pose.
- 11:21:20.901–11:21:34.548: first return command. Pi explicitly selected
  `seek_dock` because there was no mapped dock route. Cumulative distance moved
  from about −4546.5 mm to −1393.9 mm by the stop request; it later settled near
  −1358 mm. Thus it did travel toward the outbound start, but used native
  Roomba dock-seeking, not stored-path retracing or tag-15 homing.
- Scans at about 11:21:39 and 11:21:47 saw tag 15 at roughly 1.22 m; this exceeds
  its configured 1.2 m range gate. No accepted localization was reported. A
  very-close ID 5 detection in one scan was also implausible.
- 11:21:56.384–11:22:01.496: second return command, again native dock-seeking;
  cumulative distance was about −734 mm at the stop request, later −679.9 mm.
- Scan requested around 11:22:03 accepted tag 15 by 11:22:07.355. Pose was
  (6983,1307) mm, heading −0.20°, with camera tag range about 0.65 m.
- 11:22:19.053–11:22:33.819: third native dock-seeking interval. Phone impact
  episodes appeared at 11:22:22.350 and .725, then during turning at
  11:22:31.019, .636 and 11:22:32.250. Their refined peaks were approximately
  0.73, 0.55, 0.63, 1.93 and 1.49 g. Bumper contact was mapped by 11:22:24.063;
  sampled bumpers and heading changes confirm contact and subsequent turning.
  Wheel heading advanced from about 9° to 173°. This is consistent with the
  user's account of striking the iPhone, though telemetry cannot identify the
  struck object. The web Stop request ended the mission.

An important mode conflict: native dock-seeking put OI in Passive. The Pi's
bumper recovery repeatedly requested reverse at −80 mm/s, but its guard rejected
37 commands because OI was not Safe. Contact/clear/reseek cycles continued.
Returning to dock currently mixes native firmware navigation and Pi recovery;
this needs deliberate mode ownership before treating it as a controlled return.
Phone-impact aborts used in experiment modes do not provide the same stop
behavior for this native dock-seeking path.

## Tracking quality and map limitations

- No motor-lease expiry in this session. Within active legs, driving samples
  were spaced 201 ms median, 227 ms maximum: the previous map-induced timing
  failure is absent.
- Initial line offset improved from −31.4 mm to −8.1 mm over the first leg.
  Across valid outbound phone detections, median offset was −8.08 mm. Steering
  reached the default 0.25 cap in 10 of 393 driving samples. This supports an
  improved response; it does not independently establish real-world lateral
  accuracy. Main-stop wheel heading was +2.84° relative to the original start.
- Phone CPU median 26.78%, peak 31.87% of one core; memory roughly 14.03–14.09
  MiB; thermal nominal. No resource-overload evidence.
- Current map seeding assumes every newly armed experiment starts at tag 15.
  Clock resumes partway down the floor therefore restart map placement at that
  origin, even though cumulative wheel counters continue correctly. The map
  cannot be used as a continuous world trace of this interrupted outbound run.
  Resume-origin preservation should be addressed separately.

Sources: roomberry/logs/roomberry.log; sensor CSV
roomberry-sensors-20261104-111821.csv; NavLink binary
roomberry-navlink-20261104-111821-0000.bin; local control, mission and survey
configuration. Packet times are Pi receipt times; sensor distances are rounded
to 0.1 mm by the recorder, which does not imply that physical accuracy.
