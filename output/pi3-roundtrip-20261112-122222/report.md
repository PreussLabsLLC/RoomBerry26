<!-- @(#)report.md 3.2.analysis.6 2026/11/12 12:38:39 -->
# Pi3 kitchen round trip, 2026-11-12 12:22–12:31

## Result

Phone normal tracking continued after four initialization packets. No packet
sequence gaps within the active fresh session (4991packets). Earlier223packets
belonged to a different loaded-map session and were excluded from the comparison.
The room-aligned wheel trace and iPhone trace use the initial stationary tag16
capture only; no later tag corrections or fitted scale affect the reported errors.
Stationary pairing checks passed. Wheel travel between first/final tag16:9.444m.

| Capture | iPhone/tag position error | Free wheel/tag position error | iPhone/tag heading | Wheel/tag heading |
|---|---:|---:|---:|---:|
| Final close tag15,12:27:51 |1145mm|241mm|-11.72deg|-24.95deg|
| Returning tag16,12:30:25 |175mm|925mm|-5.25deg|-9.75deg|

Final tag16 pose differs from initial by86mm and+0.10deg. Phone displacement
from aligned start199mm, wheel891mm. These are estimates relative to tags,
not an external surveyed trajectory. Independent wheel trace deliberately does
not snap to subsequent tag fixes; the navigation pose can move separately.

## Return turns

Two clean mostly stationary left-turn intervals were compared on matching wall
clock windows, using the phone optical heading and encoder heading:

| Interval | Wheel rotation | Phone rotation | Difference |
|---|---:|---:|---:|
|12:28:15–12:28:36|131.15deg|128.73deg|2.42deg|
|12:28:42.8–12:28:54|74.20deg|72.74deg|1.46deg|

Wheel centre travel during these windows20.8mm/13.0mm; the overall turn was
split by a forward movement. These are actual measured rotations, not sums of
requested15degree button targets. Results do not support attributing the whole
position disagreement to a large wheel-heading failure at the return turn.

## Mount calibration sensitivity

Active configuration roomtrek_alignment means lens10mm FORWARD,180mm LEFT;
robot coordinates Xforward,Yleft. The optical axis is assumed20deg left;
mount_yaw_deg=-20 is the additive camera-to-body correction. Pitch15deg is
metadata; the horizontal optical projection determines planar heading.
The legacy phone_position block (-145,-22mm,93.6deg) is disabled and is not
used for these type6trails. Calibration applies to the active rear lens, not
phone body centre, and does not alter raw ARKit translation or tracking state.

Accepted tag15 checks show phone errors943–1146mm. Diagnostic fits only:
- Changing translation-plane rotation alone improves tag15RMS1050→847mm;
  optimum+11.25deg corresponds to mount_yaw-31.25deg. This does not solve it.
- A fitted similarity would need scale1.299 plus11.25deg to reduce residual
  to177mm. This is not a measured calibration and can conceal AR drift,
  surveyed-tag error or camera calibration error. Do not apply as a correction.
- Holding rotation fixed and fitting lens offset alone requires lens
  (-775,326)mm, i.e.775mm behind the robot centre, with196mm residual. This
  is not physically plausible for this mount and excludes a modest lens-offset
  typo as the sole explanation. Suppressing the current180mm offset changes
  the model by at most361mm over any rotation; reversing left/right gives a
  bound721mm. These bounds assume the same initial tag16 alignment and yaw.

The outbound phone displacement near tag15 is substantially shorter than
corresponding tag displacement; initial yaw/offset adjustments alone cannot
establish which source is correct. Need physical mount measurements and an
independent measured straight travel/rotation test before changing configuration.
A phone AR tracking state of normal is not a metric accuracy guarantee.

## Scan performance and other events

All13scan announcements completed. Scan duration2.859–4.483s, median2.976s;
median detector call0.304s. Half-second gaps active. No serial poll failure or
write timeout within this service run; older errors in the concatenated log
were excluded by the12:22:22run boundary. Battery97.8→95.5%.

At12:25:56 a RIGHT BUMPER contact caused safety stop and aborted the first
homing attempt; subsequent manual requests were refused while safety was not
ready. Later tag15 validation stopped at379mm versus300mm required. The early
1.343m tag15read was clear at detector level but rejected by the navigation
range filter; detector quality and localization acceptance are separate.

No runtime/configuration changes. Analysis script, metrics, calibration
sensitivity, CSV tables and plots accompany this report. Initial tag16 live
anchor is recorded, so offline comparison can be checked against live metadata.
