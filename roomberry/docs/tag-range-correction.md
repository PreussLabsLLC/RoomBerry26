<!-- @(#)tag-range-correction.md 3.2.rollup.1 2026/11/13 19:43:59 -->
# Final twelve-percent tag translation correction

User-selected final setting after the November13 checks: multiply every newly
estimated tag's native camera-frame metric translation by **1.12**. A native
1000mm range becomes1120mm. This replaces the earlier tag15-only1.10 pilot;
factors do not compound. All detected families and IDs receive the default.

The local autonomy.json selects this inside `camera`:

```json
"pose_translation_scale": 1.12
```

Scales must be finite numeric values between0.5 and2. The constructor defaults
to1.0 when omitted. The older `pose_translation_scales` per-tag map remains
supported as an absolute override for compatibility, but the active configuration
has no per-tag overrides. Physical tag size, camera intrinsics, native rotation,
quality/corners and mount geometry are unchanged. The fixed148mm mount offset
is applied after the camera translation is scaled, and is not scaled itself.
This empirical metric correction does not identify an intrinsic-model cause.

Scan archives retain `raw_tag_pose_camera`, `raw_distance_mm`, `raw_depth_mm`
and `pose_translation_scale`; existing `tag_pose_camera`, `distance_mm` and
`depth_mm` fields carry the calibrated observation. Localization and speech
consume the corrected fields. The isolated worker applies the correction once.
Old scan archives are not rewritten. The survey table exposes native range,
corrected range and applied factor alongside tape readings.

## Navigation and calibration fixes included in this rollup

- Standalone tag15 homing retains its tag-return controller when good grout
  steering is available. A direct mapped route and three fresh line frames,
  confidence≥80%, angle≤5° and camera-line error≤30mm qualify optional70mm/s
  line guidance. Multi-waypoint routes use mapped guidance. Line loss falls
  back to the bounded mapped/tag controller, rather than handing to scan-free
  GridDrive. The400mm stopped-rescan cadence, final fix, slow pulsed approach
  and two-scan validation within300mm all remain in charge. Any bumper contact
  stops standalone homing; it cannot substitute for validated arrival.
- Strong visible tag15 bearing guidance covers corrected camera ranges over2.5m
  through5m. Each150mm advance requests another scan; the20s per-view freshness
  and3000mm total bearing-travel bounds remain explicit. Full position-fix
  quality and2.5m range gates are unchanged. This removes the4.07m visibility
  gap that caused the previous search turn; it does not accept a distant tag
  plane orientation as an accurate position fix.
- A sensor readiness/age glitch while already parked can hold for at most1s,
  with motor lease ended. Movement, odometry reset, contact, hard hazard, latch,
  stopped OI, lease expiry or unsafe battery still abort. Moving sensor faults
  have no grace. Recovery never starts another tile automatically. The UI
  reports the hold and blocks Next while requalification is pending.
- The first actual tape entry anchors a restarted survey's expected-distance
  labels and wheel-based absolute cap. Original configured-start metadata and
  append-only scan/measurement events remain available.
- Existing decimal-input, stopped-station tape entry, timeout/cursor recovery,
  raw-value logging and authenticated phone-battery fixes remain included.

## GridRunner build10

Build10 additionally sends the existing NavLink type7 Core Motion packet at10Hz
from the same100Hz sensor stream used by line tracking. It includes quaternion,
angular velocity, acceleration, gravity and gyro-integrated yaw. A sampling gap
starts a new generation; old samples lose validity. This enables the existing
Pi gyro-heading comparison/nudge path to receive attitude rather than only
health gyro rates. It supplies no ARKit position. Type3 health, type4 compass,
type5 line packets, signed control and speech remain supported. Battery fields
from build9 are included.

## Deployment

The all-tag correction and Pi navigation changes require the updated Python
files, web assets and autonomy.json through the normal Pi upload, followed by an
explicit service restart. Pi uploads remain user-owned; none was performed here.
The factor does not require a phone reinstall, but type7 attitude telemetry does
require GridRunner build10. The signed app is at
`/tmp/GridRunner-device/Build/Products/Release-iphoneos/GridRunner.app` on this Mac.
Initially no USB phone was connected. After the user connected the iPhone X,
build10 was installed without uninstalling or removing app data; NavLink.key
readback was verified. Open GridRunner and start streaming to send type7 data.

For the next check, keep the same physical measurement reference and inspect
raw/corrected/tape values. Do not drive beyond the carpet threshold. No physical
run or arrival validation was performed as part of these local changes.
