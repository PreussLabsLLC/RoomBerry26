<!-- @(#)report.md 3.2.timing.1 2026/11/12 12:57:01 -->
# Pi3 versus Zero W scan timing

Measurements are from stationary820x616captures/detection, not full-resolution
benchmarks. Pi3run20261112-122222has13scans; warm statistics exclude the first.
Source camera timings are preserved in scan-evidence.txt and metrics.json.

## Same half-second cool-offs

| Timing | Zero W run20261110-135820 | Pi3run20261112-122222 |
|---|---:|---:|
| First scan |16.23s|4.48s|
| Warm median |6.58s|2.97s|
| Warm range |6.03–7.22s|2.86–3.05s|

Warm scans2.21times faster (55%shorter); first scan3.62times faster. Zero W
figures are retained in output/roundtrip-halfgap-20261110-135820/report.md.

## Stage detail

The older Zero W poster run20261110-125752 predates added cool-offs. Its
stage medians are documented in roomberry/docs/tag-scan-pipeline.md; use it
for stage comparison, not an identical total-duration comparison.

| Stage, warm median | Zero W poster run | Pi3 |
|---|---:|---:|
| Pause/guard/feedback |0.14s|0.086s|
| Settling |1.01s|1.000s|
| Capture |0.09s|0.020s|
| Detector call |2.85s|0.303s|
| JPEG archive |0.69s|0.037s|
| Added cool-offs |none|1.500s|
| Total |5.00s|2.974s|

Detector call is about9.4times faster; native detection median on Pi3is0.267s.
Pi3first detector call1.616s includes startup/IPC; total4.483s. Stage medians
do not necessarily sum to the median total. Hardware is not the only changed
variable: bindings/native estimator/runtime versions also changed after the
migration. These are observed end-to-end system gains, not a pure CPU benchmark.
No sensor poll/write faults occurred in this Pi3run.

## Higher-resolution next step

A measured experiment at1296x972capture and detection is reasonable. It uses
2.49times the pixels. Rough linear extrapolation puts warm detection near0.75s
and total around3.5–4s with current waits. This is an estimate, not a benchmark;
scene complexity, threading, copies and preprocessing can change scaling.
The detector subprocess has a10second response timeout including cold startup.

Suggested camera values for a staged test (not applied by this report):

```json
"highest_resolution": false,
"capture_resolution": [1296, 972],
"max_dimension": 1296
```

Raising capture alone while leaving max_dimension820 retains detection at the
old pixel dimensions. highest_resolution=true requests the sensor's full native
size, which is a much larger, currently unbenchmarked step. The current configured
intrinsics are illustrative at1296x972and scaled for other sizes; real camera
calibration is still needed. More pixels may improve corner/pose precision and
distant reads but do not fix inaccurate intrinsics, phone AR drift, surveyed
landmarks, wheel slip or geometric inconsistencies. The existing maximum range
filter still applies independently of read quality. No settings changed here.
