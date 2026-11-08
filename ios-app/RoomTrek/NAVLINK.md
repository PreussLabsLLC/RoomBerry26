<!-- @(#)NAVLINK.md 3.1.roomtrek.2 2026/11/08 12:00:00 -->
# Experimental RoomTrek NavLink extension

Approved for this sender; receiver implementation is pending. Existing types
1–5 are unchanged. Never send this as type 1: its frame and map semantics differ.
All integers little-endian, floats IEEE float32; exactly 128 bytes, UDP port 5010.

| Offset | Type | Meaning |
| --- | --- | --- |
| 0 | 4 bytes | NVLK |
| 4 | u8 | Version 1 |
| 5 | u8 | Type 6 |
| 6 | u16 | Length 128 |
| 8 | u64 | Nonzero attempt/session ID |
| 16 | u32 | Sequence, wraps modulo 2^32 |
| 20 | u16 | Flags: bit 0 valid map-relative camera pose; all others zero |
| 22 | u8 | Tracking: unavailable 0, limited 1, normal 2, interrupted 3 |
| 23 | u8 | Reason: none 0, initializing 1, motion 2, features 3, relocalizing 4, interruption 5, failure 6, other 7 |
| 24 | u64 | Frame timestamp, phone uptime microseconds |
| 32 | u64 | Assembly timestamp, phone uptime microseconds |
| 40 | 16 bytes | Map UUID, canonical UUID byte order; zero for Surveyor |
| 56 | 3 floats | Camera position metres, mapped world (AR.x, -AR.z, AR.y) |
| 68 | 4 floats | Quaternion x,y,z,w: native camera axes into mapped world |
| 84 | float | Optical forward heading radians; atan2(mapped forward y,x) |
| 88 | u32 | Capture age microseconds; UINT32_MAX if unknown |
| 92 | u16 | Feature count |
| 94 | u8 | Relocalization: not needed 0, relocalizing 1, candidate localized 2, lost 3 |
| 95 | 33 bytes | Reserved, zero |

Validity requires Navigator with nonzero map ID, observed relocalization then
normal tracking for at least one second, normal current tracking, usable
horizontal heading, capture age 0–250 ms, no interruption or failure. Invalid
packets are diagnostic history only. Surveyor never sends valid navigation data.
Pose is camera pose even when a mount transform has been configured; robot pose
must be derived separately using the documented rigid transform.

Future receivers must reject invalid lengths/enums/reserved fields/nonfinite
values and inconsistent validity, qualify freshness, deduplicate sequences,
and bind the full map UUID before navigation use. Phone uptime is not Pi time.
No acknowledgment, clock synchronization, robot control or fusion is included.
