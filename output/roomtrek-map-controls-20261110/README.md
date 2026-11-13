<!-- @(#)README.md 3.2.maps.1 2026/11/10 10:41:19 -->
# RoomTrek web map controls verification

Implemented the mounted-phone map panel in the local Roomberry console:
fresh/resume/stop survey, save under a name, inspect storage, rename/delete
saved maps, and persist an exact map choice for subsequent mission/Clock starts.
Battery speech follows 30 seconds of quiet and announces both devices.

- Full Python suite: 718 tests passed in 104.372 seconds. Final focused checks
  after input-validation hardening and corrupt-selection coverage: 13 passed.
- Swift authenticated control/replay checks passed, including map commands.
- Signed Release iPhone build passed; artifact:
  `/tmp/RoomTrek-maps/Build/Products/Release-iphoneos/RoomTrek.app`.
- Chrome browser simulation at desktop 1440×1500 and mobile 390×1500 passed
  fresh → save → select → rename → resume → stop → delete. Verified mission-map
  deletion disabled, names rendered as text, no JavaScript errors or horizontal
  overflow. Screenshots are desktop.png/mobile.png; HTML is rendered test state,
  using fake phone/robot data, not a live connection to Rosie.
- Initial screenshot-only browser invocation timed out; the completed checks
  use Chrome's debugging connection. Test script: `/tmp/roomberry-maps-browser-check.py`.

At the user's subsequent request, ios-deploy installed this build on Peters10
(iPhone X, iOS16.7.16) over USB at10:41, confirmed by InstallComplete and exit0.
Open RoomTrek and keep it foreground. The Pi sync/restart remains outstanding;
reload the console afterward. The app headline is
`RoomTrek 3.2.maps.1 2026/11/10 10:15:00`. No robot movement, live map mutation
or Pi upload occurred.

Usage: [RoomTrek survey documentation](../../roomberry/docs/roomtrek-survey.md).
