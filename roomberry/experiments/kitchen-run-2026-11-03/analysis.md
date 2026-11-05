<!-- @(#)analysis.md 3.1.groundtruth.1 2026/11/03 18:00:00 -->
# Kitchen run: video and odometry comparison

**The video independently confirms substantial rightward drift.** Its
perspective-corrected, floor-projected body-rim center finishes approximately
**253 mm right** of its initial position. GroundHog reports 233 mm right; wheel
odometry reports 193 mm right. The video number is a projection of an elevated
outline, not a fully height-corrected floor-center measurement.

The recordings identify a completed reverse/forward calibration, with healthy
tracking. The threshold stop is a **phone impact**, not an asserted Roomba
bumper switch. The available view does not establish the true full-leg travel
or an absolute odometry scale factor.

## Data and synchronization

Matched files are `IMG_0917.MOV`, application log run 13:46:35–13:49:14,
`roomberry-sensors-20261103-134454.csv`, and
`roomberry-navlink-20261103-134454-0000.bin`. The video is 178.808 s, 4291 frames,
3840×2160 encoded with portrait rotation, approximately 24 fps.

A joint temporal-origin/diagnostic-scale fit to longitudinal measurements from
both visible legs gives **video 0 ≈ 13:46:20.30 PST**. Video positions were not
rescaled to odometry. The fit RMS is 9.1 mm; offsets approximately 0.03–0.56 s
relative to the stream's 13:46:20 creation time remain within 10 mm of that RMS.
This is sensitivity to sparse measurements, not a statistical confidence
interval. The other QuickTime creation tag says 13:46:19; using it directly
would misalign the run by about 1.3 s. Frame sampling adds up to approximately
one frame (42 ms). GroundHog positions use a capture-time proxy: Pi receipt time
minus phone-reported frame age; unknown network delay remains.

| Observed/logged event | Pi time | Approx. video time |
|---|---|---:|
| Local start baseline | 13:46:35.279 | 14.98 s |
| Reverse threshold-stop checkpoint | 13:47:54.032 | 93.73 s |
| First forward command after hold | 13:47:55.224 | 94.92 s |
| Calibration complete | 13:49:14.214 | 173.91 s |
| First sensor observation of both physical bumpers | 13:49:15.116 | 174.82 s |

The application commands reverse, stop, a roughly one-second hold, forward,
and final stop (acknowledged at 13:49:14.211). There is no commanded in-place turn, 180° turnaround, or tag
scan. The threshold phone event peaks at 4617 mm/s² (0.47 g), with physical
bumper switches clear. Physical bumper contact near the door is first observed
in a later poll: last clear 13:49:14.197, first asserted 13:49:15.116. Its exact
onset is bracketed by those polls and is not proven to be after completion;
the controller recorded successful completion rather than a bumper abort.

## Displacement, path and heading are different quantities

Coordinates below use the initial robot heading: longitudinal positive toward
the carpet; lateral positive to the robot's initial left. Checkpoint poses are
at the controller's stop-command observations and can lag physical capture.
Path lengths use sensor distance increments / GroundHog's cumulative path,
interpolated at phase boundaries; millimetre rounding is not accuracy.

| Leg / estimate | Longitudinal delta | Lateral delta | Endpoint displacement magnitude | Cumulative path | Net heading change |
|---|---:|---:|---:|---:|---:|
| Reverse, wheels | +4580 mm | -52 mm | 4580 mm | 4587 mm | +2.17° |
| Reverse, GroundHog | +4423 mm | -100 mm | 4425 mm | 4439 mm | +1.36° |
| Forward return, wheels | -4571 mm | -141 mm | 4573 mm | 4595 mm | -2.49° |
| Forward return, GroundHog | -4387 mm | -133 mm | 4389 mm | 4415 mm | -1.23° |

Total cumulative travel is approximately **9182 mm wheels / 8854 mm phone**.
Small repeated corrections accumulate about 250° / 245° of absolute heading
variation respectively; these sampled variations are not a single turn.
The final pose is wheels (+9, -193) mm and phone (+36, -233) mm. Final headings
are -0.33° and +0.12°. Subsequent wheel distance settles close to zero and
phone longitudinal displacement near +32 mm; the lateral error persists.

There are **1590/1590 valid motion reports**, no rejected-frame increments,
no missing motion sequences, and one continuity segment. Median processing
is 27.9 ms. Tracking discontinuity or dropped packets do not explain this drift.
This is the historical heading-only controller run; the later proposed
line-following change is not being evaluated by this recording.

## What the video measures

Twenty visible grout intersections establish a homography at nominal 304.8 mm
pitch. Reprojection RMS is 5.7 mm; fitting alternating rows and checking the
others gives 6.3 mm RMS. These assess internal grid fit, not absolute scale.
Static floor registration finds about four pixels of horizontal image drift
by the end; the measurements compensate for its median translation.

Thirteen body-outline ellipses were visually reviewed. Their centers are
projected through the homography; `video-review-*.jpg` preserves the annotations.
There is a stationary initial observation, samples at 20–54 s and 136–178 s.
**No video positions are filled between 54 and 136 s**, or at other unmeasured
times. This is sparse measurement, not continuous automatic tracking. The
turnaround/contact is outside the available measured view.

| Visible interval | Video longitudinal change, projected | Wheel change | Phone change |
|---|---:|---:|---:|
| Outbound, 20–54 s | +2046 mm | +2042 mm (-0.2%) | +1963 mm (-4.1%) |
| Return, 136–170 s | -2057 mm | -2045 mm (-0.6%) | -1949 mm (-5.3%) |

These comparisons use unscaled video measurements. The synchronization fit
contains a nuisance scale parameter, so the small residual is not an independent
validation of wheel scale. The sampled video polylines are 2047 mm for 20–54 s
and 2268 mm for 136–178 s. They omit the hidden part of the run and curvature
between sparse observations; measurement noise can also affect their lengths.
They are not a measured full-run cumulative path.

The final video rim projection is **(+2, -253) mm** relative to its initial
projection. Its endpoint lateral measurement supports roughly quarter-metre
drift, but not an exact 253 mm physical-center error. Intermediate video
lateral coordinates follow grout axes; telemetry follows the initial body
heading. That initial alignment is not calibrated, so intermediate lateral
curve differences cannot be assigned entirely to odometry error. Heading
proxies from the phone-screen axis were unstable and are retained only as
labelled diagnostics, not trusted body-heading ground truth.

## Correct physical reference and uncertainty

For longitudinal center displacement, the appropriate reference is

**D = 4799 - d₀ - r_contact**, in millimetres,

where `d₀` is initial center-to-door distance and `r_contact` is the contact
point's reach ahead of the center in the reverse travel direction, including
heading and the actual threshold edge. Curved path length is a different
quantity. Neither offset is independently established by this video.

The front bumper faces the door during reverse. Do not automatically substitute
its radius for the rear threshold-contact geometry. If the later measured
rear lens offset (-200, -23) mm describes the unchanged physical mount, the
lens projects about 199 mm toward the threshold at the recorded heading;
**the lens location is not necessarily the contacting phone/case edge**.
Those lens offsets are not carried in these NavLink packets; the recorded
height and mount angle are 85 mm and 180°.

For illustration only, `d₀=200` and `r_contact=200` give **4399 mm**, not 4799.
That would make the outbound longitudinal wheel result about 4.1% high and the
phone about 0.6% high. These assumed offsets do not establish either correction
factor. They show why simply dividing 4799 by reported travel is invalid.

Important remaining uncertainties:

- The elevated rim is projected onto the floor. Its apparent center-to-door
  distance is only about 128 mm, less than the configured 174 mm robot radius;
  it must not be adopted directly as a measured physical center clearance.
- Manual bounds are approximate to about ±5 pixels, roughly 10 mm per center
  locally, before systematic geometry errors. No formal confidence interval
  for the corrected physical center is established.
- Nominal tile pitch and grout gap were not tape-verified. A 1% pitch error
  alone changes a 2 m measurement by 20 mm.
- No lens-distortion or rim-height correction is available. Apparent equivalent
  rim radius varies approximately 175–188 mm across reviewed frames. That
  variation warns of systematic geometry/annotation errors; it is not a
  measured robot dimension or a valid automatic height correction.

Consequently, **wheel agreement with the raw projected video does not prove
wheel accuracy**, and the phone's 4–5% shorter distance does not prove a VO
scale defect. Several-percent parallax could change that ordering. Wheel slip,
encoder scale, VO scale, and projection bias cannot be uniquely separated here.

## Recommendations

1. Keep these results as a drift and consistency check; apply no scale factor
   from this experiment alone.
2. Measure the initial center-to-door distance and the actual rear contact
   reach; record the exact contact edge. Those two measurements would make the
   4799 mm dimension useful for a whole-leg displacement check.
3. For a scale experiment within the camera view, use two surveyed floor marks,
   measured tile pitch, and a visible low marker/known-height target with
   calibrated projection. Keep the entire measured segment visible.
4. Measure the final physical lateral offset. Evaluate any subsequent
   line-following controller in a fresh recording, not against this historical
   heading-only run.

No navigation, control behavior, or deployment was changed during this
investigation. See [trajectory.png](trajectory.png), [measurements.csv](measurements.csv),
[events.csv](events.csv), and [README.md](README.md) for reproduction and field meanings.
