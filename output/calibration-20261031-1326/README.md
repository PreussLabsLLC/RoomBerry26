<!-- @(#)README.md 3.1.web.1 2026/10/31 14:00:00 -->
# Refreshed calibration logs: 13:26–13:32, October 31

Read the refreshed `roomberry/logs/roomberry.log`, `roomberry/logs/sensors/roomberry-sensors-20261031-132643.csv` and `roomberry/logs/navlink/roomberry-navlink-20261031-132642-0000.bin` before changing the tolerances. The earlier 12:51 report describes a different attempt.

The latest logs confirm the stationary polling fix works: scan-time ages between about 0.51 and 0.77 seconds cause a stopped wait, followed by recovery in about 0.2 seconds. Web `/roomba/?op=cal` requests now receive HTTP 200 and start the mission coordinator.

Several attempts were rejected on their tag-based starting headings (roughly −12°, and one −17.6°), against the old ±8.6° limit. Two attempts successfully anchored tag/wheel/phone measurements and actually reversed:

| Start | Abort | Encoder distance during attempt | Encoder yaw change | Outcome |
| --- | --- | ---: | ---: | --- |
| 13:29:45.149 | 13:29:48.992 | approximately −208 mm | −8.67° | Old heading-drift limit exceeded before 500 mm |
| 13:32:07.185 | 13:32:13.027 | approximately −348 mm | −8.78° | Old heading-drift limit exceeded before 500 mm |

Distances/angles use sensor samples closest to start/abort log timestamps, not a claim of exact capture synchronization. The latest attempt starts at about (7495,1177) mm with heading −6.83°. Commands progress from equal −50 mm/s wheels to roughly left −57/right −42 while wheel heading continues changing negatively. The drift was not arrested by the commanded trim; these logs alone do not establish the mechanical or control cause.

For the latest attempt, integrating gravity-projected iPhone gyro rates over the surrounding received health samples gives approximately −9.17° over 6.91 seconds. This independently supports actual turning and suggests the drift rejection was not solely a bad tag reading. No motor/encoder remapping or automatic gain change was inferred from this short run.

GroundHog repeatedly changes tracking continuity during the reverse, with invalid tracking and insufficient-agreement reason 7 packets. It recovers while stopped. A single uninterrupted cumulative iPhone displacement cannot be constructed across those gaps. Widening calibration acceptance therefore helps the experiment progress, but does not certify a continuous iPhone trajectory. The new dashboard makes the continuity, fit quality and unavailable state visible.

Applied the requested doubled geometric acceptance (heading/drift ±0.30 rad, lateral ±200 mm, return discrepancy 400 mm and expanded 100–1600 mm range). The new web console provides command discovery, scan images/reports and GroundHog diagnostics. Speeds and physical hazard checks remain unchanged. No live drive was triggered during analysis or the simulated browser tests.
