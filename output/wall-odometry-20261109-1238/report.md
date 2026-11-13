<!-- @(#)report.md 3.2 2026/11/09 13:35:55 -->
# Wheel/iPhone disagreement and next-run changes


## Mount correction notice

The operator subsequently confirmed a different mount: lens10mm forward and180mm
left, looking20° left and15° up. The exploratory plots below used the old
clip-mount lever arm and are **not a correctly mounted robot-centre comparison**.
Their numerical separation is conditional on that obsolete assumption. Preserve
them as analysis history; use the next run’s fixed tag16 alignment and newly
recorded mount metadata for the requested comparison.


[Plot PNG](disagreement.png) · [PDF](disagreement.pdf) · [CSV](disagreement.csv)
· [metrics](metrics.json) · reproducible [analysis](analyze.py).

The12:38 run supplies1677 type6 pose packets;1669 normal/fresh frames enter the
comparison. Wheel pose integrates recorded cumulative distance and heading with
midpoint differential-drive kinematics. Phone frame timestamps are mapped onto
the Pi epoch using the minimum receipt-minus-phone-send uptime offset for this
session, then wheel poses are interpolated at phone capture times. A short,
early0.2m departure aligns arbitrary survey XY yaw and translation. No full-run
alignment or scale fitting hides subsequent drift. Heading comparison removes
only the initial heading offset, independently of the positional alignment.

**The final relative separation is1.31m**, with a maximum1.31m before the abort.
The phone heading change is9.16° less than the encoder heading change at the
end; the largest absolute difference is14.28°. Using the uncorrected camera
trajectory instead gives1.42m final separation. The corrected comparison uses
the configured phone lens offset(-145,-22)mm as an assumption; it has not been
independently verified for RoomTrek. Clock/network latency, short-baseline yaw
alignment, camera-versus-robot origin, AR scale/drift and wheel slip all remain
uncertainties. **These are disagreements, not ground-truth error measurements.**
Median phone feature count was3; normal AR tracking does not establish room-map
accuracy. A fresh, close tag15 fix is useful independent validation.

## Low-speed evidence

Encoder velocities use signed16-bit count deltas, the235mm wheelbase and the
same wheel-size adjustment as the recorded controller. Statistics include
commands unchanged for at least0.5seconds; accelerations/stops are excluded.

| Command | Left median | Right median |
| --- | ---: | ---: |
|30mm/s|41.73mm/s|39.30mm/s|
|35mm/s|39.88mm/s|39.88mm/s|

This supports the observed poor low-speed command response. It does not isolate
firmware regulation from encoder quantization, sampling or physical wheel slip,
and encoders measure wheel rotation rather than body speed. The new commanded
floor is50mm/s, cruise80mm/s; hardware behavior at those settings is untested.

## Implemented for the next run

- Moving wheels use at least50mm/s, and wall following cruises at80mm/s with
  existing bounded steering. Hazard/lease/contact and no-progress guards remain.
- A new-command direction baseline excludes pre-reverse coast from wrong-way
  detection. The next fresh increments still trigger on genuine opposite travel.
- The target is a fresh, agreeing tag15 validation within300mm robot-centre
  range. Wheel proximity or a5m checkpoint only starts the validation process;
  it cannot declare success. Park/face/scan, then at most100mm forward steps
  between rescans if a stable tag fix says farther away. Twelve steps/180s bound
  closing; whole-run8m/360s limits abort without a validation-success claim.
- Add16 Australian speech phrases (32 total) for major wall/tag/map stages.
  Important confirmations may supersede queued chatter; they cannot supersede
  higher-priority safety speech.

Pi uploads and the physical trial remain with the operator. No robot commands,
Pi deployment or iPhone app changes were performed for these control updates.
The phone still supplies diagnostic Surveyor data; it is not automatically fused
into wall steering. Existing automatic survey/map-save behavior remains.

For the Pi, upload `roomberry_wall.py`, `roomberry_speech.py`,
`roomberry_trek_survey.py`, and `roomberry_web.py`, then restart Roomberry.
No iPhone app update is required for these new speech strings or Pi controls.
