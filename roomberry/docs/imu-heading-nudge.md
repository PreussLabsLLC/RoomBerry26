<!-- @(#)imu-heading-nudge.md 3.2.nudge.1 2026/11/12 18:00:26 -->
# Bounded IMU correction of the tag15 homing heading estimate

User selected correction of the estimate, rather than automatic parked turns.
The active homing pose can receive a small relative-gyro heading correction.
This applies only to Tag15Return; it does not change recorded wheel odometry,
ARKit pose, the independent comparison/trails, or start a task from idle.

An accepted stationary tag fix supplies room heading. Receiver keeps600motion
observations (~60seconds at10Hz). Pair the tag's actual capture timestamp to
nearby valid same-session/generation Core Motion samples within150ms, not to
the detector completion time. Require at least two samples spanning80ms with
less than1degree integrated rotation in the capture window. Missing history,
invalid/freshness failures or motion at capture leave wheel heading in use.

The anchored gyro target is tag-heading plus the subsequent change in the
phone's integrated vertical rotation. It needs no compass or camera mount-yaw
adjustment because a rigid mount's constant offset cancels in relative rotation.
The existing wheel integration first predicts the local homing pose. Only its
heading is nudged; subsequent ordinary distance integration follows the corrected
heading. Existing positions are not retroactively shifted or fitted.

```json
"imu_heading_nudge": {
  "enabled": true,
  "gain": 0.2,
  "max_rate_deg_s": 1.0,
  "max_step_deg": 0.25,
  "max_total_deg": 5.0,
  "max_innovation_deg": 10.0
}
```

Apply20%of the wrapped heading discrepancy, bounded by0.25degree per update,
1degree/second and an absolute total5degree correction since the last accepted
tag fix. Rate budget is capped to250ms so a long gap cannot create a large
catch-up jump. Duplicate motion sequence numbers cannot apply repeated nudges.
Disagreement exceeding10degrees is rejected. Settings must stay within hard
finite policy limits; malformed configuration rejects homing startup.

Current motion must be valid and<=250msold. Wheel sensor data must be ready,
<=150msold and timestamp-matched within150ms. Missing/stale input falls back
to wheel propagation from the current estimate, retaining any correction
already applied rather than jumping the pose back. A phone session, motion
integration generation or wheel epoch change invalidates the anchor; only a
new accepted tag fix can enable corrections again. A tag fix replaces the pose
as before and resets the correction budget. AR position is never fused here.

The existing motion leases, scan pause, pulse brake deadlines, bumper/cliff/
wheel-drop handling and300mmarrival validation remain responsible for motion
safety. Unexpected nudge errors disable that anchor and preserve wheel-only
operation. Corrections are paused while a tag scan is active. Core Motion is
not external ground truth; its biases may drift, hence the small bounded budget
and recurring tag reference.

Pi log records `IMU heading nudge anchored:` and `IMU heading nudge:` with source
session/generation, innovation, applied step and total. These do not trigger
speech. Homing status/decision samples include imu_heading_nudge; the web UI
shows availability and correction total. The existing three-way comparison
continues to use the raw wheel and AR measurements for honest diagnostics.

Sync autonomy.json,roomberry.py,roomberry_mission.py,roomberry_motion.py,
roomberry_navlink.py,roomberry_tag_return.py and web/app.js toPi3 and restart
Roomberry. Start a homing task with confirmed stationary tag scans to anchor it.
The already installed type7iPhone sender is sufficient; no phone rebuild.
Set enabledfalse to return to wheel-only homing. Physical verification should
check left/right signs and logged bounded steps before interpreting improvement.
