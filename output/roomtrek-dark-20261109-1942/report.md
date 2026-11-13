<!-- @(#)report.md 3.2 2026/11/09 19:54:04 -->
# RoomTrek after dark,19:42–19:49

The phone is responsive, but cannot relocalize to the existing mapped kitchen
seed. This is distinct from a dead camera, missing UDP link or confirmed CPU
overload. No camera brightness/CPU/thermal measurements were collected.

-2924type6 packets across10sessions.2639loaded-map packets; none qualified as
  valid localized map poses. All loaded-map samples remain limited/initializing
  or relocalizing. The logged reason is primarily relocalizing, not insufficient
  features. Loaded-map packet sequence continuity is intact; sample age is
  typically60–70ms. Two missing sequences occur only in the pre-run fresh session.
- Fresh zero-map surveys briefly reach normal tracking (254packets including
  pre-run frames), with feature medians207 and69 in two later short sessions.
  Finding features can build a new coordinate frame without recognizing the
  saved map. It does not prove successful map matching or map accuracy.
- Phone records31attention_required /2tracking_ok heartbeat attempts. Thus the
  user's predominantly low-double observation matches the software record.
- First WALL19:42:33 holds phone_ready. Resume1 times out19:43:04 after30seconds;
  Pi acknowledges stop and starts resume2. That session stops19:43:22 before
  its deadline, returning Session stopped; WALL aborts without departure.
  Startup holds as intended (7mm accumulated encoder path, no WALL departure).
- Additional local/other-client session starts and fresh surveys appear; source
  of those app actions is not logged. Discovery starts19:44:35 and remains a
  separate mode: the new phone-readiness motion gate applies to WALL, not all
  robot missions. Its phone resume is stopped19:44:48.
- Another saved-map session starts19:45:39, times out19:46:09, remains lost until
  stopped19:48:18. Second WALL then resumes the same seed, times out19:48:48,
  acknowledges stop and issues its one retry19:48:49. Copied Pi log ends19:49:04
  while waiting; later downloaded phone log records session stop19:49:14 before
  the second deadline. Stop origin (UI/background/other client) is not recorded.
- No saved-map success or new map revision appears. Original seed remains.

Darkness and changed lighting are plausible causes, not proven by these logs.
Apple notes that saved-world-map relocalization is less reliable when lighting
or the environment changes. First test normal room lighting and the same camera
view near the saved starting position, without replacing the existing kitchen
map or lengthening timeouts. An interrupted retry cannot establish whether a
full attempt would have succeeded.

Source: [Apple, Managing Session Life Cycle and Tracking Quality](https://developer.apple.com/documentation/arkit/managing-session-life-cycle-and-tracking-quality).
Read-only phone event downloads are filtered in iphone-events.jsonl; aggregate
counts in metrics.json. Supplied logs unchanged. No robot/app/config changes,
new AR commands, deployment or tests performed during this analysis.
