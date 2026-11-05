# RoomBerry phone mount review — November 4, 2026

Updated `groundhog-mount-measurements.svg` and its PNG preview describe the
GroundHog/GridRunner mount with the phone camera on the robot's rear-left,
looking down. The AYI carton and its forward-looking camera are rough layout
symbols based on `RoomBerry.svg` and the project-root `RoomBerry26b.png` photo.
The latter contains HEIC data despite its .png extension; the original is
unchanged. The supplied `GridRunner.png` screenshot is also unchanged.

## Geometry and scale

The top and side views share 2 SVG drawing units per millimetre. Zooming or
printing changes the physical print scale, so use the 100 mm scale bar.

- Body diameter 348 mm and drive-wheel center spacing 235 mm use current
  project geometry assumptions (174 mm radius and the driver wheel base).
- Phone outline uses Apple's nominal iPhone X dimensions, 143.6 × 70.9 × 7.7 mm:
  [Apple technical specifications](https://support.apple.com/en-gb/111864).
  Case dimensions and individual lens-to-phone-edge distances are unmeasured.
- Lens forward −200 mm and lens height 85 mm reproduce the screenshot's
  settings. They are not newly measured distances.
- The lens's physical lateral distance is **unknown**. The drawing illustrates
  **+13 mm** only to show the rear-left placement with the same magnitude as
  the screenshot's current −13 setting. This is not a measured replacement
  calibration. Remeasure to the active lens, not the phone's center or edge.
- Carton size/location and the robot's side profile are illustrative. No carton
  dimensions or robot-body height are inferred as measured from the photo.
- The active camera is under the phone; its top-view red marker is a projected
  location, not a camera visible on the upward-facing screen.

## Settings discrepancy

GridRunner's screenshot shows height 85 mm, physical top-edge angle 180°,
lens forward −200 mm, lens left −13 mm, steering gain 2 and correction cap 0.25.
In `GridLine.robotPoint`, the mount offsets are added in robot coordinates:
forward is +X and left is +Y. A **rear-left** lens therefore requires a negative
forward offset and a **positive** left offset. The screenshot's −13 mm instead
models a lens 13 mm to the robot's right. If the physical lens really is 13 mm
left, changing −13 to +13 would shift the modeled floor points by +26 mm in
robot-left coordinates. That alone does not establish the cause of the observed
10 mm tracking error or establish the correct magnitude.

For the reverse outbound trip, left in the direction of travel is the robot's
right. Keep that distinction when comparing a floor offset with phone settings.
The phone top-edge angle refers to the physical notch/camera end; it is
independent of the screen's landscape UI orientation.

Historical GroundHog settings were recorded as lens-left −23 mm; GridRunner
currently shows −13 mm. Neither negative value matches a physical rear-left
lens under the current robot coordinate convention. Do not reuse one app's
saved calibration in the other without checking the actual mount.

No app settings, code, or robot calibration were changed as part of this diagram
update. To regenerate both assets from their geometry and annotations:

```sh
.venv/bin/python output/groundhog-mount/build_mount_diagram.py
```
