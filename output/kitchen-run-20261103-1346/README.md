<!-- @(#)README.md 3.1.analysis.1 2026/11/03 14:00:00 -->
# Complete kitchen calibration, November 3 at 13:46

The full out-and-back completed in **158.93 seconds** with uninterrupted
GroundHog tracking. The return endpoint is approximately **233 mm right of the
starting line in the phone estimate**, and **193 mm right in wheel odometry**.
Both estimates end facing close to the starting direction. The displacement
accumulated while travelling; restoring heading did not recover lateral position.

[Trajectory, heading and steering plot](drift-analysis.png) ·
[Vector PDF](drift-analysis.pdf) · [Metrics](metrics.json)

## Route and endpoints

Coordinates are local to the manually aligned start: +X initially forward,
+Y robot-left. Negative Y is right of the original line. Figures below are
stop-command checkpoints, not overhead truth.

| Checkpoint | Time | Signed wheel distance | Wheel X / Y | Phone X / Y | Wheel / phone heading |
|---|---|---:|---:|---:|---:|
| Start | 13:46:35.279 | 0 mm | 0 / 0 mm | 0 / 0 mm | 0 / 0° |
| Threshold | 13:47:54.032 | -4583 mm | -4580 / -52 mm | -4423 / -100 mm | +2.17 / +1.36° |
| Finish | 13:49:14.214 | -9.6 mm | -9 / -193 mm | -36 / -233 mm | -0.33 / +0.12° |

Outbound elapsed time was 78.75 s; turnaround-to-finish was 80.18 s including
the hold. The reverse contact produced the only new in-run phone bump, count
0→1, peak **4617 mm/s² (0.47 g)**. It correctly triggered the threshold
turnaround before the 5000 mm wheel-distance limit. There was no return bump
or calibration abort and no tag scan.

Final displacement magnitude was 194 mm (wheels) and 236 mm (phone). Their
endpoint estimates differ by 48 mm, predominantly lateral (39 mm). Subsequent
phone observations settle near (-32, -233) mm. The sensor CSV settles at signed
wheel distance -0.7 mm: the longitudinal stop was close to its wheel target,
while the lateral error remained. Completion within wheel-distance tolerance
is not a guarantee of returning to the original physical point.

## Why the drift accumulated

| Measurement | Reverse | Return |
|---|---:|---:|
| Phone lateral displacement | -100 mm | additional -133 mm |
| Wheel lateral displacement | -52 mm | additional -141 mm |
| Distance-weighted phone heading | +0.76° | -2.24° |
| Distance-weighted wheel heading | +0.66° | -1.75° |
| Maximum absolute phone heading | 3.67° | 4.84° |
| Maximum absolute wheel heading | 3.90° | 4.44° |
| Mean steering command | +0.054 | +0.157 |
| Peak absolute steering | 0.256 | 0.338 |
| Samples at the 0.35 steering cap | 0 | 0 |

The heading plot shows repeated oscillations around a biased mean, particularly
on return, rather than unbounded yaw growth. During reverse, a positive
heading produces negative lateral travel because distance is negative. During
forward return, a negative heading also produces negative lateral travel.
Thus the two legs add rightward displacement rather than cancel it.

The controller in roomberry_calibration.py uses heading error only:
`error = -phone_heading`, proportional gain 4.0 and steering cap 0.35 with
the reverse sign correction. It does not use lateral position, and it has no
integral term to cancel persistent steering bias. Steering signs are consistent
with correcting heading in both directions. Nonetheless, the return retains
an average negative heading while receiving a sustained positive correction.
This is consistent with residual drive/response bias under proportional control;
the log alone does not isolate its mechanical, low-speed motor-control, timing
or dynamic cause. The 0.338 peak approaches the cap, and the existing oscillation
makes an indiscriminate gain increase a poor next experiment.

For scale, a 2° heading offset over 4.4 m creates about 154 mm lateral travel.
Integrating phone longitudinal steps against its contemporaneous heading
predicts about -58 mm lateral change outbound and -173 mm returning. Those sum
to -231 mm, close to the -233 mm phone endpoint. Per-leg differences (~-41 and
+40 mm) nearly cancel and are consistent with roughly a 0.5° constant mismatch
between translation axes and reported heading. That is a diagnostic hint for
mount/geometry review, not proof of a mount-angle error or an explanation for
the whole return offset. The wheel heading/translation match is expected
because wheel poses are constructed by integrating those same wheel headings.

These observations support a substantial physical path deviation, consistent
with the user's observation, rather than a pure phone-position discontinuity.
The two estimates are not fully independent: the phone heading steers the robot,
and both estimates have unverified calibration. Overhead video or an endpoint
measurement is still the independent reference.

## Tracking and sensor health

- **1590/1590 motion reports valid**, one session/calibration and continuity 0.
- Zero rejected-frame increments and zero missing motion packet sequences.
- 4768 accepted-frame increments, approximately **30.0 accepted frames/s**.
- Processing median **27.93 ms**, max 34.71 ms; median frame age at send
  88.6 ms, max 110.2 ms. The latter is phone-local freshness, not synchronized
  end-to-end latency.
- Candidate count min/median 333/439; inliers 323/435. Fit RMS median 0.086 mm,
  max 1.277 mm. Residual describes internal fit consistency, not absolute accuracy.
- CPU median 55.9%, battery 78→74%, thermal nominal throughout, 480×640 images.
- No active-run physical bumper, wheel drop, hard hazard or wheel-overcurrent
  flags. Left/right wheel current medians 0.106/0.105 A, maxima 0.375/0.293 A.
- Roomba voltage minimum 13.888 V (lower than the morning run), with no
  associated motion abort. These logs do not establish a battery cause for drift.

Both physical bumper switches appear asserted in the first post-completion
sensor record at **13:49:15.115**, about 0.90 s after the finish checkpoint.
Applied wheel commands are zero then. That contact did not end the calibration,
and the log cannot establish whether it was contact while settling or subsequent
handling. The lateral offset is already present before it.

## Comparison and scale limitations

Compared with the earlier iPhone X run, tracking is again healthy, and the
return now completes without the separate impact that stopped the earlier run.
The user has identified a grain of rice as that earlier disturbance and cleaned
the path. Today's full run therefore supplies the missing endpoint measurement.

Threshold wheel travel is 4583 mm versus 4564 mm earlier (19 mm, 0.4% difference).
Phone X travel is 4423 versus 4349 mm. In this run the phone is 157 mm shorter
longitudinally than the wheel estimate at threshold (~3.4%), with 47 mm lateral
separation. Neither repeatability nor uninterrupted tracking certifies either
estimate's scale. The two out-and-back endpoint errors also cannot establish
scale because systematic forward/reverse scale errors may cancel.

If the robot-reference displacement to threshold is independently confirmed
as exactly 4799 mm, this checkpoint would imply a wheel factor about 1.047 and
phone longitudinal factor about 1.085. Initial stand-off, phone contact geometry,
actual threshold distance and stop settling must be checked before applying
such factors. The phone still reports **85 mm lens height** and the same mount
calibration identity as the morning run; physical measurement has not been
confirmed by these logs.

The signed wheel speed inferred during cruise is about 59 mm/s despite the
50 mm/s nominal command. For the return cruise window, the applied command
averages approximately left 41 / right 58 mm/s, while average wheel yaw rate is
near zero. These are closed-loop, sampled observations, not a controlled motor
transfer measurement. They flag a command-versus-encoder response discrepancy
worth checking with a short fixed-command trial; they do not establish a speed
floor, wheel defect, or a new calibration factor.

## Recommended next step

Keep the reliable iPhone X and 50 mm/s setting. Measure the final sideways
offset against the grout line and check the overhead video to anchor the
estimated 19–23 cm drift. Confirm the X's lens height and mount offsets.

For the next control change, target the original line explicitly: a bounded
lateral-error correction can request a small heading toward that line, with
correct handling of reverse motion. Review damping and persistent steering
bias at the same time; a bounded, anti-windup heading integral is one possible
way to reduce steady bias, but would need validation alongside the existing
oscillation. Do not simply raise heading gain or relax safety limits. No
controller, calibration factor, impact threshold or robot configuration was
changed for this analysis.

## Artifacts and reproduction

The PNG/PDF includes the wheel and phone paths, heading traces, per-leg mean
heading and steering commands. Lateral scale is magnified; these are estimated
local paths. Recreate it from the repository root with:

```sh
.venv/bin/python output/kitchen-run-20261103-1346/plot_run.py
```

The script reads archived motion-samples.json and metrics.json in this folder
and requires numpy/matplotlib. Metrics were extracted from:

- roomberry/logs/roomberry.log, calibration 13:46:35–13:49:14.
- roomberry/logs/sensors/roomberry-sensors-20261103-134454.csv.
- roomberry/logs/navlink/roomberry-navlink-20261103-134454-0000.bin.

Phone/Pi clocks are unsynchronized. Packet health is selected by Pi receipt
time; poses use arrival freshness. Distance-weighted headings use absolute
longitudinal increments between logged pose samples; heading-based lateral
predictions sum `dx * tan(midpoint_heading)` over those intervals. They are
descriptive diagnostics, not independent accuracy estimates.
