<!-- @(#)report.md 3.2.maps.3 2026/11/10 11:14:37 -->
# Movement and the happy-to-sad transition

The11:02–11:11 recording establishes AR session replacement on the first pad
move. It does not isolate an intrinsic motion-induced tracking failure.

- Fresh phone session13744358242786495527 has630normal packets from11:02:35
  through11:03:38. A left5degree step enters remote_control11:03:38, which
  queues automatic survey startup. SESSION_STOP completes11:03:38.849;
  seed0B2FA89D-F7EA-4002-9AC7-92C32AF1D0D5 resumes11:03:38.877. The phone now
  reports initializing/relocalizing in a new session, explaining attention beeps.
- Repeated pad remote/idle transitions queue starts and saves faster than the
 30second relocalization operation completes. Queue-full errors begin11:03:46.
  Jobs continue starting/stopping AR long after their originating pad steps.
- There are brief real candidate matches, followed by rapid save/stop/restart.
  Four successful child saves create revisions2–5 at11:04:52,11:04:58,11:05:12,
  and11:09:39. Latest UUID11CEE584-D76D-4B69-B3AF-2FE1C804BB7C.
 19sessions/4559packets contain31map-valid frames in six sessions. Feature
  medians remain sparse. The reason records contain initializing, relocalizing
  and normal states; no excessiveMotion reason is recorded. Neither this fact
  nor brief candidates establish sustained accuracy or physical tracking health.
- Cached live console state has no map job/kept session. Thus the previous
  explicit-Keep preservation was not active. No fresh/Keep web action is logged
  in this supplied run. Exact phone tone events were not downloaded.

Fixed locally in3.2.maps.3: manual mode entered from idle does not own the phone
lifecycle. Pad/idle cycles preserve a locally running survey even without Keep
and after a Pi restart. Existing autonomous-run takeover saves once at idle;
later manual steps do not create new jobs. Explicit Keep still protects unsaved
survey work from autonomous mission starts. Phone save qualification unchanged.

46focused map/survey/manual-step tests pass, including actual four-direction
steps without adoption,100rapid remote/idle pairs with no phone commands or
queue entries, and single automatic-run save at takeover. JS syntax/whitespace
checks pass. Per-session metrics in metrics.json. This change is Pi/web-only;
the installed iPhone build already supports it.

For the next test: Stop / idle; sync/restart Roomberry to clear the old queue;
reload the page, start a fresh survey, then use the pad. Refresh phone status
after a move and compare session IDs. A tracking failure within that unchanged
session would be new evidence to investigate. More viewpoints do not guarantee
that ARKit will reach extending/mapped coverage or recognize a saved map.

Read-only supplied-log/cached-status analysis. No live movement, AR start/stop,
map mutation, phone installation or Pi deployment was performed.
