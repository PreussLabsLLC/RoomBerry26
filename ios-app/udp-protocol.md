<!-- @(#)udp-protocol.md 2.3.ios-plan.1 2026/10/29 -->
# UDP pose protocol v1 (proposed)

## Transport and identity

Send UTF-8 JSON, one object per UDP datagram, unicast to configurable Pi port 5010. Default pose/status frequency is 20 Hz. Maximum application datagram is 1200 bytes; reject oversized or truncated messages. No image data. UDP can lose, duplicate, delay or reorder packets: retain the newest valid frame, never retransmit old pose samples. A new pose supersedes an old one.

`robot_id` selects the robot; `room_id` and `map_revision` select the surveyed coordinate system. `session_id` is a fresh UUID for each AR tracking epoch, including reset/restart. `calibration_id` identifies alignment within that session. `seq` starts at zero and increases across all pose/status datagrams in one session; use an integer up to 2^53-1, starting a new session before overflow. `frame_time_s` must increase for accepted poses even if `seq` increases.

Bind one configured phone/robot/session/calibration tuple on the Pi while idle after explicit operator selection. A new UUID or calibration is a candidate requiring stationary rebind, never an automatic takeover. Delayed old-session packets cannot rebind. Persist room/mount definitions, but require rebind after receiver restart. Source IP filtering and random IDs prevent accidental cross-talk, not spoofing; v1 assumes a trusted private WLAN. If that assumption changes, require authenticated transport or per-packet authentication before autonomous use.

## Pose packet

Example with a qualified, calibrated frame (values illustrative):

```json
{
  "v": 1,
  "type": "pose",
  "robot_id": "roomberry",
  "room_id": "living-room",
  "map_revision": "survey-1",
  "session_id": "4f36453e-9bab-49cc-a5b9-1bb02c9d5c48",
  "calibration_id": "9ee53fc6-6792-4f34-8a18-689f4081fa46",
  "seq": 120,
  "frame_time_s": 1024.125,
  "send_time_s": 1024.130,
  "tracking": "normal",
  "reason": null,
  "mapping": "extending",
  "calibrated": true,
  "pose": {"x_mm": 1060.0, "y_mm": 760.0, "heading_rad": -1.570796},
  "height_mm": 0.0,
  "tilt_rad": 0.01
}
```

`pose` is the robot axle-center pose in the surveyed room frame, not the phone camera pose. X/Y are millimeters; heading is radians counterclockwise from room +X. `height_mm` and `tilt_rad` describe the robot base after mount compensation, relative to the calibrated floor and upright orientation; use them to detect lifting or bracket movement. Do not treat ARKit tracking status as a measured position covariance.

Enums: `tracking` is `normal`, `limited`, `unavailable`, or app-derived `interrupted`. `reason` is null or a diagnostic string, such as `initializing`, `excessive_motion`, `insufficient_features`, `relocalizing`, `backgrounded` or `session_error`. Unknown reasons remain diagnostic and do not make a non-normal state acceptable. `mapping` is `not_available`, `limited`, `extending` or `mapped`; it describes mapping progress and does not override tracking validity. Apple's [world mapping status](https://developer.apple.com/documentation/arkit/arframe/worldmappingstatus-swift.enum) is a separate signal.

While uncalibrated or unhealthy, use `type: "status"` with the same identity/sequence/timing fields; set `pose`, `height_mm`, and `tilt_rad` to null and supply tracking/reason. Calibration ID may be null before calibration. A status reports health only and cannot refresh accepted-pose age. Status with a bound identity and unhealthy state invalidates immediately. Session changes require rebind even if tracking is normal.

## Time bases and clock exchange

Frame and send times are seconds in the phone's monotonic uptime domain. Use `ARFrame.timestamp` for capture and a matching uptime clock for send time; verify their shared time base on-device. Do not subtract phone uptime from Pi monotonic time or use wall-clock time for freshness.

Pi initiates clock probes to the selected phone's UDP endpoint, which receives replies on its existing connection. Probes carry `v`, `type: "sync_request"`, `session_id`, random `probe_id`, and `pi_t1_s`. Phone replies immediately with `type: "sync_reply"`, the same identifiers and t1, plus phone receive/send uptime `phone_t2_s`, `phone_t3_s`. Pi records receive monotonic time t4 locally; never trust a packet-provided t4.

```text
offset(phone - pi) = ((t2 - t1) + (t3 - t4)) / 2
network_rtt = (t4 - t1) - (t3 - t2)
frame_capture_pi = frame_time_s - offset
frame_age = pi_now - frame_capture_pi
```

Correlate probe IDs, reject invalid/negative intervals, and retain low-RTT samples. Use at least five probes before enabling poses, then refresh every second. Initial targets: network RTT <= 50 ms, timing uncertainty <= 25 ms, clock estimate no older than five seconds. Bound uncertainty conservatively using half network RTT plus a clock-drift allowance; asymmetry limits accuracy. These are trial settings, not established WLAN guarantees. If sync fails, keep logging reception but withhold navigation validity. Reset clock state on session change, sleep or discontinuity.

An optional Pi `ack` once per second contains `v`, `type`, bound `session_id`, `last_received_seq`, `last_accepted_pose_seq` (nullable), `accepted_pose_age_s` (nullable), and receiver state (`unbound`, `syncing`, `tracking`, `stale`, `invalid`). It confirms receipt/application status, not motion permission. It cannot change phone calibration or drive the robot.

## Receiver processing order

1. Read with a bounded buffer and detect truncation; reject malformed UTF-8/JSON, non-object roots, duplicate keys, non-finite numeric values, booleans used as numbers, wrong types and unsupported versions/types. Limit string lengths and nesting before storing anything. Unknown fields within size limits may be ignored.
2. Check expected source and all bound identities. Never adopt unsolicited session/calibration changes during motion. Only a fully validated packet may advance sequence state.
3. Require increasing sequence and, for pose updates, strictly increasing frame timestamp. Packet duplicates, replay, and old frames do not refresh health or freshness.
4. Check send >= frame; map capture time with the current clock estimate. Reject ages above 250 ms, implausible future frames beyond timing uncertainty, or missing/expired sync. Track both capture age and Pi receive age.
5. Require normal tracking, calibration, finite bounded pose, matching room survey, acceptable height/tilt and continuity. Start with configurable room bounds plus a small margin. Fit velocity/yaw envelopes to actual configured robot limits and timing uncertainty; large discontinuities invalidate rather than clamp.
6. Atomically replace the latest accepted snapshot with capture/receipt times. Never let rejected input refresh the last-good pose timestamp. Drain bursts to the newest valid sample with bounded processing work.
7. Mission tick evaluates age again independently of socket activity. A stream of status, duplicate or invalid packets cannot defeat the 500 ms last-good watchdog. Explicit unhealthy tracking invalidates immediately. Socket exceptions and receiver thread death also invalidate.

Log accepted/rejected counts by reason, sequence gaps, capture/receive age, timing uncertainty, pose deltas, tracking changes and session transitions. Rate-limit repeated errors so malformed traffic cannot exhaust SD storage. No acknowledgements or retries are needed for individual pose packets.

## Mapping to existing pose consumers

Return `x_mm`, `y_mm`, `heading_rad`, `localized`, and `localization_age` with additional `source: "arkit"`, session/calibration IDs, and diagnostics. Age means time since the last accepted external observation, including during wheel propagation. Preserve tag-specific fields as empty tuples where legacy callers require them; do not fabricate accepted tag IDs. Consumers that require a real tag-scan event need explicit adaptation, as described in the implementation plan.
