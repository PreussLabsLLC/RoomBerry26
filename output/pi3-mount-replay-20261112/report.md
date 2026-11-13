<!-- @(#)report.md 3.2.mount.2 2026/11/12 12:53:19 -->
# Replayed map with remeasured camera mounts

Offline replay of recorded run20261112-122222. No new robot run, trajectory
fitting, AR scale change, navigation changes or live Pi modification.

- Old phone lens(10,180)mm/yaw-20deg → measured(-21,202)mm/yaw-30deg.
- Pi camera centre(125,0,160)mm → measured(148,0,137)mm in robot coordinates.
- Recomputed the three logged idle tag robot poses from their full camera/tag
  rotations and translations, surveyed landmarks and new camera_from_robot.
  Other navigation-only tag poses were not reconstructed without full matrices.
- Rebound the same initial capture with new extrinsics; transformed recorded
  iPhone displacement without fitting, including camera lens/body offset.
  The fixed-alignment orientation changes the translated path by+10deg.
  Reanchored free wheel integration at the revised initial tag16 pose.
- map.png is the updated preview; map-before.png preserves old measurements.
  comparison.png/PDF show the same before/after tracks and robot scan poses.
  Black scan crosses are robot positions derived from tags, not tag locations.
  The previous run's map.png link was updated, retaining
  map-before-remeasurement.png beside it. Original metrics/CSV remain unchanged.

| Captured reference | Phone error before | Phone error after | Wheel before | Wheel after |
|---|---:|---:|---:|---:|
| Midway tag15 scan12:26:44 |1029mm|782mm|297mm|332mm|
| Final tag16 scan12:30:25 |175mm|157mm|925mm|926mm|

The Pi camera changes shift these tag-derived positions by25–27mm. They do
not materially change heading because the camera rotation is unchanged.
The wheel trajectory shape therefore stays the same. The phone's outbound
lateral bias improves visibly, but the remaining position discrepancy is not
eliminated. This replay does not establish whether remaining error is AR scale/
drift, wheel slip, camera intrinsics, tag placement, mount yaw or their combination.

## How accurate do the measurements need to be?

- Measure the active lens relative to the wheel/robot centre; Xforward,Yleft,
  and height from the floor. Phone centre or holder edges are different points.
- A small lens-offset error creates a bounded, orientation-dependent position
  error. With initial-only alignment its contribution can reach twice the
  offset error after a180degree turn;10mm offset uncertainty gives at most20mm.
  This particular phone-offset revision has magnitude38mm, bound76mm.
- Direction matters more over distance: a fixed yaw error rotates the translated
  path. At4m displacement,1degree is about70mm,5degrees about349mm,10degrees
  about697mm. These are geometric sensitivities, not measured residual causes.
- A practical start is lens positions within5–10mm and optical direction within
 1–2degrees, followed by an independently measured straight-distance test.
  Existing camera intrinsics remain illustrative, so precise mount measurements
  alone cannot guarantee precise tag distances/positions.
- Restart the Pi with the new config and take a fresh stationary tag16 scan for
  live results. Existing running trail history is not retroactively recalibrated.
