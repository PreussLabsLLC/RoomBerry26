<!-- @(#)CAPTAINSLOG.md 3.1 2026/11/02 17:40:00 -->
# Captains Log

## Stardate 26-11-02

### Discovered
- reviewed big pickle's analysis with focus on tracking down position disagreements between roomba odometry,
april tag scan results, and iphone tracking.
- recommendation was to tape a test track on the floor. Luckily my kitchen floor has built-in tracks: the tiles
consist of imperial 1 foot squares of unknown material with a hard surface, clear black gaps between tiles,
and built-in simulated dirt particles to support optical tracking.
- we have two iphone apps: StarLock using ARKit to track the ceiling, and GroundHog using some other kit to
correlate position (like an optical mouse). When turning the iphone towards the floor, StarLink still seems
to lock on and track. Earlier problems were drop-outs when running under chairs, tables, etc. - but the floor
should be visible at all times. Worth a try!

### Next
- prepare kitchen for manual tag scans from verified positions
- tag 15 in the kitchen has moved y +57 mm to align with a gap to follow for measurements. map needs to update.
- review manual steering of the robot to test positions and trigger tag scans
- perform and record tag scanning ativities

### Completed
- positioning filter hardened: motion-aware single-tag gate, rejected scans can no
  longer unlock the jump gate, planar branch check against the known tag pose,
  tag 15 limited to 1.2 m, `max_localization_age` reduced 900 s -> 30 s.
- map rendering hides the previous session by default and marks relocation
  segments in red.
- GroundHog reporting moved to its own queue (build 4) with stale-heartbeat
  reports instead of inventing displacement.
- analysis written to `output/positioning-analysis-20261102.md`.
- focused python suite: 258 tests OK.
- Next: publish the snapshot to GitHub, then tape-measure the tile pitch and run
  the straight five-tile test before trusting an odometry scale correction.


