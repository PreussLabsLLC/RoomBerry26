<!-- @(#)report.md 3.2 2026/11/10 10:05:37 -->
# Daylight startup investigation

The supplied 09:54–10:02 Pi recording shows three WALL starts, all held before
departure because the phone never relocalized to the requested kitchen seed
0B2FA89D-F7EA-4002-9AC7-92C32AF1D0D5. Daylight did not resolve the failure;
lighting alone is not an adequate explanation.

- 09:54:13: first attempt times out after 30 seconds. Its retry is stopped
  at 09:55:03 before the deadline; WALL aborts with `Session stopped`.
- 09:58:32 and 10:00:44: both starts exhaust two 30-second attempts and abort.
  Neither run departs. Logged finish travel is 0, 0.45 and 0 mm respectively.
- No loaded-map session reaches normal tracking or a localized valid pose.
  Loaded sessions have no packet sequence gaps; median frame ages are about
  55–73 ms. The camera and UDP stream continue delivering observations.
- Fresh sessions do reach normal tracking: 09:54:01–13 and most of
  09:56:36–09:58:32. These are not saved-map locks. Fresh sessions deliberately
  do not set the map-valid packet flag. Their median visible feature counts
  are only 10 and 4; loaded sessions range from 2 to 132.5. These counts do
  not measure illumination, prove a camera fault or establish map quality.

The user reports using Delete Selected during the run. Code inspection shows
that this deletes a library file without stopping the active AR session or
clearing its in-memory world map. Remote SURVEY_START sets surveyParentID but
does not update selectedMapID, so the selected row need not be the active map.
Deletion also ignores filesystem errors. The recording alone cannot identify
which map was deleted or whether deletion succeeded.

Separately, autonomy.json pins seed_map_id. The coordinator chooses that seed
when no kitchen child revision exists, even if the seed is absent from the
inventory. Deleting a seed therefore does not request a fresh robot survey;
on a subsequent start a missing seed should produce a map-load failure.
The supplied starts instead report relocalization timeouts, so they are not
evidence of a successfully deleted seed being reloaded from disk.

Next diagnostic: leave Rosie idle, stop the phone session, then start a local
Surveyor session without launching WALL. Local Surveyor start clears the
parent map. Inspect sustained tracking and the camera view there before
changing the robot's seed policy. A fresh robot baseline would also require
an explicit seed/configuration change; deleting a row alone is insufficient.
Do not infer that a fresh coordinate frame preserves the old kitchen frame.

Source: supplied roomberry.log, NavLink binary for 20261110-095401, and local
RoomTrek/coordinator source. Per-session counts are in metrics.json. A read-only
iPhone log-list request timed out both inside and outside the sandbox; phone
events and exact deletion timing are unavailable. No app/control/configuration
changes, deployment, AR commands or robot movement were performed.
