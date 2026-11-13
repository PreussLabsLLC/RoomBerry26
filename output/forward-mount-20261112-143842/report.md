<!-- @(#)report.md 3.2.analysis.7 2026/11/12 14:57:59 -->
# Forward-facing phone mount round trip

Run20261112-143842; phone mount lens(-66,-58)mm,yaw0,pitch20deg is confirmed
in the live tag16 anchor. One fresh session5731packets, all normal tracking,
no sequence gaps. Median3visible features (minimum1,p95=26).
Initial capture pairing34.5ms; stationary checks passed. Second initial tag16
scan35.98seconds later repeats pose within0.6mm; phone error2mm/0.20deg at
that scan. Use the final tag16 AFTER tag15 as the return reference; the extra
initial tag16 must not be mistaken for trip completion.

## Position and heading against tag checkpoints

| Checkpoint | Phone position error | Wheel position error | Phone heading error | Wheel heading error |
|---|---:|---:|---:|---:|
| Tag15,14:42:09 |1274mm|459mm|-10.39deg|-3.12deg|
| Final close tag15,14:44:26 |1351mm|445mm|-11.29deg|-3.38deg|
| Returning tag16,14:47:24 |371mm|356mm|-4.81deg|+2.75deg|

One initial tag16 alignment,unit scale,fixed mount/lens offset. No later
trajectory fitting or corrections applied to independent phone/wheel tracks.
Tag references are surveyed-camera estimates, not external motion capture.
Final tag16 itself82.5mm/-4.50deg from initial. Wheel travel8.888m.
Phone/wheel heading disagreement p958.16deg,max8.80deg; previous angled-mount
recording p9513.31deg,max33.31deg. Final wheel error improves from925mm/-9.75deg
to356mm/+2.75deg; phone final error increases from175mm to371mm. These are
different physical runs/calibrations, not a controlled mount-only experiment.

## Remaining translation issue

The straight-facing mount improves directional alignment but the phone still
reports much less outbound translation than the wheel/tag references. At final
tag15 its position error is1.35m, despite normal tracking throughout. Independent
phone/wheel separation peaks1.673m. No additional angular correction or arbitrary
scale change was made to hide this discrepancy.

For16forward500mm steering steps, paired actual remote-mode start/result times
show phone endpoint displacement29–82%of wheel advance,median57%. Endpoints use
recorded frame time and mount-corrected robot centre. These are not16independent
truth measurements: wheel slip can affect encoder distance, and phone motion
can drift. The nonconstant ratios do not justify one fixed AR-scale correction.
Tag15checks also place the phone substantially short of the estimated room
position. Low feature counts may contribute, but logs do not prove causation.

Next useful test: a taped, straight1m movement with start/end ground marks,
good textured view, and stationary tag scans. Compare physical distance,
encoders and phone displacement before further geometry/scale adjustment.
Three visual features and normal tracking status do not establish metric accuracy.

## Scans, serial, safety and battery

Twelve scans and twelve scan-result speech completions. First4.502s;
warm median2.973s; median detector0.319s. Current820x616capture,500msgaps.
One startup serial write timeout14:38:43.926, before first tag scan. No later
poll failures or scan-associated write timeouts in this recording.

Tag15arrival again rejected: final robot-centre range382mm exceeds300mm.
Spoken camera range25cm has a different origin. Earlier1.318m clear tag read
was excluded by localization range filtering. Battery99.3→96.7%.

Metrics, straight-step table, raw scan evidence, config snapshot, plots and map
preview accompany this report. No runtime or calibration changes.
