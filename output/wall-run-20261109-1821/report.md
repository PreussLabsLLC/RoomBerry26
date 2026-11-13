<!-- @(#)report.md 3.2 2026/11/09 18:38:31 -->
# 18:21 and18:28 runs — resume readiness and stopped-scan limits

Two WALL attempts are present. Neither validated arrival within300mm, neither
produced a qualified tag16/iPhone alignment, and no new kitchen-map revision
was saved. The existing mapped seed remains unchanged.

## First attempt

- WALL starts18:21:26.712. Pi loads seed0B2FA89D-F7EA-4002-9AC7-92C32AF1D0D5
  at18:21:27.368. Phone remains initializing/relocalizing for30seconds and fails
  at18:21:57.587; Pi then SESSION_STOPs it. On-phone normal tracking appears in
  that same final second, but no sustained normal/localized candidate was reached
  before the deadline. No automatic retry follows.
- Pi tag16 anchor completes18:21:46.288 while the phone is still relocalizing.
  Diagnostic binding rejects it. Robot departure does not wait for phone readiness:
  this asynchronous startup policy is the coordination gap exposed by the run.
- Phone frames absent18:21:57.534–18:26:16.599 (4min19s). A later app restart
  relocalizes in about2.8seconds. The Pi coordinator did not initiate that restart;
  its exact UI/CLI origin is not logged. The original anchor is not retried.
- Fourteen bumper/contact recoveries, five wall-loss searches; lucky scan starts
 18:24:03.515 at4304mm path, finds tag15 at1886mm centre range. Six100mm advances
  follow; accepted ranges1886,1816,1506,1434,1563,1472mm. They are not monotonic,
  indicating scan/pose variability rather than clean measured closure.
- Validation stops18:27:03.592 on180second limit,5022mm wheel path. Only12.24seconds
  were in approach stages; approximately168seconds were stopped for scans or
  confirmation. The last accepted1472mm range precedes the final100mm segment;
  there is no fresh final range measurement. This was not a near-goal validation.

## Second attempt

- WALL starts18:28:14.244. Pi map resume succeeds18:28:32.541, about17.4seconds,
  but tag16 was already anchored18:28:25.258. No qualified phone pairing then.
- The app session stops18:28:38 and starts again18:29:08; origin not logged by
  the Pi coordinator. That new session relocalizes in about3seconds but remains
  in limited mapping most of the rest of the attempt. Tracking and world-mapping
  status are separate: normal camera tracking can coexist with limited mapping.
- Six contact recoveries and six wall-loss searches. Lucky scan starts18:30:02.473
  at3710mm path. Four captures at the initial view find a candidate but cannot
  confirm a consistent fix. The controller requests the+10degree view.
- Turn origin200.94degrees; stop requested near209.36degrees, but subsequent
  encoder angle reaches218.55degrees (17.61degree excursion) by18:30:22.767.
  Centre translation remains about12mm, within25mm. Angular coast exceeds the
  +/-15degree envelope, so it aborts18:30:22.774 at3723mm path before the sweep
  finishes. This is pivot overshoot, not a completed scan or unsafe-limit waiver.
- SURVEY_SAVE fails18:30:23.244 because capture readiness fails; phone log shows
  mapping limited. No new revision is written; the source map is preserved.

## Low tone and phone performance

Filtered phone log records46heartbeat attempts:30attention_required and16tracking_ok.
The attention tone also means session stopped or relocalization pending; it does
not always mean camera tracking crashed. After the first timeout the Pi explicitly
paused the AR session, explaining much of the low-tone interval.

Five received sessions total2553type6 packets, with zero missing sequences within
each session. Initial resume298frames is entirely limited (8initializing,
290relocalizing). Later sessions return normal tracking. Sampled frame ages have
session medians57–85ms, maximum192ms. These packets do not show network loss or
an overloaded/stalled phone frame pipeline. CPU/thermal load is not measured.
Feature counts and dancing dots alone do not establish localization or save quality.
The app also logs61speech completions, no heartbeat audio setup errors.

## Disagreement and next corrections

No valid current-run wheel/iPhone disagreement curve can be generated: both
qualified tag16 phone bindings failed, and multiple new phone sessions appear.
Do not stitch them together or align after the fact and claim tag16 calibration.
The first attempt's tag-derived range variability also limits a simple endpoint
wheel/tag comparison. Timeline PNG/PDF and per-session metrics show the evidence.

The Pi already supports AR restart: SESSION_STOP, then SURVEY_START with map_id.
The recommended next implementation is one bounded retry after relocalization
failure, holding the robot stopped until map relocalization and tag16/phone
binding succeed. Reuse settled-turn control for the small lucky-scan pivots so
encoder coast does not consume the angular envelope. Revisit scan latency and
pose stability before raising the180second validation limit. These are proposed
changes, not applied by this report; no robot/app/config changes or deployment.

Reproduction: run analyze-run.py from repository root with the downloaded phone
log under /tmp/RoomTrek-1821-events. iphone-events.jsonl preserves the filtered
read-only download. Supplied Pi logs and map snapshots remain untouched. No
regression suite needed for analysis-only artifacts.
