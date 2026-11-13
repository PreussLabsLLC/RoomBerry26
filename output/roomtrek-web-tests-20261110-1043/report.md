<!-- @(#)report.md 3.2.maps.1 2026/11/10 10:49:30 -->
# Web tests: fresh tracking replaced by old-map startup

The fresh session does not spontaneously lose tracking in the supplied run.
Starting WALL replaces it with a saved-map relocalization attempt.

- 10:43:42: WALL starts, resumes the configured old kitchen seed. Two attempts
  time out; abort at10:44:43 with0mm travel.
- 10:44:56: web map refresh completes.
- 10:45:11: web fresh-survey action completes. Its NavLink stream has seven
  initializing packets followed by232normal packets, ending10:45:34. Median
  visible feature count3. Frame stream continues; no sequence gaps.
- 10:45:34: GET /roomba/?op=wall starts WALL. Coordinator explicitly stops the
  fresh session10:45:35 and resumes seed
  0B2FA89D-F7EA-4002-9AC7-92C32AF1D0D5. This is a new AR session/coordinate frame.
- Attempts time out10:46:05 and10:46:36. WALL aborts stopped with0mm travel.
  Map POST requests during the active mission receive409 conflicts, as designed.
- Another loaded-seed session appears10:47:06–28, still limited. Its initiator
  is not established by Pi logs. No successful save, rename, delete or mission
  selection action is recorded in the supplied interval.

1808type6 packets total:1417loaded-map packets, all limited, zero valid localized
poses, zero within-session sequence gaps. Loaded median ages57–77ms.391fresh
packets include the healthy pre-run session and the web fresh session.
Fresh packets intentionally lack map-valid flags even when tracking is normal.
Feature counts are sparse, but do not establish why the old map cannot match.

The high beep means active, valid, normal, fresh phone tracking with NavLink on.
The low double also covers a stopped session; it is not specific to a camera
failure. Phone event listing timed out both inside and outside the sandbox, so
exact high/low timestamps are unavailable. Evidence establishes the session
switch and failed relocalization, not the cause of the map mismatch.

Next: keep Rosie idle; start fresh Surveyor from the panel; refresh to inspect
tracking and world mapping; save under a new name once extending/mapped coverage
permits; select that saved entry and press Use for next run. Verify Next run
shows its name/UUID before starting WALL. Do not infer saved coverage from a
happy beep. Starting WALL before save/selection returns to the old automatic
seed policy and discards the unsaved fresh session.

Sources: supplied roomberry.log, NavLink104326binary, local heartbeat and
coordinator source. Per-session metrics in metrics.json. Read-only investigation;
no application/configuration changes, deployment, AR or robot commands issued.
