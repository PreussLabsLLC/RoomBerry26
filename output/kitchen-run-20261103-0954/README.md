<!-- @(#)README.md 3.1.plot.1 2026/11/03 10:15:00 -->
# Kitchen run plots

[kitchen-run.png](kitchen-run.png) shows wheel and GroundHog local trajectories,
with separate reverse/return line styles, phone impacts, and two coincident
floor-IR dips. Its second panel shows distance against elapsed time.
The lateral axis is in millimetres and the longitudinal axis in metres, so
lateral differences are visually magnified. No overhead position truth is used.

[floor-ir.png](floor-ir.png) shows all four raw downward cliff-IR reflectance
channels, their local medians, and the candidate-detection score. These are
floor-facing IR signals, not the forward light-bumper or docking IR channels.
Both figures also have vector PDF versions for zooming and export.

## Event interpretation

- Phone bump 8: 75.31 s, 0.49 g, threshold stop/turnaround.
- Phone bump 9: 111.50 s, 0.63 g, return abort.
- IR dip candidate: 51.26 s, 3.0575 m signed wheel distance from start,
  front-right and right signals.
- IR dip candidate: 92.45 s, 3.6910 m signed wheel distance from start,
  front-left and front-right signals.

Bump timestamps are first Pi receipt of the incremented phone counter, not
synchronized impact-capture times; mission reaction occurs later. Wheel and
phone positions at event times are linearly interpolated. The stopped distance
of ~2.46 m comes from the sensor CSV after settling; plotted pose paths end at
the last mission motion sample before abort (~2.49 m wheel distance).

## IR method and limits

For each signal, subtract it from a centred 2.5-second local median, then divide
by 1.4826 times the median absolute deviation of those residuals (minimum scale
1 raw unit). Take the second-largest score across the four sensors, requiring
at least two channels to show a coincident downward excursion. Keep local
maxima above 2.5 robust noise units, suppressing weaker peaks within 0.8 seconds.
This is an exploratory heuristic, not a validated grout detector or a
statistical confidence level. The two reported scores are 2.84 and 3.29.

There is no clean, repeating 304.8 mm pattern in these traces. The two dips may
reflect grout, floor texture or robot-height changes; lack of a detection does
not imply lack of a grout crossing. Sensor positions relative to the robot
reference and the grout-grid phase have not been surveyed. The plotted marker
positions are robot estimates, not exact floor locations under each IR sensor.
The algorithm can miss staggered dips as different sensors cross a line at
different times, and it does not identify intersections of two grout lines.
Do not count these markers as verified tile intersections or calibrate scale
from them. Use overhead video to confirm which, if any, are actual crossings.

## Reproduce

From the repository root, run:

```sh
.venv/bin/python output/kitchen-run-20261103-0954/plot_run.py
```

Requires numpy and matplotlib (installed in the project virtual environment).
Inputs: the timestamped 095424 sensor CSV, previously extracted 0954 metrics
JSON, and the archived motion-samples.json in this folder. On first execution
only, the script extracts motion samples from roomberry/logs/roomberry.log.
Outputs: two PNGs, two PDFs, and events.csv. No robot settings were changed.
