<!-- @(#)report.md 3.2.analysis.8 2026/11/12 15:38:19 -->
# First IMU / wheel / tag / AR round trip

Run20261112-152528. This is the clearest independent heading comparison so far,
and wheel return closure is excellent. AR translation remains substantially
short of the outbound tag positions and fails to close as well on return.

## Inputs and alignment

One phone session11678513292918582639;4419AR packets all normal,4420valid
Core Motion packets, no sequence gaps in either. One motion generation with
no sensor integration resets. Three repeated IMU sample timestamps at startup
were deduplicated for interpolation (4417unique samples). Sensor age median
11.7ms,p9520.8ms,max177.6ms. Median4AR visual features.1913live Pi comparisons.

Initial tag16capture15:25:49.642 is the only room position/heading anchor.
Phone lens(-66,-58)mm,yaw0,pitch20deg,Pi camera(148,0,137)mm; tag15survey
Y1225mm retained in frozen run-config.json. No subsequent tag corrections,
AR path fit or scale fit applied to these independent tracks. Capture/phone
stationarity checks passed. Wheel travel initial-to-finalcapture8.739m.

## Returning tag16,15:32:22.033

| Source | Position error against final tag | Heading error against final tag |
|---|---:|---:|
| ARKit, mount-corrected robot centre |820.5mm|+0.77deg|
| Wheel-only dead reckoning |12.1mm|+6.46deg|
| Core Motion gyro heading |No standalone position|+0.91deg|
| Wheel distance + gyro heading, offline hybrid |15.5mm|+0.91deg|

Tag robot pose:(3197.8,1148.0)mm,heading-103.66deg.
AR robot pose:(4015.4,1078.2)mm; wheel pose:(3209.2,1143.8)mm.
The final tag pose itself is9.2mm from the initial location,with-5.39deg heading
change. Thus the robot returned close to its starting position, but not with
identical orientation. All final errors use this new tag estimate, rather than
assuming the start/end pose is exactly the same.

Core Motion does not supply an independently measured XY position. The hybrid
uses actual wheel distance, merely replacing encoder-derived heading with
integrated gyro heading. It is an offline diagnostic and did not steer Rosie.
Small endpoint closure can include cancelling path errors; intermediate
checkpoints show larger discrepancies.

## Tag15 checkpoints and centre grout line

| Accepted capture | AR position error | Wheel position error | Gyro+wheel hybrid error | AR heading | Wheel heading | Gyro heading |
|---|---:|---:|---:|---:|---:|---:|
|15:27:54|1034mm|262mm|240mm|-2.05deg|+1.45deg|-1.72deg|
|15:28:08|1113mm|192mm|167mm|-1.69deg|+2.13deg|-1.19deg|
|15:28:29|1192mm|171mm|90mm|-3.93deg|+0.15deg|-3.39deg|
|15:28:50|1235mm|154mm|124mm|-1.33deg|+2.57deg|-0.60deg|
|15:29:02|1237mm|168mm|143mm|-0.96deg|+2.87deg|+0.11deg|
|15:29:50|1234mm|233mm|213mm|-1.94deg|+0.22deg|-1.19deg|

Accepted tag15robot Y estimates lie within25.4mm of1225mm, consistent with the
centre-line run. Final tag15pose:(7337.1,1228.7)mm. The first long-range
confirmation pair differed about245mm laterally, requiring a third view; scan
quality alone does not establish accurate pose. The final close pair repeats
within0.33mm and0.031deg, which is repeatability, not a surveyed absolute error.
Tag-derived checkpoints remain subject to camera intrinsics and survey errors.

## Heading agreement and30degree commands

Across initial-to-finaltag16,AR-minus-gyro absolute median0.37deg,p951.00deg,
max1.60deg. Wheel-minus-gyro absolute median3.28deg,p954.71deg,max5.70deg.
Final wheels exceed gyro by5.55deg; AR differs from gyro by-0.15deg.
Core Motion and AR share physical inertial hardware, so their agreement is not
fully independent ground truth; final tag heading agreement strengthens the
result. Neither was magnetically anchored during this run.

Eleven30degree pad command windows were measured at actual mode-start/result
sample times: total wheel rotation328.04deg versus gyro318.92deg; median wheel
excess0.66deg per command. This suggests encoder rotation tends to overestimate
physical yaw in these conditions. Timing/braking/slip can contribute; do not
change wheelbase calibration from this run alone. Six return-turn commands
also show consistent gyro/AR direction signs, validating the newly added stream.

## Remaining AR distance issue

AR error near tag15 remains1.03–1.24m, predominantly insufficient outbound
translation. By returntag16 its X remains about818mm too far along the room.
Close AR/gyro heading agreement now makes a large heading error a poor
explanation for that translation mismatch. Low feature count may contribute,
but logs cannot distinguish AR metric-scale/drift effects from all other
geometric calibration errors. A physically measured1m straight segment along
the grout remains the useful next discriminating test. Do not double-integrate
phone acceleration or fit a constant AR scale as a substitute for that check.

## Operations

17scans,17completed spoken results. Cold4.406s;warmmedian2.955s,median detector
call0.289s. Zero sensor poll failures or serial write timeouts in this run.
Battery88.0→85.8%. Tag15homing still ends with a safe validation rejection:
393mm robot-centre range versus300mm required; the spoken26cm camera range
has a different origin. This is not yet a completed autonomous arrival.

Analysis,metrics,CSV,standard andIMU-specificPNG/PDF plots,map.png,frozenconfig
and log evidence accompany this report. No configuration/runtime changes.
