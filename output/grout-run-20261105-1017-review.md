<!-- @(#)grout-run-20261105-1017-review.md 3.1.grout.16 2026/11/05 -->
# 10:17 run review

Sources: roomberry.log, session 20261105-101653. Statistics below describe
mission samples (roughly 5 Hz), not every phone camera frame.

## Threshold and impacts

Phone bump detector remained active. At 10:18:00.333/.533 event 5 peaked at
5337.313 mm/s² (.544 g), recorded only under .6 g cutoff, around 4668–4679 mm
outbound encoder displacement. At 10:18:06.595 event 6 peaked at 14374.503
mm/s² (1.466 g), ignored because its estimated occurrence was 38.84 ms after
a [-30,-30] -> [0,0] wheel change. This may be the user's phone tap; logs
cannot identify its physical source. The robot resumed low-speed motion and
aborted at 10:18:08.617 on 5000 mm travel limit, not a reacted phone impact.
10:18:08.249 sustained right motor current .48 A was report-only.

## Phone grout tracking

Outbound 218/291 samples locked (74.9%), 73 slow. Median confidence .978,
frame age132 ms, maximum215 ms. Visible-line target error median+3.9 mm,
range-2.0 to+11.1 mm. Sustained line loss started10:17:56.858 at4526 mm;
continued11.56 seconds and approximately468 encoder mm through final sample.
Near the threshold the phone had fresh packets but usually no stripe detection.
Wheel slip means this encoder displacement is not reliable floor travel.

Return208/214 samples locked(97.2%),6 slow. Medianconfidence .987, age117 ms,
max184 ms. Visible-line error median-4.7 mm, range-10.8 to-.5 mm. Maximum
reported loss .428s. No mission-sample frame exceeded250ms in either leg.

## Tag scans

All seven scans detected a strong tag15. Initial3.917m detection margin60.4,
hamming0 was not accepted as reliable mapped localization. Return used retained
pose. Six subsequent checkpoint attempts at ranges1.311/1.302m,
.878/.877m,.462/.462m had margins117–130,hamming0,low pose errors.
Firstfour rejected for position discrepancy>500mm; finaltwo for inconsistency
with lastfix+wheel motion(468/465mm position,~7.1/6.5deg heading innovation).
Thus failed checkpoint feedback did not mean the camera failed to read tag15.
Slipping wheels provide a plausible source of odometry bias, not proof.
At final bumper contact10:20:25.214, retained estimate still563mm fromtag,
so mission aborted unsafe contact instead of declaring arrival.

## Recommended next policy

Use a distinct outbound threshold-approach window beginning about4000mm:
restore lower phone-event reaction sensitivity there and disable transient
suppression in that window. Preserve .6g elsewhere. A .5g approach cutoff
would catch this .544g event; .25g restores original phone-event sensitivity.
Do not reset counter baselines and discard pending events when arming.
Review retained-pose confidence after slip and allow stationary repeated strong
fixes to confirm relocation rather than blindly increasing innovation limits.
No control code or deployment changed in this review.
