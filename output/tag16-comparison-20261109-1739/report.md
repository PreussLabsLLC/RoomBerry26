<!-- @(#)report.md 3.2 2026/11/09 17:55:38 -->
# 17:39 run — recording, audio and tag15 disagreement

User clarification: “a shove” meant commanding **Return to tag15**, not physically
pushing/lifting/sliding Rosie. All analysed motion is commanded wheel motion;
no external-motion explanation is assumed for the odometry error.

## Arrival and stops

- WALL starts17:39:29.700; survey starts17:39:30.719. Qualified tag16 alignment
  succeeds17:39:47.868, capture/frame pairing23.27ms.
- Bypass bound starts lucky scan17:41:38.419. Two consistent tag15 fixes found
 17:41:48.412 at1486mm centre range. Five bounded100mm advances follow.
- WALL stops17:43:59.759 for unsafe/stale/unavailable Roomba sensors. Pi I/O
  reports one failure and max3107ms polling time; mission max3621ms. This is
  observable Pi sensor latency, not evidence that the iPhone stopped tracking.
- WALL map save verified17:44:03.148. Return to tag15 starts17:44:30.328 with
  a **new iPhone survey session**. Do not stitch that session into the original
  tag16 phone frame. Return map save verified17:45:56.543.
- Two final validation captures17:45:47.830 and17:45:52.635 give354.8/355.0mm
  centre range, agreeing0.48mm/0.075degrees. Raw Pi-camera range248.3mm differs
  because the camera is ahead of the centre. Repetition shows precision, not
  independent proof of camera/tag calibration accuracy.
- Controller stops17:45:55.719 explicitly “tag15 validation outside300mm”. The
  measured centre was55mm outside the requested goal. No final success claimed.

## Disagreements

| Reference/check | Position | Heading |
|---|---:|---:|
| Wheels vs iPhone at WALL stop |1124mm|8.16deg|
| Wheels vs iPhone at last aligned frame |1123mm|8.17deg|
| Maximum aligned wheel/iPhone separation |1126mm|maximum abs11.20deg|
| Pure wheels vs final tag15 measurement |735mm|10.45deg|
| Return controller correction at final validation |88mm|0.82deg|

Independent wheel trace integrates every recorded sensor sample from tag16,
without later tag corrections, path fitting or scale fitting. At final tag15
measurement it predicted(7582,137)mm; tag measured(7379,844)mm. Thus wheels were
203mm too far alongX and707mm too lowY. This is accumulated drift across the
whole run, distinct from the recently corrected return controller's88mm error.
At the earlier distant WALL tag15 fix, wheels differed794mm and phone1638mm
from the tag-derived pose; treat distant camera calibration/pose accuracy as a
limit, not either odometry source as truth. Saved-map quality is unvalidated.

The16:33 run ended with about760mm wheel/phone disagreement; this WALL session
reached1124mm. It was a longer/different run, so this is not a controlled
before/after quality comparison.

## Map discontinuity

The map is a corrected navigation trail, not a pure wheel or iPhone trace.
Between stationary scans17:43:26.893 and17:43:32.293, global pose changes from
(6529,438)mm, unlocalized and still based on tag16, to(6456,963)mm, localized on
tag15: about530mm. That is a landmark correction of accumulated drift. It does
not indicate a break in UDP recording. The local WALL checkpoint solver can
accept distant tag15 before the normal global1.2m gate, explaining why seeing
an early tag does not immediately update the global display. Later return
corrections include74.5mm,32.0mm and88.0mm at tag checks. The map renderer joins
successive accepted positions, so a correction can appear as a kink/jump;
the final aborted validation can leave its previous wheel point displayed.

## iPhone load and silent audio

WALL session2723packets:2716normal/7initializing (99.74%normal), zero missing
sequence numbers. Median frame age67ms,95th89ms,max204ms, median sample interval
100ms, maximum receive gap516ms. Return session848packets:842normal/6initializing,
zero missing sequences; median age65ms,95th97ms,max176ms. Normal-frame feature
counts WALL min0/median5/max107; return0/3/31. Feature counts alone do not grade
map quality. These samples do not show a tracking/telemetry stall.

Read-only downloaded iPhone event log confirms35heartbeat attempts and40speech
completed callbacks over the collected run window, with no heartbeat audio
setup errors. Pi also receives speech completions throughout. This verifies
software activity, not audible speaker output: no audio route/volume, thermal
state, CPU load or physical speaker measurement was recorded. Thus overload
is unproven and silence is unresolved; volume/output routing or audio-session
behavior remain possibilities. Do not equate dancing feature dots or speech
completion with an audible or accurate recording. Two world maps and telemetry
were saved; RoomTrek does not record camera video.

## Artifacts and reproduction

- disagreement.png/pdf/csv and metrics.json: original fixed tag16 wheel/iPhone
  comparison, WALL session only. Generated with roomberry/tools/plot-trek-anchor.py.
- tag-checks.png/pdf/json: pure wheel trace through return, tag15 measurements
  and local controller corrections. Reproduce with analyze-run.py from repo root.
- iphone-events.jsonl: filtered downloaded iPhone events for this run.

No app/control/config changes, installation, robot movement or Pi upload made
while analysing. Source logs preserved; plot inspection and timestamp/session/
epoch/SCCS/whitespace checks completed. No code regression suite needed.
