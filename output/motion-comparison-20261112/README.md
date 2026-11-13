<!-- @(#)README.md 3.2.imu.1 2026/11/12 15:16:24 -->
# Independent motion comparison and30degree steering

Implemented:
- iPhone Core Motion requested50Hz, streamed type7at10Hz and locally logged2Hz.
  Separate native attitude, processed gyro, user acceleration, gravity and
  gravity-vertical integrated rotation. Works independently of AR pose validity.
- No magnetic bearing, acceleration-derived position, pose correction or steering
  fusion. Session stop stops device-motion updates. Error/gap transitions flag
  availability and reset integration generation; old callbacks ignored.
- Pi validates/records/exports new type7, orders observations with retired
  session/generation protection, and compares fresh same-session AR frames and
  wheel samples within150ms. Relative three-way turns and differences appear
  in log JSON, status JSON and web console. Unavailable/stale readings hidden;
  diagnostic exceptions cannot interrupt control.
- Pad adds left+30/right-30 beside existing5/15degree buttons, using existing
  measured wheel feedback, braking, motion leases and safety cancellation.

Verification:
- Swift gyro checks: tilted gravity axes preserve yaw sign, roll does not create
  yaw, timestamp gaps break integration. Synthetic Swift128byte type7fixture
  decodes exactly in Python (session42,generation3,yaw1.25rad).
- Python validates bad framing/numbers/age/quaternion/gravity, CSV roundtrip,
  reordered/wrapped/retired packets, signed relative turns, same-session/fresh
  pairing, generation/wheel reset, stale panel state, diagnostic failure isolation.
-746full-suite tests passed in96.9s.
-166focused mission/motion/steering/web tests pass after30degree routing update.
- Unsigned and signed iphoneos Release builds pass. Signed app:
  /tmp/RoomTrek-motion/Build/Products/Release-iphoneos/RoomTrek.app.
- JavaScriptCore syntax check of app.js passes. Browser visual/device-motion
  performance and sign verification on the actual mounted phone still needed.

Rollout: install the new RoomTrek build; sync roomberry.py,roomberry_mission.py,
roomberry_navlink.py,roomberry_motion.py,roomberry_manual_step.py,
roomberry_web.py and web assets to Pi3 and restart the manually run process.
Start a fresh phone session; compare one left and one right turn while stationary
before a longer run. Existing key and mount configuration remain applicable.
No iPhone installation, Pi deployment or robot motion was performed in this task.
