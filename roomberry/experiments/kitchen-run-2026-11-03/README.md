<!-- @(#)README.md 3.1.groundtruth.1 2026/11/03 18:00:00 -->
# Reproduce the kitchen experiment

Read [analysis.md](analysis.md) for findings and limitations. The original movie
is an unchanged local input; its size and SHA-256 are recorded in provenance.json.
Its embedded location metadata is not copied into the generated video-metadata.json.

From the repository root:

```sh
.venv/bin/python roomberry/experiments/kitchen-run-2026-11-03/analyze.py
.venv/bin/python roomberry/experiments/kitchen-run-2026-11-03/report.py
```

Requirements: ffmpeg/ffprobe, numpy, Pillow and matplotlib. OpenCV is not
required. Decoded frames are cached under `/tmp/roomberry-kitchen-0917-frames`;
remove that cache or use a different path if the movie changes. Each requested
frame time is approximate to the decoded frame cadence. Use the original movie
matching provenance.json, not a recut/transcoded copy.

`analyze.py` reads the explicit grid and reviewed body bounds in annotations.json.
It produces grid-check.png, calibration.json, video-measurements.json, and three
video-review contact sheets. One initial grid intersection covered by the phone
is excluded. The homography is fitted only to independently labelled floor
intersections, not telemetry or assumed robot motion. An initial door/floor
line is annotated separately. Body centers are transformed conic centers of the
reviewed outline ellipses. They are deliberately named floor projections rather
than height-corrected physical robot poses.

Static-floor translation is estimated from 64×64-pixel patches at grid locations
using phase correlation, retaining peaks above 0.15 within ±10 pixels, then taking
the median shift. This removes the observed small image drift. It does not fit
framewise scale, rotation or a new camera model. Framewise retained-patch count
and scatter are in video-measurements.json. No trajectory is generated for the
unobserved interval.

`report.py` reads application-extract.json if present. On its first run, it
extracts checkpoints, motion samples and relevant event lines from the current
roomberry/logs/roomberry.log and checks the expected session identity. The archive
allows reproduction after that mutable application log is replaced. It also
reads the timestamped sensor CSV and binary NavLink log in roomberry/logs.

Wheel poses are reconstructed from recorded signed distance and wheel-angle
increments, using midpoint heading. The baseline readings are stationary and
zero. Wheel path sums absolute distance increments; its kinematics do not
measure sideways slip. GroundHog segment transforms are referenced to the exact
logged anchor packet; its cumulative path comes from the transmitted tally.

Synchronization fits one constant video time origin and a nuisance longitudinal
scale to both visible legs, with a fixed observed initial image position.
**That scale is not applied to video coordinates.** It is not independent wheel
calibration. The search is ±2 s around the stream creation timestamp, at 0.01 s
steps. Clock skew is not estimated over this three-minute clip. Phone capture
proxies subtract source frame age from Pi receipt time, leaving network-delay
uncertainty. Times in the application log and source metadata are PST (UTC-08).

## measurements.csv

Rows combine a 0.1 s video-time grid with the exact reviewed frame times and
application event times. There are 1794 rows and 13 video observations.

- `video_s`, `pi_epoch_s`, `elapsed_from_run_start_s`: aligned time coordinates.
- `phase`, `event`: commanded-state interpretation, not visual proof of hidden
  movement or precise physical contact onset.
- `wheel_*`: center estimate in the start frame; longitudinal positive toward
  carpet and lateral positive initially left; heading zero at the start.
- `wheel_signed_distance_mm`: original signed wheel distance, negative reversing.
- `command_*`: latest sensor-observed applied commands, held between polls;
  these are requested velocities, not measured wheel velocity. During the
  post-stop polling pause these columns can retain the last nonzero observation;
  the application log confirms the actual stop separately.
- `physical_bump_*`: previous sampled flags, not interpolated fractional flags.
- `cliff_*_signal`: downward reflectance telemetry, not direct grout detections.
- `groundhog_*`: analogous local estimate; position/path are linearly interpolated
  only between usable packets within 0.5 s. Frame-end ID is from the nearest
  actual packet, while interpolated position need not equal that packet's pose.
  Before the start, path-minus-anchor can be slightly negative: that is a
  relative counter offset, not negative physical travel.
- `video_measurement_available`: 1 only at one of the 13 reviewed image times.
- `video_rim_projection_*`: elevated-body floor projections relative to the
  initial projection. Blank elsewhere, including all of 54–136 s.
- `video_screen_axis_proxy_deg`: unvalidated phone-screen orientation proxy;
  not physical body-heading ground truth and not used for conclusions.
- `video_body_pixel_*`, `camera_shift_*`: original annotation center and the
  applied image-registration translation at measured frames.

Interpolation is not extrapolated or used across larger source gaps. Some
telemetry fields are blank near completion because a sensor poll interval
straddles the stop. Summary path values alone allow up to 1.25 s phase-boundary
interpolation to span that polling pause; position checkpoints remain the logged
application observations. These small endpoint/path sampling differences are
not evidence of slip.

`summary.json` includes phase metrics, timing-fit sensitivity, visible-segment
comparisons and tracking counts. Phase path and pose differences have different
sample/capture timing; neither six-decimal CSV output nor rounded millimetres
imply that precision in physical truth. Sparse video polyline lengths sum chords
only inside reviewed visible blocks. They do not bridge the missing interval;
with measurement error they are not strict mathematical lower bounds on true
physical path length.

`trajectory.png` / `.pdf` overlays wheel and phone paths with green video
projection points. No connecting video curve is drawn through the gap. Lateral
scale is magnified. The video uses grout axes, while telemetry uses initial body
heading; intermediate lateral differences include unknown initial alignment.
No robot-control module is imported or executed by these scripts.
