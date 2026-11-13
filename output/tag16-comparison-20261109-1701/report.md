<!-- @(#)report.md 3.2 2026/11/09 17:13:08 -->
# 17:01 run — tag15 arrival and disagreement

The run includes automatic WALL, manual remote steering, calibration, and a
mapped tag15 return. Distances below refer to the robot centre, except raw
camera ranges explicitly labelled as such.

| Check | Result |
|---|---:|
| First confirmed return tag15 fix (capture17:07:29.812) | 859mm from tag15 |
| Last confirmed tag15 fix (capture17:07:59.428) | 646mm from tag15 |
| Last controller estimate (17:08:23.171) | 133mm from tag15 |
| Wheel-only error at first confirmed fix | 448mm /6.77degrees |
| Wheel-only error at last confirmed fix | 528mm /7.06degrees |
| Local controller correction at final confirmed fix | 58.3mm /0.30degrees |

**Arrival qualification:** 133mm is a wheel-projected estimate after the last
scan, not a final measured tag fix. No scan verifies the final300mm goal.
The return controller stopped17:08:23.373 with “tag return final approach
exceeded its bounded travel”. Only about524mm accumulated after the final fix,
so the750mm travel branch was not exhausted; the same guard also stops when
estimated centre range falls below124mm (174mm robot radius minus50mm).
The last logged estimate was133mm immediately before that guard triggered.
Do not interpret this as a completed final validation scan.

**Independent wheel check:** integrate every sensor sample from the tag16
capture at17:02:06.339, including manual wheel movements, using the recorded
tag16 robot pose and fixed heading. Do not apply later tag corrections or fit
a scale/trajectory. At the last confirmed tag15 capture, wheels predicted
(7287,355)mm versus measured robot pose(7086,843)mm: wheels were201mm too far
along roomX and488mm too low in roomY. The heading discrepancy was7.06degrees.
The two final stationary scans agree within7.2mm and0.53degrees. Absolute
accuracy still depends on surveyed tags and the Pi camera calibration.
Any unrecorded lifting/sliding of the robot would affect this interpretation.

**iPhone comparison unavailable:** at WALL start, SESSION_STOP failed “App must
be foreground”; at tag16, alignment reported no normal frame within250ms.
First recorded type6 telemetry arrives17:05:54.680, after WALL ended17:04:43.933
on its wall-loss search limit (4883mm wheel path,11contact recoveries).
There are728 type6 packets across six new sessions. Final session has596packets:
553normal,6initializing and37limited by insufficient features. Normal-frame
feature count min0 /median2 /max3. Save attempts fail “Insufficient features”.
Session resets prevent stitching coordinates into a tag16-anchored comparison.
No retrospective alignment or wheel/iPhone disagreement number is invented.

Files: run-analysis.png/pdf show pure wheel trace, independent tag15 errors,
and final iPhone feature count. tag15-wheel-check.csv and analysis.json contain
numbers. analyze-1701.py reproduces the exports from the supplied local logs.
No robot/app/config changes or deployment performed.
