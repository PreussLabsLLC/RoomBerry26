<!-- @(#)roomtrek-alignment.md 3.2.tag15.1 2026/11/12 15:23:38 -->
# Fixed tag16 alignment for the next RoomTrek run

The qualified initial tag16 scan supplies the robot's room-frame XY position
and heading. The Pi pairs the actual tag capture time with nearby normal
RoomTrek frames and fixes one planar transform for that run. No later path,
scale, tag15 correction or disagreement is fitted back into the phone alignment.
This is room-frame alignment, not a new measurement of the physical mount.

`autonomy.json` now includes:

```json
"roomtrek_alignment": {
  "enabled": true,
  "heading_basis": "optical_forward",
  "mount_yaw_deg": 0.0,
  "mount_pitch_deg": 20.0,
  "lens_x_mm": -66.0,
  "lens_y_mm": -58.0
}
```

A different phone mount was installed on2026/11/12 at14:37. The active
lens is **66mm back and58mm right** of the Roomba centre (robot X forward,
Y left). Its optical axis looks approximately **straight forward and20° upward**.

The heading offset is additive camera-to-body yaw, so camera optical heading
plus0° gives robot heading. The optical direction is obtained from quaternion
camera−Z and projected onto the horizontal plane; the upward pitch therefore
does not become an extra planar yaw rotation. Pitch20° is retained in anchor
metadata. This is planar alignment on a roughly level floor; camera height and
AR scale are not estimated.

The old93.6° camera+Y correction and rear lens offset(−145,−22)mm do **not** apply
to this mount. Historical records retain their original heading basis and
extrinsics for reproducibility. New anchors record `optical_forward` and the
new measurements. Legacy type1 `phone_position` soft aiding is disabled in
`autonomy.json` so its old mount calibration cannot be applied accidentally;
RoomTrek type6 remains diagnostic-only.

At the accepted tag16 capture:

1. Convert tag capture epoch to Pi monotonic time, preserving capture time
   despite delayed AprilTag processing.
2. Pair the closest normal phone frame within250ms. Require at least3 frames
   spanning150ms, with camera movement≤20mm and projected heading variation≤2°.
   Reject poor tracking, old frames and near-vertical optical-axis projections.
3. Rotate the survey plane into the room using the tag robot heading and mount
   yaw; align camera position to the tag robot pose plus the rotated lens offset.
4. For each later frame, apply that same rotation/translation at scale1, then
   subtract the lens offset using the aligned heading to recover robot centre.
   Pivoting therefore does not become an artificial camera-to-body translation.

The NavLink receiver keeps a bounded600-frame history (about60s at10Hz) solely
for capture pairing, separate from unchanged binary recording and legacy fusion.
Phone uptime uses the minimum receive-minus-send monotonic offset; this assumes
clock rates stay stable over the short run and one-way network latency is small.
A phone session/map change or wheel-odometry epoch reset invalidates the binding;
it cannot re-anchor during that run. A tracking/freshness gap suspends comparisons
and later normal frames resume the same transform. Missing/unstable history at
the initial capture is logged as unavailable; a new run is needed to bind again.

## Independent comparison

A separate wheel trace starts at the same tag16 robot pose and integrates only
wheel distance/angle increments. It is not reset by the tag15 navigation/validation
corrections. This allows an honest drift comparison after the run. Neither
phone nor wheel disagreement feeds steering or alters the existing localizer.
Unexpected diagnostic errors disable this comparison and are logged without
interrupting robot control.

The run log contains:

- `RoomTrek tag16 alignment:` with session, fixed transform, lens/mount values,
  tag capture time, paired phone frame and wheel baseline.
- `RoomTrek anchored comparison:` with timestamped independent robot-centre
  estimates, XY separation and heading difference (one per observed new phone
  frame at the mission update cadence).
- Alignment state/missing-data/reset messages. `/status.json` also exposes
  `wall.last.phone_alignment_state` and `phone_separation_mm` when available.

The binary log still contains the original10Hz camera poses. Live comparison
samples can differ by one frame in time; the offline plot interpolates the raw
wheel stream at phone frame times for a closer comparison.

## After the next run

Collect the complete Roomberry log, NavLink binary and matching sensor CSV.
On the development Mac (NumPy/matplotlib available in the project venv), run:

```sh
.venv/bin/python roomberry/tools/plot-trek-anchor.py \
  --log roomberry/logs/roomberry.log \
  --navlink roomberry/logs/navlink/roomberry-navlink-<run>.bin \
  --sensors roomberry/logs/sensors/roomberry-sensors-<run>.csv \
  --out output/tag16-comparison-<run>
```

It selects the matching recorded tag16 anchor, interpolates wheel samples at
phone capture times, and produces PNG/PDF plots, CSV and metrics in room
coordinates. There is **no early-departure/full-path fit or scale adjustment**.
It rejects unmatched files, missing anchors and significant epoch-clock jumps.
Initial mismatch is removed by the common stationary anchor; later disagreement
remains visible. Absolute accuracy still needs independent tag/physical checks.

Upload to the Pi: `roomberry.py`, `roomberry_mission.py`, `roomberry_wall.py`,
`roomberry_navlink.py`, new `roomberry_trek_anchor.py`, and updated `autonomy.json`.
Restart Roomberry after uploading all matching modules. No iPhone update or
new UDP port is required; keep the existing Pi-controlled Surveyor workflow.
The plot tool runs locally and need not be deployed on the Pi. Pi uploads remain
with the operator.

When Surveyor resumes a saved map, tag16 binding additionally requires the
nonzero-map type6 pose to carry the valid flag and localized state. Normal
tracking before relocalization completes cannot establish a fixed alignment.
Fresh zero-map Surveyor telemetry keeps its existing qualification.

With the survey coordinator enabled, WALL now waits for its successful AR
startup before requesting tag16. Failed binding can retry with fresh captures
within the startup deadline; it cannot release departure. The latest phone
frame must still match the acknowledged session and selected map. Once driving,
comparison values remain diagnostic and do not feed steering or refit alignment.

## Pi camera mount (remeasured 2026-11-12)

The Pi camera lens is148mm forward of the Roomba centre, centred laterally,
and137mm above the floor. Its forward-facing axis convention is retained.
`camera_from_robot` maps body Xforward,Yleft,Zup into camera Xright,Ydown,
Zforward. Since this matrix transforms robot coordinates into camera
coordinates, its translation is minus the rotated camera position:

```json
"camera_from_robot": [
  [0, -1, 0, 0],
  [0, 0, -1, 0.137],
  [1, 0, 0, -0.148],
  [0, 0, 0, 1]
]
```

Restart Roomberry after syncing autonomy.json, then begin a new run with a
stationary tag16 scan to bind the new mount values. No iPhone app rebuild is
required. The iPhone pitch is20degrees for the replacement mount.
Historical analysis should use the mount values recorded for that run; rerunning
old analysis scripts against the new config changes their calibration baseline.

## Tag15 centre grout reference (2026-11-12 15:23)

Tag15 was physically moved to room Y1225mm on the centre grout line, to
provide an easier distance reference for camera/wheel alignment measurements.
Its configured centre is now X7730mm,Y1225mm,Z160mm, facing room-X. Only Y
changed; tag16 remains at its surveyed position. Sync autonomy.json and restart
Roomberry before the next test. Earlier recordings/replay configs retain the
previous tag15position; do not reinterpret them with this new survey coordinate.
