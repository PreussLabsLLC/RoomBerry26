<!-- @(#)grout-run-1-20261104-review.md 3.1.grid.1 2026/11/04 10:00:00 -->
# Grout run 1 investigation

Run: November 4, 2026, 09:45:51–09:45:59 local time.

The robot stopped because GridRunner reported an invalid line detection. Wheel
odometry settled at −485.7 mm (1.59 ft), consistent with the observed distance.
Motion commands began at 09:45:51.416; the mission stopped at 09:45:59.652.

## Evidence

- Last valid phone packet: sequence 2473, received 09:45:59.432, flags 3,
  reason 0, confidence 0.873. Scanline x positions were 0.1405 and 0.1572.
- First invalid packet: sequence 2474, received 09:45:59.533, flags 2,
  reason 1 (detector found no acceptable unambiguous line). Sequence 2475
  repeated this at 09:45:59.638. Invalid detections continued after stopping.
- Frames remained fresh: send minus capture time approximately 70 ms.
  Health packets continued at approximately 10 Hz; bump count stayed 8
  through the stop. Roomba bumper and hard-hazard flags were clear.
- Pi logged `line lost, stopped, or line/phone telemetry stale`; the raw
  packets resolve that generic message to loss of valid line detection.
- Start: offset −27.9 mm, angle +1.26°, scanline x 0.2355/0.2480.
  Last commanded sample: offset −33.0 mm, angle +2.01°, x 0.1405/0.1572.
  The line did not converge to the robot centerline during this short run.
- Actual packet settings: height 85 mm, lens left −13 mm, gain 2.0,
  correction limit 0.25. Final commanded wheels were left −59/right −40
  mm/s; settled wheel heading was −0.98° relative to the start.

## Interpretation and next change

Phone resources during the active interval (82 valid health packets): app CPU
25.39–27.63%, median 26.72%, where 100% equals one CPU core; app physical
footprint constant at 14,500,464 bytes (13.83 MiB). Thermal state remained
nominal (0), battery 100%. Resource readings update approximately once per
second; repeated packets are not independent measurements. All 83 recorded
line packets in the interval carried distinct frame timestamps; frame age at
send was 67.95–69.80 ms (median 68.82 ms). These are app metrics, not total
device CPU or system memory pressure. No evidence of resource overload.

For detector improvement, aggregate nearby parallel image rows into narrow
bands and robustly fit the same grout stripe across multiple longitudinal
positions. Current code already averages a 3×3 neighborhood and tries three
row positions around each of two nominal scanlines; it does not jointly fit
all these rows. More samples may improve noise rejection and bridge a locally
poor row, but cannot recover a stripe excluded by the x search boundary.
Avoid averaging across separate parallel grout stripes or across a transverse
intersection; reject inconsistent samples and retain confidence checks.

The strongest explanation is loss at the detector's left search boundary.
`GridLine.hits` searches only x in [width/8, 7*width/8), rejecting dark runs
that touch a search edge. Immediately before loss, the upper scanline's
detected center was only 1.55% of image width inside that left boundary.
A finite-width stripe can therefore be rejected before its center reaches
12.5%. This is consistent with the observed progressive movement leftward.

The binary log contains detections, not camera pixels or rejected candidates;
it cannot prove edge clipping versus an ambiguous/low-contrast candidate.
Nor does this run establish why steering failed to center the line: geometry,
mount calibration, actual wheel response and detector behavior need separate
validation. Do not infer a steering sign fix from these data alone.

Recommended next work: widen the detector search region with appropriate
image-edge handling, add explicit detector rejection reasons and separate Pi
stop diagnostics, then validate geometry and steering against recorded camera
frames or a stationary alignment test. Preserve immediate braking on invalid
detection. The log confirms −13 mm lens-left configuration; verify that value
against the physical mount (GroundHog previously used −23 mm).

Sources: roomberry/logs/roomberry.log; NavLink recording
roomberry-navlink-20261104-094541-0000.bin; sensor recording
roomberry-sensors-20261104-094541.csv; GridLine.swift, GridCamera.swift and
roomberry_gridrunner.py. Analysis only; no control code changed.
