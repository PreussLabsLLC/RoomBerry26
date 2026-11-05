<!-- @(#)README.md 2.3.analysis.1 2026/10/30 13:45:00 -->
# October 30 ride-along reconciliation

The ride-along supports a real wheel-odometry/localization error, especially in heading. It also exposes phone-frame calibration and Pi logging-timing issues. The phone is useful corroboration, but is not surveyed ground truth.

## Inputs and coverage

All times below are the Pi log's local wall time, October 30 (America/Los_Angeles).

- `roomberry/logs/navlink/roomberry-navlink-20261030-131355-0000.bin`: 3,722 complete records, received 13:13:56.043–13:20:09.600; sequence 1777–5498 with no gaps, duplicates or reordering; one session.
- `roomberry/logs/sensors/roomberry-sensors-20261030-131355.csv`: matching serial sensor run.
- `roomberry/logs/roomberry.log`: matching mission, safety and AprilTag records through 13:23:37.
- `rb.log` contains camera startup information. `roomb.log`, `roomberry.log.23`, and the supplied map-state files predate this run and cannot establish its final geometry.
- The original `map.png` was not saved. In the follow-up, the active `roomberry/map-state-reset-20261028-02.json` was retrieved from the Pi: its modification time is October 30, 13:22:36. It contains 648 trail points and 12 blocked cells. See [reconstructed map](map-reconstructed.png) and [phone overlay](map-phone-overlay.png). These reconstruct the saved state, not the original image pixels.

The NavLink recording ends before the 13:20:11 tag result and before the 13:22:36 wheel-drop/manual-lift event. Its final packets remain healthy and its file ends on a complete record. These files do not establish why transmission/recording ended.

## Coordinate alignment

NavLink alignment token is zero throughout; these are session-relative camera coordinates. Signed wheel travel versus phone translation in 1,092 qualifying half-second straight-motion intervals indicates the phone's camera +Y heading axis faces backward: inferred mount yaw approximately −179.53°. Using the raw heading as robot forward would invert the translation comparison.

For the comparison, infer that constant mount yaw and anchor camera position to the stationary initial-scan robot pose at 13:14:39.062, (1102, 233) mm. This gives a fixed session-to-room rotation of approximately −133.68°. No scale or later trajectory fitting is applied. The camera-to-axle lever arm is unmeasured and uncorrected. Consequently the plotted phone position is an anchored camera trajectory, not a calibrated axle estimate; turns can introduce position differences from the mount offset alone.

See [trajectory.svg](trajectory.svg) and [pose-comparison.csv](pose-comparison.csv). Red lines connect sparse logged poses and include tag corrections; they do not reproduce every part of the map path.

## Where the observations disagree

| Local time | Anchored camera vs Roomberry position separation | Roomberry heading minus phone heading | Age of latest accepted tag |
| --- | ---: | ---: | ---: |
| 13:15:21 | 0.16 m | +2.8° | 0.1 s |
| 13:16:13 | 0.09 m | +1.4° | 19.8 s |
| 13:16:46 | 0.24 m | −13.5° | 53.6 s |
| 13:17:37, right bumper | 0.65 m | −26.9° | 105.1 s |
| 13:18:28 | 0.37 m | −38.6° | 156.2 s |
| 13:19:20, left bumper | 0.85 m | −7.3° | 43.5 s |
| 13:20:04 | 0.84 m | −7.2° | 86.6 s |

The heading discrepancy is especially persuasive because independent calculations from the phone's recorded yaw rate approximately agree with its AR heading change:

| Interval | Wheel yaw change | AR heading change | Integrated sampled phone gyro |
| --- | ---: | ---: | ---: |
| 13:15:22–13:15:44 | −236.8° | −227.5° | −227.7° |
| 13:16:14–13:16:46 | −183.9° | −167.9° | −168.9° |

The wheel estimate overstates these clockwise turns by about 9° and 16°, respectively. This supports turn slip or an odometry calibration error as a contributor. It does not establish a universal correction factor: mixed motions, floor conditions, sampling and phone estimation error matter. AR and gyro share phone sensors and are not statistically independent measurements. The gyro integral uses only the roughly 10 Hz samples transmitted, not a full high-rate recording.

The phone is also imperfect: every packet reports normal tracking and usable pose/velocity/IMU/statistics (flags 111), but median feature count is only 4 (range 1–73). Reported camera height falls about 173 mm from the initial anchor to the final sample. Without a surveyed mount and known height history, this can be pose drift, mount/robot movement, or a mixture. Reported battery falls 77%→20% in roughly 6.2 minutes, unplugged; this deserves a separate device-power check and does not establish why logging stopped.

## AprilTag corrections and map consequences

Accepted tag corrections occur at 13:14:39 (tag 1), 13:14:57 (tag 1), 13:15:21 (tag 2), 13:15:52 (tag 1), and 13:18:37 (tag 2), plus initial idle localization at 13:14:28. Between 13:15:52 and 13:18:37 the robot goes about 165 seconds without an accepted correction. Heading disagreement grows to approximately 39° during that period.

The 13:16:55 and 13:17:04 scans reject large relocations requiring another consistent scan. The logs show that a requested confirmation scan does not necessarily yield confirmation. At 13:18:28 another large relocation is rejected; the 13:18:37 tag-2 scan is finally accepted. That correction substantially reduces heading disagreement, but subsequent camera/robot position separation remains approximately 0.7–0.85 m.

`autonomy.json` configures `max_localization_age` to 900 seconds. Thus `localized=True` in these logs does not mean a recent tag fix: at 13:22:11 it still accompanies a tag age of 214 seconds. Obstacle coordinates are derived from this potentially drifted pose. For example the 13:22:11 contact is mapped near (2239, 82) mm while the robot's logged pose is (2473, 155) mm. Incorrect heading/position can therefore place obstacles incorrectly and distort subsequent planning. The phone recording has already ended by that contact, so its actual room location cannot be checked against NavLink.

At 13:22:24 there is another bumper brake. At 13:22:26 the requested spin is rejected with `Motion rejected while a safety stop is active`; this is an explicit safety rejection, not evidence of silent motor execution. At 13:22:36 both wheel-drop sensors trigger OI STOP and mission idle.

## Timing: delayed receipt is visible in this run

The phone assembles packets every approximately 100 ms without sequence gaps. The Pi repeatedly stops recording receipts for 3–5 seconds, then records many packets less than a millisecond apart. Examples:

- 13:14:50.548→13:14:55.636: 5.088-second receipt gap, but only 99.5 ms between the two adjacent phone send timestamps.
- 13:16:57.353→13:17:02.706: 5.353-second receipt gap, but only 100.7 ms between adjacent sends.

These gaps coincide closely with the native AprilTag detector intervals in `roomberry.log`. This strongly suggests local receiver/thread starvation or queued delivery during detection. It does not by itself prove a particular GIL or networking mechanism. Receiver code timestamps after `recvfrom`, so these timestamps are application dequeue times rather than kernel packet-arrival timestamps.

For this offline comparison, estimate the constant Pi/phone clock offset from the minimum of receipt wall time minus phone send uptime. Map phone capture uptime with that offset. This removes visible burst delays but retains unknown minimum transport latency and possible clock drift; it is not a measured clock synchronization. Estimated excess receipt delay is about 7 ms median, 3.31 s at the 95th percentile, and 5.27 s maximum. Sender-reported frame age remains 29–58 ms, demonstrating that frame age at assembly alone does not detect delayed delivery.

NavLink is currently record-only and cannot have caused the map/navigation drift through pose fusion. Before navigation consumes it, clock synchronization and stale-packet rejection are necessary. Isolating native detection from the receiver process is a candidate improvement to investigate.

## Recommended next changes

1. Calibrate and encode the actual phone mount: backward heading, camera-to-axle translation, and room transform. Preserve native device acceleration axes until explicitly transformed.
2. Investigate wheel-turn calibration/slip using repeatable stationary left/right turns and the phone yaw/gyro comparison. Do not apply a blanket scale correction from this single run.
3. Revisit the 900-second localization lifetime and discovery behavior when tag confirmation fails, since stale poses can continue placing map obstacles. Establish limits appropriate to measured drift.
4. Add clock exchange/freshness checks and investigate the detector-associated receiver stalls before enabling phone navigation.
5. Correct the log-fetch map selection: `roomberry/tools/get-pi-logs` currently fetches `roomberry/map-state.json`, but the configured and logged active filename is `roomberry/map-state-reset-20261028-02.json`. The active snapshot was retrieved separately for this analysis. The ride-along cannot validate the final two minutes because recording ended early.

## Reproduction and limits

`navlink.csv` is the existing receiver's binary-to-CSV export. Run `.venv/bin/python output/navlink-analysis/analyze.py` from the repository root to regenerate the comparison CSV and SVG; redirect stdout to `metrics.txt` for the printed statistics. The script uses NumPy already present in the environment. This is offline analysis only; no runtime, deployment or navigation settings were modified.

## Battery and saved-map follow-up

The user confirmed that the iPhone was not connected to Roomba power and displayed a low-battery/power-saving warning when picked up. The recorded battery state is unplugged in all 3,722 packets. [Battery plot](iphone-battery.png) shows a monotonic reported drop from 77% to 20% over 372.10 seconds (6 minutes 12 seconds), about 9.2 percentage points per minute during this recording. This is the reported charge estimate, not a measurement of energy use or battery health. The final 20% report was assembled at approximately 13:20:07.64 and received at 13:20:09.59. No later battery levels were recorded. NavLink does not encode Low Power Mode or warning presentation, so their exact activation time and effect cannot be established from this file.

`plot-battery.py` produces the PNG and [battery-level transitions](battery-changes.csv). It uses phone packet-assembly uptime to preserve the battery timeline through Pi receive stalls, with the same estimated wall-clock offset described above. The plot ends at the last packet; it does not extrapolate to pickup.

The active saved map was fetched from `/home/pi/Projects/Roomberry/roomberry/roomberry/map-state-reset-20261028-02.json` into `roomberry/logs/`. Its grid is 103 × 92 cells at 87 mm per cell. The trail begins near (1105, 232) mm and ends near (2518, 138) mm, consistent with this run's logged poses. Unlike the stale `map-state.json`, this snapshot can reconstruct the recent map. The saved trail occupies the lower part of the room; in later portions the Roomba estimate runs close to y=0, while the phone camera trajectory remains farther inward. This supports the earlier disagreement analysis, subject to the same phone drift and mount-offset limitations.

`reconstruct-map.py` uses the existing map renderer and current configured landmark coordinates, then adds the previously aligned phone path. Blue is the mapper's saved trail; magenta is the phone camera trajectory. The robot trail continues about two minutes beyond phone coverage. Saved trail points have no timestamps, so this image is a spatial comparison; use `pose-comparison.csv` for simultaneous logged observations. No navigation code, fetch script or runtime configuration was changed.

## Individual-turn investigation

`turns.py` identifies 24 approximately in-place turns of at least 25° during phone coverage. It groups encoder angular motion with low translational motion, adds 0.3-second boundary margins, and compares cumulative wheel angle with interpolated AR heading and the sampled gyro integral. The results are approximate because boundaries and the offline clock offset are estimated; they are diagnostic, not a navigation calibration. See [turn-comparison.csv](turn-comparison.csv).

For 18 turns before 13:19:20, the median AR/wheel angular ratio is 0.9395 (range 0.902–0.963). For six later turns, the median is 0.989 (range 0.986–0.991). Examples: at 13:16:41–13:16:46, encoders report −159.88°, AR −151.59°, and integrated gyro −150.72°. At 13:19:27–13:19:33, encoders report +153.67°, AR +152.01°, and gyro +152.15°. Both turn directions show the earlier discrepancy.

This temporal change argues against treating a fixed wheelbase/scale correction as the complete explanation. Changed traction, floor surface or wheel loading is plausible, but the logs do not label the actual surface at those times, and phone estimation error remains possible. A fixed effective wheelbase near 250 mm could approximately compensate the early ratio relative to the configured 235 mm, but would worsen the later turns; no such change was made.

Independently unwrapping the CSV's left/right encoder counts and recomputing yaw with the runtime's 0.444565 mm/count and 235 mm wheelbase matches successive logged yaw deltas within 0.01°. This checks the logged conversion and rollover handling for this recording; it does not prove the wheel parameters or physical no-slip assumption. The runtime localizer receives these encoder-derived cumulative angles, not the legacy raw OI angle packet.

At one metre of subsequent travel, a 39° heading error creates approximately 0.63 m of lateral error even with accurate distance measurement. Accumulated turn error plus long intervals without accepted tag correction therefore has the right magnitude to explain much of the path discrepancy. This does not establish that every positional error comes from yaw.

Stationary NavLink samples are delayed rather than missing in this recording. Keeping them is useful for detecting phone drift, recording battery state and comparing stationary tag fixes. The serial sensor recorder also shows multi-second gaps (maximum 5.434 seconds), consistent with broader processing stalls. While stopped these gaps need not lose travel because encoders are cumulative. Process isolation remains useful for timely telemetry and control, but is separate from the observed wheel-versus-body rotation discrepancy. Tag detection already calls a native detector through the Python `apriltag` package; implementing the surrounding worker in C is not required merely to give detection a separate process.
