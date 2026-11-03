<!-- @(#)README.md 3.1 2026/10/31 14:35:00 -->
# GroundHog calibration run, 31 October 2026, 14:21–14:25 PDT

All three reverse milestones completed in the second attempt. The return began but was aborted by a phone impact candidate. This analysis changes no robot code or runtime state.

## Sequence and tracking comparison

There were two attempts in this session:

- First: start 14:21:27.629; checkpoint 1 at 14:21:40.239, −490.6 mm wheel travel. Wheel heading changed −11.81° and tag heading changed −13.50°, so the turn is independently visible. GroundHog lost continuity. The next reverse leg aborted at 14:21:46.101 when wheel heading drift exceeded 17.2°.
- Second: start 14:22:40.058; all three checkpoints below completed. Phone continuity remained 25 throughout. Return drive accepted at 14:23:20.115; phone-impact abort at 14:23:20.715. No return checkpoint, tag-verified return, or gentle bumper contact completed.

| Second-attempt milestone | Wheel reverse path | Phone/wheel endpoint difference | Wheel heading change | Phone heading change | Tag/wheel endpoint difference |
|---|---:|---:|---:|---:|---:|
| 1, 14:22:53.321 | 498.8 mm | 26.1 mm | −7.37° | −7.46° | 62.6 mm |
| 2, 14:23:06.337 | 992.0 mm | 56.1 mm | −10.08° | −10.32° | 247.1 mm |
| 3, 14:23:19.986 | 1496.9 mm | 77.4 mm | −11.49° | −11.27° | Tag rejected |

GroundHog path tally increased **1424.4 mm**, versus 1496.9 mm wheel path: 72.5 mm, or 4.84%, less. Its endpoint chord is 1417.6 mm, a different quantity from path length. Phone/wheel heading differences at the three checkpoints are −0.09°, −0.24°, and +0.22°. Translation is an independent optical observation; phone yaw comes from the gyro, which also supplies optical de-rotation. Neither source establishes absolute metric truth without camera, phone mount, and wheel-scale calibration.

## The leftward curve

Both independent relative estimators see it. Negative yaw here means clockwise rotation of the nose, which swings the rear toward robot-left while reversing. From the second attempt's starting heading (−14.35°), final cross-track displacement relative to that initial reverse line is **234.5 mm by wheels and 210.8 mm by phone**. At the first two checkpoints those values were 42.0/38.3 mm and 132.4/118.8 mm. Thus the curve is not just an AprilTag localization artifact.

World +Y displacement is larger (592.8 mm wheels, 551.6 mm phone), partly because the robot began angled relative to world −X. It should not all be attributed to newly developed steering error.

The controller attempted the correct-sign countersteer and reached its ±0.15 steering cap: left −57, right −42 mm/s while reversing. That commands the left wheel to reverse faster and should turn the nose counterclockwise. Despite this, measured reverse distances were:

| Leg | Left encoder travel | Right encoder travel |
|---|---:|---:|
| 1 | −483.7 mm | −513.9 mm |
| 2 | −487.7 mm | −498.8 mm |
| 3 | −501.9 mm | −507.7 mm |

These leg totals include ramps, slowdown and scan boundaries; they are not steady-state motor gain measurements. Nevertheless, they show the residual yaw sign, independently supported by phone gyro. Software command serialization preserves right/left ordering, and the heading feedback sign is consistent with differential-drive geometry. There is no demonstrated steering-sign bug. Unequal low-speed wheel response, drag, wheel/motor condition, or wheel-scale differences remain candidates; a measured straight-wheel test is preferable to assuming one cause. A greater correction range or measured feed-forward trim may help, but should follow that check.

## Reporting change worked

Second attempt: 407 motion packets over 40.66 seconds, all marked valid and in the same continuity segment. Between start and checkpoint 3, accepted-frame count increases 1185 with **zero rejected frames**. Median Pi receipt spacing is 99.8 ms. Maximum phone emission interval is 101.2 ms. This is a substantial improvement over the previous run's two packets during 12 seconds.

Pi receipt gaps still reach 0.99 seconds, despite the regular sender timestamps. Busy Pi-side camera/processing or transport/receive scheduling can delay delivery; the logs do not isolate the cause. Independent phone emission is now functioning. An arrival gap must not be mistaken for a camera tracking break.

## Why the return stopped

The third phone impact candidate arrived at the Pi at 14:23:20.598; the mission aborted at 14:23:20.715 (117 ms later), and logged stop completion at 14:23:20.722 (124 ms after receipt). These are receipt-to-action times, not synchronized physical-impact latencies. Encoder travel between return-drive acceptance and abort was only approximately 15 mm.

The event peak was 3383 mm/s², about **0.345 g**, dominated by native phone Z (−3359.5 mm/s²). X/Y were approximately 278/288 mm/s². With the phone looking at the floor, this is predominantly vertical. Both Roomba bump switches were clear. This is consistent with chassis/mount vibration at forward take-up, a floor disturbance, or an impact; it does not establish obstacle contact. There were two earlier candidates at 14:22:23.642 and 14:22:26.101, before the second attempt. No additional counter increase occurred during its reverse legs.

The low amplitude plus sharp transient can trigger the detector's jerk-sensitive 0.25 g path. Simply raising the amplitude threshold could hide real phone contact. Better next evidence is a controlled stationary-mount and forward/reverse take-up comparison, followed by tuning episode classification if those trials reproduce it.

## Tags, map and resources

Tag 15 was still detected at checkpoint 3: strong margin 119.5, hamming 0, estimated range 1.986 m. Its pose was rejected for a 1875 mm / 0.87 rad jump from the predicted pose. Tag identity confidence does not guarantee pose accuracy. The earlier tag/wheel residual also grew to 247 mm at checkpoint 2, while phone/wheel residual was 56 mm. This favors investigating distant tag pose and camera calibration before trusting that fix or loosening the jump gate. Configured Pi camera intrinsics/mount remain documented placeholders.

`roomberry/logs/map.png` includes both attempts and accepted tag corrections; its blue trail is a fused map history, not an uncorrected independent trajectory. In particular, tag corrections can introduce bends or jumps. The wheel/phone checkpoint comparison separately confirms a physical curve.

Phone battery stayed 100%; app CPU 57.2–65.4%, memory footprint 14.9–41.7 MB during attempt 2. Compass supplied seven usable packets but also reported poor accuracy at other times (10–26.75° range); no compass correction is applied. Phone capture remains 480×640. No source/runtime modifications or deployment were performed for this review.

## Reproduction

Run `.venv/bin/python output/calibration-20261031-1421/analyze.py` from the repository root. It reads the refreshed application log, `roomberry-sensors-20261031-142102.csv`, and `roomberry-navlink-20261031-142101-0000.bin`, then writes `summary.json` and the original checkpoint records in `checkpoints.json`. All displayed times are Pi local wall times (PDT). Starting poses are anchored equal by definition and are not accuracy measurements.
