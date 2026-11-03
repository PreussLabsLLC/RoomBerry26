<!-- @(#)overhead-ground-truth.md 3.1.threshold.2 2026/11/03 09:20:00 -->
# Overhead ground truth from the tile grid

The kitchen floor is a metric reference: 1 ft (304.8 mm nominal) tiles with
dark grout lines. A phone fixed above the run sees both the grid and the robot,
so the grid supplies the scale and the phone supplies the trajectory. Nothing on
the robot has to be trusted while the reference is being recorded.

This is the reference used to answer two questions:

1. Is the wheel odometry scale correct?
2. Do AprilTag poses agree with where the robot actually is?

## What you need

- A phone or camera that records 4K at 30 or 60 fps. The iPhone 11 Pro is fine.
- A mount that keeps the camera still for the whole run: tripod, ladder,
  shelf, or a plank clamped to two cabinets. Any camera motion corrupts the
  reference.
- Two matte colour patches for the robot: red at the front, green at the rear.
  Matte paper or vinyl, not glossy tape. About 40–60 mm square is plenty from
  2.4 m.
- A tape measure for the tile pitch and the marker spacing.

## Camera setup

- Height 2.2–2.5 m, looking straight down at the floor.
- Wide lens, no digital zoom. Keep the whole driving rectangle inside the
  central ~70 % of the frame; phone lenses distort badly at the edges and a
  homography cannot correct radial distortion.
- Lock focus and exposure if the camera app allows it. Autofocus hunting
  changes the effective focal length between frames.
- Record 4K. At 2.4 m and a 1× lens, 4K gives roughly 1–2 mm per pixel; 1080p
  is 4–8 mm per pixel and is not good enough for a 1 % check.
- Turn off electronic stabilisation. It moves the image between frames.

## Marker rig

Tape the two patches to a flat card on top of the Roomba so both are visible
from above and neither is shadowed by the other. Put the red patch at the front.

Measure the centre-to-centre distance with the tape or calipers and write it
down. The tracker reports the measured baseline in every frame; if it drifts or
disagrees with the tape by more than a few millimetres, the homography or the
marker detection is wrong.

The reported robot position is the midpoint of the two marker centres, and the
reported heading points from the green (rear) marker to the red (front) marker.
Put the midpoint over the robot's reference point if you want absolute
positions; for pure distance and leg measurements a constant offset cancels.

Keep the markers away from the Pi camera and the AprilTag so they cannot
occlude a scan.

## Recording protocol

1. Start the overhead recording.
2. Clap, or flash a light at the camera, to mark the start. This gives a
   fallback visual sync point if the speed correlation is ambiguous.
3. Let the robot sit still for about a second.
4. Manually align the robot at tag 15 facing the tag, along the grout line.
   Calibration does not scan or verify this placement.
5. Start GroundHog tracking and start calibration with Clock or the web control.
   The robot captures a stationary local baseline, reverses at up to 50 mm/s until a new iPhone bump or the
   5000 mm wheel-distance limit, stops for one second, then drives forward to its starting
   wheel distance and stops. There are no tag scans, intermediate stops, turns,
   or bumper approaches. The endpoint tolerance is 15 mm; actual return position
   remains a measurement to check against the video.
6. Stop the recording after the robot finishes.

The carpet threshold is about 15.75 tiles (4799 mm) from the aligned start.
The default reverse travel limit is **5000 mm**. A new iPhone bump ends the
reverse leg immediately, regardless of peak strength; after the hold the robot
returns to its starting wheel distance. Existing bump counts do not trigger it.
The same event may refine its peak without triggering another stop. New return-leg
impacts retain the existing peak-based stop policy; physical bumper contact
always aborts. A bump marks a candidate threshold, not a verified world position.
Use the LED flashlight for tracking and verify the endpoint against the video.
`ROOMBERRY_CALIBRATION_DISTANCE_MM` overrides the limit (100–5000 mm).
Remove an older 1850 mm environment override to use the new default.
Restart the robot process after changing its environment. The optional
`ROOMBERRY_CALIBRATION_HOLD_S` sets the far-end hold (default 1 second, range 0–30).
The calibration status reports both configured values.

Timer-driven camera captures and tag scans are currently disabled globally;
`snapshot_interval` no longer schedules scans. Explicit scan requests remain
available outside calibration. During calibration, Clock cancels the active
run; release and press Clock again to start a fresh run from the current
position. Realign at tag 15 before restarting if the robot has moved.

GroundHog relative heading drives a proportional steering correction (gain 4.0,
limit 0.35). Wheel distance controls the endpoints; wheel and GroundHog positions
remain separate estimates in a local frame with the origin at the start and +X
along the initial robot heading. No world/tag position is inferred. GroundHog
tracking loss or continuity changes abort the run, as do physical hazards and
heading drift above 0.30 rad in either estimate. Clock cancels the run.

`Calibration sample` JSON log entries record wall and monotonic times, wheel
pose, GroundHog pose and frame sequence, heading error, steering, and wheel
velocity commands during travel. `Calibration checkpoint` entries include the turnaround reason (phone bump or
distance limit) and mark start, turnaround, and finish for alignment with the overhead recording. The initial
heading gain and steering limit require validation on the physical floor.


Do not turn during the calibration run. Turns add wheel scrub that contaminates
the scale estimate. Run the whole sequence twice: once at 4K/30 and once at
4K/60, and compare. If the two disagree by more than 0.5 %, something in the
setup moved.

The Pi sensor CSV and the video have no shared clock. The tool aligns them by
cross-correlating their speed profiles, so a constant offset in either is fine.
The clap/flash is only needed when the motion has several similar bursts.

## Step 1: extract a frame and calibrate the grid

```bash
cd roomberry
../.venv/bin/python tools/overhead-track.py frame \
    --video ~/Movies/run.mov --time 1.0 --width 1920 --output run-frame.png

../.venv/bin/python tools/overhead-track.py calibrate \
    --frame run-frame.png --span 6 4 --output run-grid.json
```

`--span 6 4` means the rectangle you click is six tiles across and four tiles
down. In the calibration window:

- click the four intersections **clockwise**, starting at the top-left of the
  rectangle. The first click is the floor origin.
- a 6× magnifier follows the cursor. The cyan crosshair is the exact click
  point. Use it; do not eyeball the full frame.
- `u` undoes the last click, `r` resets, `s` saves, `q` quits, `m` toggles the
  magnifier.
- after the fourth click the point becomes selected and the magnifier centres
  on it. Arrow keys nudge it by 0.5 source pixels, Shift + arrows by 0.1. `[`
  and `]` switch between the four points. Nudge until the grout line sits under
  the crosshair; this is how you get repeatable sub-millimetre corners without a
  zoomed display.
- the magenta grid preview should sit on the grout lines. If it does not, the
  clicks are wrong.

For an unattended or repeatable run, pass the points directly:

```bash
... calibrate --frame run-frame.png --span 6 4 \
    --points "412 388 2211 402 2205 1826 406 1811" --output run-grid.json
```

If you are also checking the true tile pitch, measure across ten tiles with a
tape and pass `--tile-mm <measured/10>`. The nominal value is 304.8 mm.

## Step 2: verify the overlay

```bash
../.venv/bin/python tools/overhead-track.py check \
    --frame run-frame.png --grid run-grid.json --output run-grid-check.png
```

Open `run-grid-check.png`. Every magenta line must sit on a grout line, and the
cyan rings must be on the four clicked intersections. The command prints the
pixel scale (for example `3.05 mm/px`, `100 px per tile`). A tile that is only
20–30 px across cannot support a 1 % measurement; move the camera closer, use a
longer lens, or record at a higher resolution.

## Step 3: track the markers

```bash
../.venv/bin/python tools/overhead-track.py swatch --frame run-frame.png

../.venv/bin/python tools/overhead-track.py track \
    --video ~/Movies/run.mov --grid run-grid.json \
    --front red --rear green --fps 10 \
    --output run-track.csv --debug "run-debug-{index}.png" --debug-every 30
```

`swatch` lists every colour preset that found a blob, with its area and pixel
centre. Pick the two largest. If the red patch splits into several blobs (a
specular highlight or a shadow), switch to a different preset or diffuse the
lighting.

`track` prints solved and missed frames and the median marker baseline. Check
three things:

- close to 100 % solved. A 10 % miss rate biases the path length low.
- baseline spread of a few millimetres, not tens.
- the debug images show both rings on the patches.

The default `--width` for `frame` is 960 px, and `track` inherits the
calibration width from the grid file. For the real scale run, calibrate at
1920 px or 3840 px: blob centroids are quantised to whole pixels, so a 960 px
frame adds roughly 0.5 px of jitter per axis. Tracking costs about 15 ms per
frame per colour at 960 px, 55 ms at 1920 px, and 0.2 s at 4K.

Use `--roi x0,y0,x1,y1` in frame pixels to restrict detection to the driving
area if the frame contains other red or green objects.

## Step 4: compare with wheel odometry

```bash
../.venv/bin/python tools/overhead-track.py compare \
    --track run-track.csv \
    --sensors logs/sensors/roomberry-sensors-20261102-160100.csv \
    --output run-compare.json
```

The output looks like this (from a synthetic end-to-end test):

```
aligned at +0.00 s (speed correlation 1.000, 99 samples)
path    overhead   1219.2 mm   wheels   1158.2 mm   ratio 1.0526
displacement 1219.2 mm vs 1158.2 mm   ratio 1.0526
odometry scale correction = 1.0526  (multiply distance_mm)
overhead-wheels separation = +61.0 mm over 1158 mm
verdict CHECK (tolerance 1.0%)
```

How to read it:

- `path_ratio = overhead path / wheel path`. This is the factor to multiply
  `distance_mm` by. `1.05` means the wheels report 5 % less than the robot
  actually moved.
- `displacement_ratio` compares straight-line endpoints instead of path
  length. On a straight run the two ratios should agree; if they do not, the
  robot turned or the markers slipped.
- `correlation` below about 0.8 means the alignment is weak. Narrow the sensor
  window with `--sensor-start` / `--sensor-end`, or add a clap/flash.
- `verdict PASS` means the ratio is within `--tolerance` (1 % by default).

## Step 5: audit every stop-to-stop move

The calibration run stops at each scan, so the overhead track can report the
actual distance between stops:

```bash
../.venv/bin/python tools/overhead-track.py legs \
    --track run-track.csv --expected-tiles 1 --output run-legs.json
```

The output is one row per leg:

```
leg  start..end s      dur s   distance mm   tiles    dx mm    dy mm   speed mm/s
  1     0.95..  1.85    0.90       304.9   1.000   +304.9     -0.2     338.8
  2     2.75..  3.65    0.90       303.8   0.997   +303.7     +0.4     337.6
summary 2 legs: median 304.4 mm (0.999 tiles), range 1.1 mm, sd 0.5 mm
expected 1.000 tiles = 304.8 mm: ratio median 0.999, min 0.997, max 1.000
```

Use this to answer the one-tile question directly:

- If every leg is about 304.8 mm, the robot really moved one tile and the wheel
  scale is the only correction needed. Apply the `compare` ratio.
- If the legs are systematically shorter (for example 289 mm), the robot moved
  less than a tile. The scale correction must then also account for the actual
  distance, and the earlier `1.056` estimate is partly measuring the stopping
  point, not the wheel scale.
- If the legs vary by more than a few millimetres, look at wheel slip,
  direction, or a stop that the tracker merged. A brief hesitation shorter than
  `--min-stop` does not create a station.

`--speed-threshold 40` means 40 mm/s; below that the robot counts as stopped.
Raise it if tracker jitter makes a stop look like slow motion. The robot drives
at 200–300 mm/s, so there is plenty of margin.

## Acceptance criteria

Treat the wheel scale as verified only when all of these hold:

1. Forward and reverse runs give ratios within 0.5 % of each other.
2. Two frame rates or two separate recordings agree within 0.5 %.
3. The residual after applying the correction is under ~2 mm per tile
   (about 6 mm over 6 tiles).
4. The measured marker baseline agrees with the tape within 2 mm.

If forward and reverse disagree, the wheels are slipping or one direction has a
different effective radius. That is a robot problem, not a scale factor, and
must be fixed before applying any correction.

## What this reference cannot do

- It only measures the floor plane. A homography is exact for a plane and
  nothing else.
- It does not remove radial lens distortion. Keep the run in the central part
  of the frame.
- It does not measure the tag camera. The forward Pi camera still needs a
  checkerboard or AprilTag target and its own intrinsics calibration.
- It cannot see wheel slip directly; it only sees that the integrated path
  disagrees. Use forward/reverse runs, and a slow steady speed, to keep slip
  small and repeatable.

## Keeping the calibrations separate

Store three independent artifacts and do not overwrite one when the other
changes:

| Artifact | Source | Re-run when |
|---|---|---|
| `wheel_scale` | overhead tile run | wheels, tyres, or motors change |
| `camera_intrinsics` | checkerboard target | camera, lens, or resolution changes |
| `tag_landmarks` | surveyed tag poses | tags move or the floor plan changes |

Changing `fx`, `fy`, `cx`, or `cy` invalidates tag landmark positions but not
the wheel scale: the tile grid is a metric ruler independent of the camera.

## Common failure modes

- **Grid lines miss the grout.** The four clicks were not intersections of the
  same rectangle, or the span is wrong. Re-click clockwise from the top-left.
- **Track jumps by a tile.** The grid origin is off by one tile. Check the
  overlay before tracking.
- **Baseline drifts.** One patch is partly occluded or its colour is splitting.
  Narrow the ROI, change the lighting, or use a larger patch.
- **Alignment correlation is low.** The speed profile has several similar
  bursts. Trim the sensor log to the calibration run, or record a clap.
- **Path ratio changes between runs by more than 1 %.** The camera moved, the
  markers moved, or the robot slipped. Fix the setup before trusting the ratio.
