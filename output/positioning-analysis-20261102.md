<!-- @(#)positioning-analysis-20261102.md 3.1 2026/11/02 17:40:00 -->
# Roomberry positioning analysis — 2026-11-02

Scope: the 16:01–16:21 remote-control session (`roomberry/logs/roomberry.log`), the
sensor CSV for that run, the NavLink/GroundHog recording, and the saved map state
and PNGs. No cleaning or planner code was changed. Wheel-drop safety is unchanged.

## TL;DR

1. **The map is not geometrically distorted.** It is a pose trail drawn over a grid
   in which every cell is still `free` and every cookie is still `pending`. There
   are no walls, obstacles or cleaned cells to distort.
2. **The trail is inflated by pose relocations, not by scale.** The current-session
   trail is 19.915 m long; the robot actually travelled 9.549 m. 9 segments longer
   than 275 mm account for 8.653 m (43 %), and 15 segments longer than 150 mm
   account for 9.856 m (49 %). Remove those jumps and the remaining trail is
   10.059 m, i.e. within 5 % of the real path.
3. **The three biggest jumps are tag-15 relocations at 1.7–2.5 m.** They are
   1.711 m, 2.528 m and 1.850 m (6.089 m total, 31 % of the trail). They happen
   when the 30 s jump gate has expired, so the next tag-15 solution is installed
   without a plausibility check, and a second consistent bad solution confirms it.
4. **Odometry is not 9.8 % high.** That earlier number came from
   `travelled_distance_mm`, which is the *absolute* path length and includes the
   forward/back correction at every stop. The localizer integrates the *signed*
   encoder distance. Over 12 intended one-tile moves the signed value averages
   288.6 mm, i.e. about **5 % short** of a 304.8 mm tile, not 10 % long.
5. **Tag range is not 18 % short and `fx` should not be changed.** At 16:08:40 the
   tag-15 range was 2079.7 mm while the odometry-propagated pose predicted
   2086.4 mm to the same landmark (0.3 %). The long-range failure is the tag's
   **bearing/orientation solution**, not its range.
6. The final stop is excellent: tag-15 range 136.5–136.6 mm (sd 0.03 mm), pose
   spread 1 mm, reprojection error 0.46–0.50, hamming 0, accepted on all three
   post-nudge scans.
7. **GroundHog is accurate when locked but loses lock while driving.** It is valid
   on 99.0 % of stationary packets but only 76.8 % of moving packets, in 420 short
   continuity segments. Its 6.356 m path is 66.6 % of the 9.549 m actually
   travelled because of those gaps, not because of scale. Its 26 bump events are
   nudges, drive starts/stops and the final carpet-threshold jolt — not the
   removed carpet runner.

## 1. Data used

| Source | Path | Use |
|---|---|---|
| Service log | `roomberry/logs/roomberry.log` | scan detections, fused poses, rejection reasons |
| Sensor CSV | `roomberry/logs/sensors/roomberry-sensors-20261102-160100.csv` | signed encoder distance, heading, wheel drops |
| NavLink | `roomberry/logs/navlink/roomberry-navlink-20261102-160100-0000.bin` | GroundHog advisory motion |
| Map state | `roomberry/logs/map-state-reset-20261031-01.json` | occupancy, cookies, trail |
| Map images | `output/map261102b.png`, `roomberry/logs/maps/roomberry-maps-20261102-160100-769646/` | rendered trail |
| Layout references | `roomberry/docs/KitchenFloor.jpg`, `Roomba-1tile-off-tag15.jpg`, `Tag15-close-up.jpg` | tile/tag geometry |

NavLink `segment_x_mm` / `segment_y_mm` reset when `continuity` changes, so only
within-continuity deltas are meaningful. GroundHog remains advisory only and was
not used to override any pose.

## 2. Last three post-nudge scans at each stop

The first scan at a stop was taken before the Roomba was nudged into its final
position, so the table below uses the **last three scans** of each stop. Stop
groups with only one scan are the startup stop and the fast repositioning stops
after 16:14; the final stop has five scans and its last three are 16:17:53,
16:18:16 and 16:18:39.

`odom since prev` is the change in **`travelled_distance_mm`** (absolute), shown
only as a timeline aid; see §5 for why it is not the odometry scale.

| Stop | scans | last-3 tag-15 range (mm) | sd | min/max pose err | hamming | accepted (last 3) | fused pose (last) | pose spread | odom since prev |
|---|---:|---|---:|---|---:|---|---|---:|---:|
| 16:03:00 | 1 | 326.1–326.1 | — | 0.05–0.05 | 0 | 15 | (7299, 1267) | — | — |
| 16:03:11 | 4 | 593.1–594.3 | 0.5 | 0.02–0.27 | 0/0/0 | 15/15/15 | (7025, 1282) | 14 | +400 |
| 16:04:02 | 4 | 864.3–865.7 | 0.6 | 0.01–0.02 | 0/0/0 | 15/15/15 | (6754, 1245) | 54 | +313 |
| 16:04:56 | 4 | 1116.4–1123.3 | 2.9 | 0.01–0.07 | 0/0/0 | 15/15/15 | (6558, 1421) | 65 | +416 |
| 16:05:49 | 4 | 1390.6–1405.4 | 6.5 | 0.00–0.09 | 0/0/0 | 15/15/15 | (6200, 1305) | 253 | +332 |
| 16:06:38 | 4 | 1580.8–1644.9 | 27.7 | 0.16–1.26 | 0/0/0 | -/15/15 | (6046, 1772) | 697 | +315 |
| 16:07:30 | 4 | 1825.9–1849.8 | 9.8 | 0.60–0.93 | 0/0/0 | 15/15/15 | (5918, 1850) | 142 | +339 |
| 16:08:14 | 5 | 1980.8–2181.3 | 82.6 | 0.07–1.57 | 0/0/0 | 15/15/- | (6123, 323) | 191 | +351 |
| 16:09:09 | 5 | 2050.7–2142.4 | 38.3 | 2.68–4.30 | 0/0/0 | 15/15/15 | (6225, 2830) | 203 | +320 |
| 16:09:59 | 5 | 2671.9–2713.8 | 17.2 | 0.02–0.07 | 0/0/0 | -/-/- | (6071, 3066) | 0 | +305 |
| 16:10:46 | 4 | 1804.4–1943.8 | 59.0 | 14.18–20.23 | 0/0/0 | -/-/- | (4687, 1931) | 0 | +324 |
| 16:11:24 | 4 | 2444.4–3289.9 | 351.6 | 0.03–5.45 | 0/0/0 | -/-/- | (4416, 2041) | 0 | +308 |
| 16:12:05 | 4 | 1545.8–1831.1 | 123.0 | 26.80–49.67 | 0/0/0 | -/-/- | (4148, 2165) | 0 | +369 |
| 16:12:51 | 4 | 1858.3–2610.7 | 336.8 | 6.20–29.15 | 0/0/0 | -/-/- | (3882, 2285) | 0 | +339 |
| 16:13:36 | 4 | 1198.0–1508.8 | 127.0 | 64.71–127.32 | 0/0/0 | -/-/- | (3611, 2435) | 0 | +319 |
| 16:14:39 | 1 | 2449.0–2449.0 | — | 5.30–5.30 | 0 | - | (4409, 1999) | — | +922 |
| 16:15:05 | 1 | 2032.9–2032.9 | — | 3.85–3.85 | 0 | - | (5300, 1613) | — | +971 |
| 16:15:23 | 1 | 2043.8–2043.8 | — | 0.00–0.00 | 0 | 15 | (5590, 1419) | — | +445 |
| 16:15:31 | 1 | 1973.0–1973.0 | — | 0.35–0.35 | 0 | 15 | (5849, 1811) | — | +21 |
| 16:15:39 | 1 | 1997.6–1997.6 | — | 0.31–0.31 | 0 | 15 | (5776, 2058) | — | +3 |
| 16:16:07 | 1 | 1173.0–1173.0 | — | 0.38–0.38 | 0 | 15 | (6468, 1485) | — | +1002 |
| 16:16:36 | 1 | 411.9–411.9 | — | 0.09–0.09 | 0 | 15 | (7219, 1282) | — | +929 |
| 16:17:04 | 5 | 136.5–136.6 | 0.0 | 0.46–0.50 | 0/0/0 | 15/15/15 | (7488, 1257) | 1 | +504 |

Notes:

* At 16:03:11 the second of the four scans also contains a 77.9 mm hamming-1
  false detection (`pose_error` 130612.78), but the same scan has a valid
  593.1 mm detection and the localizer rejects the hamming-1 one. The three
  post-nudge scans (593.1, 593.5, 594.3 mm) agree to 1.2 mm.
* At 16:08:14 the group contains a rejected scan before tag 15 is accepted at
  16:08:46 with a 1.7 m jump. This is the first teleport; see §4.
* At 16:06:38 the three scans span 697 mm in pose even though the tag-range sd is
  only 27.7 mm and the reprojection error is ≤ 1.26. The branch is already
  unstable at ~1.6 m, well before the first teleport.
* Rows 16:09:59–16:13:36 have no accepted tags. The fused pose continued on
  odometry and the listed pose is the stale/teleported estimate.
* The `16:17:04` row's last three scans are the final post-nudge scans
  (16:17:53, 16:18:16, 16:18:39); their ranges are 136.5–136.6 mm and the pose
  spread is 1 mm. The first two scans of that stop are excluded.

### Repeatability vs range

The tag is 57.5 mm across. With `fx ≈ 633 px` at 820×616 capture, it is only:

| range | tag width on sensor |
|---:|---:|
| 0.5 m | ~73 px |
| 1.0 m | ~36 px |
| 1.5 m | ~24 px |
| 2.0 m | ~18 px |
| 3.0 m | ~12 px |

That matches the observed repeatability: sub-mm at 0.14 m, 0.59 m and 0.86 m,
a few mm at 1.1–1.4 m, then tens to hundreds of mm beyond ~1.5 m:

| range (mm) | last-3 sd (mm) |
|---:|---:|
| 136.5 | 0.03 |
| 593.6 | 0.5 |
| 865 | 0.6 |
| 1119 | 2.9 |
| 1400 | 6.5 |
| 1606 | 27.7 |
| 1838 | 9.8 |
| 1885 | 59.0 |
| 2073 | 82.6 |
| 2091 | 38.3 |
| 2692 | 17.2 |
| 2820 | 351.6 |

The degradation is not a clean function of range — geometry and the two-fold
pose ambiguity matter — but the practical boundary is about **1.2–1.5 m**.

## 3. Why the generated map is badly distorted

### The map is a trail on a blank grid

The saved state is:

* grid `103 × 92` cells at `87 mm` → `8.961 × 8.004 m`
* occupancy: **9,476 cells, all `free`**
* cookies: **9,476 cells, all `pending`**
* image: `694 × 676 px` at 6 px/cell (plus margins)

Manual driving never marks obstacles or cleaned cells, so the image contains no
map content except the trail and the tag markers. The map is not a SLAM map yet.

### The trail length is dominated by relocations

Current session (`trail_session_start = 256`, 205 points):

| quantity | value |
|---|---:|
| trail path length | **19,914.7 mm** |
| actual path (`travelled_distance_mm`) | **9,549 mm** |
| ratio | **2.09×** |
| segments > 275 mm | 9, summing **8,652.7 mm** (43.4 %) |
| segments > 150 mm | 15, summing **9,856.1 mm** (49.5 %) |
| remaining path after removing >150 mm | **10,058.6 mm** |
| remaining vs actual | **+5.3 %** |

So essentially all of the 2× inflation is a handful of pose jumps. The trail itself
is a reasonable 10 m path; the jumps add another 10 m of straight lines across the
kitchen.

Largest current-session jumps:

| trail index | jump | from → to (mm) | approximate event |
|---:|---:|---|---|
| 59 | 1,711.3 mm | (5664.7, 2002.4) → (5932.9, 312.3) | 16:08:46 tag-15 relocation |
| 67 | 2,527.9 mm | (5843.1, 243.6) → (6088.3, 2759.5) | 16:09:37 tag-15 relocation |
| 81 | 1,850.2 mm | (5927.9, 3301.0) → (4681.4, 1933.7) | 16:10:50 tag-15 relocation |
| 42 | 693.6 mm | (5943.2, 1375.2) → (6232.6, 2005.6) | 16:07:30/16:08:14 correction |
| 152 | 470.2 mm | (5590.4, 1418.5) → (5848.8, 1811.3) | 16:15:23 correction |
| 33 | 394.2 mm | (6285.2, 1519.3) → (6438.3, 1882.5) | early tag correction |
| 34 | 380.6 mm | (6438.3, 1882.5) → (6245.1, 1554.6) | next correction |
| 23 | 325.4 mm | (6460.8, 1310.6) → (6565.4, 1618.7) | early tag correction |
| 43 | 299.4 mm | (6232.6, 2005.6) → (6045.9, 1771.6) | correction |

The three big ones alone are **6,089 mm = 30.6 %** of the trail.

### The previous session is still drawn

The state contains an older 256-point trail with a path length of **27,832 mm** and
a largest jump of **4,417 mm**. The renderer draws it in a pale blue fade behind
the current trail. So the PNG contains both this session's jumps and last
session's much longer scribble.

The renderer does split the trail at 275 mm (`trail_segments`) and does not draw a
line across a gap, but it still draws **every fragment** of both sessions. That is
why the picture looks like a set of disconnected streaks rather than one path.

### What the distortion is not

* **Not aspect ratio.** 103 × 92 cells at 6 px = 618 × 552 px inside the
  694 × 676 px image; cells are square.
* **Not a 10 % odometry scale.** A 10 % scale would stretch a 9.5 m path by 1 m,
  not double it.
* **Not the grid.** The 87 mm cell size is the map's planning resolution
  (`robot_radius / 2`), not the 304.8 mm tile grid. The two are unrelated.

## 4. Root cause of the pose teleports

### The 30 s gate is disabled by rejected scans

`_consistent_estimates()` only applies the 500 mm / 0.6 rad jump gate when:

```python
prior_age <= self.max_pose_jump_age   # 30 s
```

`prior_age` is `monotonic() - self._last_tag_time`, and `_last_tag_time` is
updated **only when an estimate is accepted** (`roomberry_localization.py:137`).
A rejected scan does not refresh it. Scans are roughly 23 s apart, so one
rejected scan plus processing time pushes the next scan past 30 s and the gate is
skipped exactly when a bad solution arrives.

The log shows the three teleports following this pattern exactly:

| event | prior pose | localization age at prior scan | result |
|---|---:|---:|---|
| 16:08:46 | (5674, 1998) | **37.5 s** | tag 15 accepted, pose → (5933, 312), jump 1,705 mm |
| 16:09:37 | (5866, 248) | **37.1 s** | tag 15 accepted, pose → (6088, 2760), jump 2,522 mm |
| 16:10:50 | (6071, 3066) | **45.5 s** | tag 15 accepted, pose → (4681, 1934), jump 1,792 mm |

At 16:08:17 the same tag-15 solution was still inside the 30 s window and was
correctly rejected:

```
tag16h5, 15: jump 861 mm / 0.21 rad from predicted pose
```

After the age passed 30 s, the 16:08:41 scan reported `large relocation needs
another consistent scan`; the 16:08:45 scan produced the same wrong solution and
confirmed it at 16:08:46. The wrong solution is **repeatable**, so the two-scan
confirmation passes.

### Low reprojection error cannot catch it

The wrong solutions have very low reprojection error because the tag corners fit
well; the error is in the pose branching, not the corner fit. Examples:

* 16:08:45 tag-15 solution: range 2057 mm, `pose_error` 0.82 → accepted.
* 16:11:24, robot stationary: range moved 2444 → 3290 mm, `pose_error` 0.03.
* 16:13:36: range spread 1198–1509 mm, `pose_error` 64.7–127.3.

`max_reprojection_error = 10` therefore does not reject these.

### The range is right; the bearing is wrong

At 16:08:40 tag 15 was measured at **2079.7 mm**. The pose propagated from the
last accepted tag was (5674.2, 1997.9), heading −0.4796 rad. With the camera
107 mm forward of the robot origin, the camera was at (5769, 1949); the
camera-to-tag distance to the surveyed landmark (7730, 1237) is **2086.4 mm**.
That is a 0.3 % agreement. The tag **range** was correct. The accepted pose
(5933, 312) put the robot on the wrong side of the tag, so the **bearing /
orientation branch** was wrong.

The same 107 mm camera offset checks out at the final stop: robot (7488, 1257),
heading −0.208 rad → camera (7593, 1235) → 137.0 mm to the tag, measured
136.5 mm.

This is the classic planar-tag two-fold pose ambiguity, made worse by the small
tag and the oblique/far view. It is not a range-scale error.

### Stale poses stay “localized”

`max_localization_age = 900` keeps `localized=True` for 15 minutes. At 16:08:41
the pose was 37 s old and still reported `localized: True`. Navigation would
continue to trust a stale or teleported pose during that window.

## 5. Odometry scale: correcting the earlier +9.8 % claim

`roomberry_control.py` integrates the **signed** encoder distance into `_distance`
and accumulates `_travelled_distance += abs(distance_delta)`. The localizer gets
`state['distance']` (signed); `travelled_distance_mm` is only the absolute path
length used by the map/log.

The tile sweep contained 12 moves between the 13 scan stops from 16:03:49 to
16:13:27. Per move:

| metric | mean | median | sd | 304.8 / mean |
|---|---:|---:|---:|---:|
| signed `distance_mm` | **−288.6 mm** | −292.0 mm | 11.2 mm | **1.056** |
| absolute `travelled_distance_mm` | **336.0 mm** | 328.2 mm | 29.9 mm | 0.907 |

The absolute metric is inflated by the forward/back correction at each stop.
Example, 16:03:49 → 16:04:38:

* reverse from −285.2 to −588.2 mm
* forward correction to −577.7 mm
* signed net = **−292.5 mm**
* absolute travelled = **+313.4 mm**

So the earlier “+9.8 % odometry” figure is an artifact of using the absolute path
length. The signed distance is the right scale reference, and it reads about
**5 % short** of a 304.8 mm tile (scale 1.056). That is consistent across the 12
moves (sd 3.9 %), which points to a real systematic bias rather than random
stopping error — but it still assumes each move was exactly one tile and that the
tile pitch is 304.8 mm.

**Do not apply the 1.056 correction yet.** Measure the actual gap-to-gap pitch
with a tape and run a straight 5-tile (1,524 mm) forward-and-back test. If the
signed distance is consistently ~5 % short, multiply `ROBOT.TICK_TO_DISTANCE`
accordingly (currently `0.444565 mm/tick`, wheel diameter 72 mm, wheelbase
235 mm). A 5 % error is plausible from wheel wear or an effective rolling radius
of ~75.6 mm instead of 72 mm.

## 6. Tag range and `fx`: correcting the earlier ~18 % claim

The earlier estimate compared tag-range **changes** to one-tile moves and
concluded the range under-reported by ~18 %, implying `fx` should be ~1.2×.
That inference is not valid:

1. The robot was **reversing** for most of the sweep (`distance_mm` is negative
   from 16:03 onward), and the moves were not straight toward the tag.
2. The change in tag range is the **projection** of the move onto the tag bearing,
   not the move distance. A 304.8 mm move at 30° to the bearing changes the range
   by only 264 mm; the observed ~251 mm is in that range.
3. The tag range and the fused pose are both derived from the same PnP result, so
   comparing them is circular.

The independent check in §4 (odometry-propagated pose vs measured tag range at
2.08 m, 0.3 % agreement) shows the **range scale is correct** at 2 m. A 1.2× `fx`
error would have produced ~2.5 m, not 2.08 m.

**Conclusion: leave `fx`, `fy`, `cx`, `cy` alone.** The long-range problem is the
pose branch, not the intrinsics or the tag size. If more range margin is wanted,
the productive changes are a larger tag and/or higher capture resolution, not an
intrinsics fudge.

## 7. GroundHog behaviour

NavLink logged 10,900 ground packets, 10,922 health packets and 1,088 compass
packets with **0 malformed**. GroundHog remains advisory and supplied no pose.

### Lock quality depends on motion

| Metric | Value |
|---|---|
| Valid ground packets | 10,375 / 10,900 = **95.18 %** |
| Stale: fit failed (reason 7) | 261 |
| Stale: stale frame (reason 4) | 256 |
| Stale: IMU/time (reason 3) | 8 |
| Valid while **stationary** | 8,948 / 9,041 = **99.0 %** |
| Valid while **moving** | 1,427 / 1,859 = **76.8 %** |
| Continuity segments | **420** |
| Segments shorter than 1 s | 356 |
| Continuity changes while moving / stationary | 360 / 59 |

The robot was actually moving for only ~17 % of packet time. The high overall
95 % therefore mostly reflects a parked robot: as soon as it drives, roughly one
packet in four is stale. GroundHog is not a continuous track; it is a series of
short locks separated by dropouts.

### Scale is good when locked; the path is short because of gaps

Within a single continuity segment GroundHog matches odometry closely:

| Continuity | Window | GH path | Odom (signed/travelled) | Ratio |
|---|---|---|---|---|
| 347 | 16:15:51–16:16:05 | 611.8 mm | 609.5 / 612.1 mm | ~1.00 |
| 345 | — | 154.6 mm | 150.9 mm | 1.02 |
| 112 | — | 99.6 mm | 99.4 mm | 1.00 |
| 115 | — | 177.4 mm | 163.8 mm | 1.08 |
| 397 | — | 109.8 mm | 115.4 mm | 0.95 |

Across the whole session it recorded **6,355.9 mm** against **9,549 mm** of
odometry path (**66.6 %**). There were **387 gaps >150 ms** between valid
packets, including **2.41 s** at 16:09:06→16:09:08 and **2.00 s** at
16:18:57→16:18:59. The missing distance is in those gaps, not in a scale error.
The final span (c=404, 16:16:52–16:18:51) measured 218.1 mm path vs 221.7 mm
odometry (0.98) with only 41.8 mm net displacement — consistent with the
back-and-forth nudging.

### The bump events are nudges, starts/stops and the carpet threshold

GroundHog counted **26 bump events**: **20 while stationary**, **6 while
moving**, and **21 within 15 s after a scan stop**.

* **Moving bumps are drive transients, not floor impacts.** They occur at drive
  start/stop/turn, with commanded wheel speeds of ±19–50 mm/s:
  16:13:34.926 (0.51 g, −50/−50), 16:13:35.774 (0.47 g, −50/−50),
  16:14:18.921 (0.43 g, 27/27), 16:14:20.204 (0.34 g, 50/50),
  16:16:14.134 (0.34 g, 27/27), 16:16:29.498 (0.33 g, 19/−19).
* **Stationary bumps are you repositioning the robot.** They cluster a few
  seconds after each scan stop; the largest is **1.147 g at 16:13:01.914**,
  followed by **0.801 g at 16:09:16.698** and **0.771 g at 16:05:11.354**.
  This is exactly the manual-nudge pattern, not a rough floor.
* **The final pair is the carpet threshold.** At **16:18:51.918** the robot
  latched both wheel-drop sensors plus the right cliff sensor; GroundHog
  recorded **0.719 g at 16:18:51.967** — the same jolt. The **0.997 g at
  16:19:00.997** is the subsequent lift/handling. So the threshold event did
  register, as expected.
* There is **no evidence of the removed carpet runner**. No bump occurs while
  driving across open tile; everything is either a command transient or a
  stationary nudge.

The detector is an impact heuristic (jerk on the accelerometer), not a
floor-contact or proximity sensor, so 0.3 g drive starts are expected.

### Phone load

Capture was 480×640. App CPU averaged **79.4 %** (median 78.3 %, max 87.7 %),
and `processing_us` median was **39.1 ms**, p95 **47.4 ms**, max **92.7 ms** at
a ~10 Hz packet rate. Thermal state was nominal/fair/serious on
5,170/3,306/2,446 packets, i.e. serious for ~22 % of the run. Sustained CPU and
thermal pressure is plausibly part of the stale-frame losses while moving.

**Conclusion for use:** GroundHog is a good short-window motion cross-check
while continuity is intact, but it must not be used as a distance or pose
source. Do not integrate its path without filling the gaps; do not feed it into
the localizer.

## 8. Recommendations, in order

### Positioning / filter

1. **Never let a single tag make a large correction.** When only one tag is
   accepted, compare the candidate pose with the odometry-propagated pose and
   reject if the disagreement exceeds a motion-aware bound, e.g.
   `max(500 mm, 1.5 × |signed odometry since the last accepted tag| + 150 mm)`
   and a matching heading bound. At 16:08:46 the odometry-propagated pose and the
   candidate differed by 1.7 m; this gate would have rejected it.
2. **Do not let a rejected scan disable the gate.** Apply the gate on every
   scan, so a run of rejected scans cannot unlock the next bad solution.
   Keep the “relocation after a long outage” path, but require stronger
   evidence for it (two different tags, or a short-range tag). *(Implemented.)*
3. **Resolve the planar ambiguity with the known tag pose.** The landmark's
   `world_from_tag` is known; use it (and/or the odometry prediction) to choose
   between the two IPPE/homography solutions instead of accepting the first one.
   Reject solutions whose implied tag normal points away from the camera.
   *(Implemented for the mounting-plane test.)*
4. **Restrict tag 15 to short range.** Use it for final approach below ~1.2 m.
   Beyond ~1.5 m, require a second tag or a larger target. A 57.5 mm tag is only
   ~18 px at 2 m.
5. **Shorten `max_localization_age`.** 900 s is too long for a pose that can be
   teleported; consider 10–30 s for navigation decisions, with an explicit
   “stale” state.
6. **Keep GroundHog advisory.** Use its short-window path only as a cross-check
   while `continuity` is intact; never feed it into the pose filter or a distance
   total. Its 33 % path shortfall is dropped frames, and its bump events include
   drive starts/stops and manual nudges.

### Calibration

7. **Measure the tile pitch** (gap center to gap center) with a tape. Confirm it
   is 304.8 mm, not 300 mm or 307 mm.
8. **Straight 5-tile run** along a gap, forward and back, with a scan at each gap.
   Compare signed `distance_mm` to the tape. Apply the scale only if it is
   consistent in both directions.
9. **Dedicated tag-range/fx test** if desired: tag 15 centred, marks at 0.5, 1.0,
   1.5 and 2.0 m, camera axis aligned with the tag normal. Compare range to the
   tape. Do not change `fx` from a curved-path test.

### Map presentation

10. **Do not draw the previous session's trail by default.** Start the render at
    `trail_session_start`, or only draw the old trail on explicit request.
11. **Mark or drop relocation segments.** Colour segments that contain a
    >275 mm jump differently (e.g. red), or omit them, and reset the trail
    segment on an accepted relocation. This makes a bad pose immediately visible
    instead of looking like a wall.
12. **Do not resume cleaning/planner work until the gate and scale tests pass.**
    The planner needs a pose that does not teleport by metres.

## 9. Next verification run

1. Ground the robot, then `GET /roomba/?op=restart_oi`, then
   `_change_mode&mode=2` (the robot is wheel-drop latched from 16:18:51).
2. Tape-measure the tile pitch and the tag-15 position/size.
3. Straight 5-tile run along a gap, stopping and scanning at every gap; keep the
   last three post-nudge scans per stop.
4. Approach tag 15 head-on from 2 m to 0.2 m in 0.25 m steps; record range and
   pose at each step.
5. Repeat the tile sweep and confirm there are no accepted poses more than
   ~500 mm from the odometry prediction.
6. Only then return to cleaning/planner work.

## Appendix: code changes in this pass

Scan gating (implemented earlier on 2026-11-02):

* Tag 15 landmark Y updated `1.18 → 1.237 m` in `roomberry/autonomy.json`.
* `scan_pause()` no longer returns early when `oi_stopped`.
* A scan start now forces a real soft-stop.
* `RoomberryCommandArbiter` rejects drive commands while a scan is active; stops
  and zero-motion commands remain allowed.
* The scan gate is cleared in `scan_complete()`.

Position filter and map presentation (implemented after this analysis):

* The jump gate now runs on every scan and uses a motion-aware bound
  `max(500 mm, 1.5 × |signed odometry since the last accepted tag| + 150 mm)`.
  A single distant tag can no longer teleport the pose.
* Large corrections after a long accepted-tag outage need either two distinct
  tags or a tag within `relocation_max_tag_distance_m` (1.2 m), and still need
  two consistent scans.
* Tag 15 has `max_tag_distance_m: 1.2` in its landmark entry.
* `max_localization_age` reduced from 900 s to 30 s.
* An estimate behind the surveyed tag's mounting plane is rejected using the
  known `world_from_tag` normal, which discards the impossible planar branch.
* The pose result reports `relocated` so callers can distinguish a confirmed
  relocation from ordinary tracking.
* Map rendering hides the previous session's trail unless explicitly requested
  and draws segments after a >275 mm jump in red.
* Localization, map-image, mission, control and queued-control tests pass
  (217 tests in the focused suite).

The odometry scale correction is deliberately **not** applied until the tape
test confirms the tile pitch in both directions. No cleaning/planner changes
were made. The Pi deployment/restart is not confirmed in this workspace.

## Appendix: overhead ground-truth harness

Added after this analysis, to remove the manual tape-and-eyeball step:

* `roomberry/roomberry_overhead.py` — tile-grid homography, colour-marker
  detection, marker pose, ffmpeg video decode, track/wheel comparison, and
  stop-to-stop leg splitting. Depends only on numpy and Pillow.
* `roomberry/tools/overhead-track.py` — `frame`, `calibrate` (click four tile
  intersections with a magnifier), `check` (grid overlay), `swatch`, `track`,
  `legs`, and `compare`.
* `roomberry/docs/overhead-ground-truth.md` — camera setup, marker rig,
  recording protocol, commands, acceptance criteria, and failure modes.

How it settles the one-tile question:

* `legs --expected-tiles 1` reports the actual grid distance between every pair
  of scan stops. If the legs are 304.8 mm, the robot really moved one tile and
  the only correction is the wheel scale. If they are systematically ~289 mm,
  the robot did not reach the next tile and the earlier `1.056` ratio was
  partly a stopping-point artefact.
* `compare` aligns the overhead track with the Pi sensor log by speed
  correlation and reports the wheel-scale ratio (`overhead / wheels`) with a
  `PASS`/`CHECK` verdict at 1 %.

The synthetic end-to-end check moved the robot four tiles (1219.2 mm) and
recovered a 5 %-short wheel log as a 1.0526 scale, so the pipeline arithmetic
is verified. The real calibration still needs the overhead recording and the
tape-measured marker baseline. Changing camera intrinsics invalidates tag
landmarks but not the wheel scale, because the tile grid supplies the metric
reference.
