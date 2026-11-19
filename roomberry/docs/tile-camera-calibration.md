<!-- @(#)tile-camera-calibration.md 3.2.calibration.4 2026/11/12 21:20:00 -->
# Tile-grid camera calibration

The local autonomy configuration now uses the measured **pinhole** fit from
the 50-image run with retakes. At 820×616 it is fx715.940499, fy711.317621,
cx415.587714, cy294.939691 pixels, with 0.561px fitting RMS. The configuration
stores these at the existing 1296×972 reference resolution: fx1131.535227,
fy1122.403778, cx656.831313, cy465.391850. Runtime scales x and y separately.
Source: output/camera-calibration-20261112-retakes/models.json, model pinhole.
The radial2 candidate remains an offline fit: the current pose estimator has
no distortion correction. Its intrinsics must be used with its distortion
model in a future runtime change. Actual print dimensions remain unverified.
This configuration edit does not deploy to or restart the Pi.

Use the 4-column, 3-row tag16h5 sheet with IDs 0–11. Nominal black-square
width is 41.91 mm; horizontal centre pitch 66.801 mm, vertical 67.31 mm.
Measure the actual print in both directions and mount it flat. Its IDs overlap
mapped landmarks: keep navigation idle and stop the Roomberry service before
opening the camera with this standalone script. No automatic robot motion occurs.

## Coordinate convention and tile survey

Measure several grout-centre to grout-centre intervals and divide by their count.
One nominal foot is 304.8 mm; tile size plus grout may differ. Use the measured
pitch with --tile-mm. Check both directions; this script assumes a square grid.
For unequal pitches, enter coordinates scaled to the selected pitch or record
the actual survey in notes. Grout lines are placement references, not precision
ground truth or a replacement for the printed calibration board.

Origin: floor projection of the board centre onto its plane. x is distance out
from the board plane; y is left while facing the board; z is height above floor.
Record the Pi lens optical centre, not the bumper or wheel centre. Positive yaw
turns left from facing perpendicular to the board; positive pitch points up.
Angles are measured estimates, not inferred from the tiles. This is a local
survey frame, separate from the navigation map's room coordinates.

Mark grid intersections with tape and label their coordinates relative to the
origin. If the board plane lies between grout lines, measure that offset rather
than rounding it to a tile. The current mount is approximately 148 mm forward
of the axle centre and 137 mm above floor; check rather than assuming these.
At yaw zero the lens is 148 mm closer to the board than the axle. For other
headings project that offset along both horizontal axes, or measure the lens
projection directly with a plumb reference.

## Ranges and capture sequence

All ranges below are perpendicular lens-to-board-plane distance, not bumper
distance or slant range. Start at 2 tiles; try 1.5 tiles only after checking
framing. The whole sheet and a margin must fit and all tags should be sharp.
If the fixed board is above the lens and clips at close range, back away.
The closest useful distance is set by field of view, board height and focus;
there is no confirmed universal minimum for this camera.

| x tiles | Lens distance | Purpose |
|---|---|---|
| 1.5 | 457 mm | Optional closest view if the whole board fits |
| 2 | 610 mm | Starting close view; strong corner sampling |
| 3 | 914 mm | Main calibration views |
| 4 | 1219 mm | Main calibration and checks |
| 6 | 1829 mm | Midrange validation |
| 8 | 2438 mm | Longer-range validation |
| 10 | 3048 mm | Optional detection/range limit check |

1. At x=2,3,4 tiles capture y=-1,0,+1 tile where space and framing permit.
   Aim the camera toward the board at side positions; record the actual yaw.
   Approximate aiming yaw is -atan2(y,x). Take two stationary shots per pose.
2. Add modest heading variations to place the board near the left and right
   image boundaries, keeping every corner in frame. Wait for vibration to stop.
3. For a full lens calibration, add about 10–15 views with the board temporarily
   held at different heights and tilted 15–30 degrees about horizontal and
   vertical axes. Keep the camera mounted. Record these as notes such as
   "board moved; intrinsic-only"; their positions are not fixed-board validation
   measurements. Floor positions alone provide poor vertical/tilt diversity.
4. Restore the board to its surveyed position. Reserve x=3,6,8 and optionally
   10-tile centred shots as held-out validation, not fitting images. Measure
   actual positions with a tape for these checks. Compare estimated translation
   in the board frame against measured lens position after calibration.

Aim for 25–40 varied fitting views plus held-out shots. Duplicate shots check
repeatability; they do not add geometric diversity. At 820-pixel width, the
placeholder focal length predicts roughly 44,29,22,15,11,9 pixels per tag at
2,3,4,6,8,10 tiles respectively. These are planning estimates, not measured
optics. Tags near 10 pixels across are weak calibration evidence. Prefer close,
sharp views for fitting; use distant views to establish the practical limit.

## Capture on the Pi

Use the Pi's system Python with Picamera2 and Pillow installed. If needed:

```sh
sudo apt install python3-picamera2 python3-pil
sudo systemctl stop roomberry.service
python3 roomberry/tools/capture_camera_calibration.py --output ~/camera-calibration --gray
```

Run from the repository root; adjust the script path if copied separately.
Stop navigation before stopping the service; leave Rosie stationary throughout.
The script uses the same still configuration, 820×616 BGR888 stream and
queue=False as current navigation. Do not refocus the lens between captures.
If the camera supports autofocus, keep its focus setting consistent with
navigation; the script records returned LensPosition metadata when available
but does not change focus controls. Inspect that value for unwanted changes.

Example interactive entries (replace heights and yaw with measured values):

```text
2,0,137,0,0,centred close
3,1,137,-18.4,0,left station aimed at board
6,0,137,0,0,holdout measured with tape
q
```

Or create a CSV plan with this exact header and launch with --plan positions.csv:

```csv
x_tiles,y_tiles,z_mm,yaw_deg,pitch_deg,note
2,0,137,0,0,centred close
3,1,137,-18.4,0,left station aimed at board
6,0,137,0,0,holdout
```

Each planned row waits for Enter after manual placement. Use --tile-mm 306.0
if that is the measured pitch. Quote notes containing commas using CSV rules.

Original colour images are lossless PNGs. --gray adds a derived grayscale PNG;
retain colour originals so grayscale processing can be reproduced. No threshold,
contrast enhancement, resizing or annotations are applied. The original PNG
embeds a RoomberryCalibration JSON text field; a matching .json sidecar retains
the coordinates, camera configuration and request exposure/sensor metadata.
captures.csv is the editable index. Local coordinates are not GPS and are not
written into EXIF GPS fields. If correcting metadata later, keep the CSV and
JSON consistent; embedded PNG metadata is the original capture record.

When finished, review a few PNGs at 100% zoom before collecting everything.
Restart roomberry.service only after restoring tag 15 and clearing the board
from navigation views. This capture tool does not fit calibration or update
autonomy.json. The subsequent fit must include distortion and use the same
camera mode; runtime pose estimation must then apply that distortion model.
