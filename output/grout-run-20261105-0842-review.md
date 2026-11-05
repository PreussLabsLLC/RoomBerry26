# November 5, 08:42–08:47 — phantom thresholds, pose disagreement and short final stop

Analysis only. Sources: roomberry/logs/roomberry.log, sensor CSV and NavLink
binary from 20261105-084144. User confirms a phantom threshold bump and final
stop about 50 mm in front of tag 15.

## Guard fix and outbound tracking

The shared settling guard completed 24 measured settling phases. No wrong-way
or settling-timeout abort occurred. Logs show reference polls after dispatch.
The repeated guard abort from previous runs did not recur.

Both outbound legs stayed locked throughout their recorded travel. First:
58 samples at -100 base, heading -2.19..+1.64 degrees, camera-line error
-0.07..+5.23 mm. Second: 65 samples, error -5.02..+3.21 mm, heading range spans
4.92 degrees relative to its new start. Frame ages remained <=176 ms. These
are short legs and do not establish full-route tracking reliability.

First threshold classification: 08:42:10.402 at 1186.2 mm, settled 1194.3 mm;
second: 08:44:02.850 at 1348.2 mm, settled 1363.9 mm. User confirms phantom
contact before the actual threshold. Both were phone-only classifications.
Event #8 peak: 3804 mm/s² (~0.388 g); event #17: 3844 (~0.392 g). No front
bumper contact at either event. Three other phone bumps were correctly consumed
by the 150 ms speed-change filter. These later phantom events were outside its
matching windows. Timing suppression alone cannot identify threshold contact.

The shared iPhone BumpDetector uses user acceleration (gravity removed):
>=0.25 g with jerk >=40 g/s; or >=0.6 g with jerk >=15 g/s; or >=1.2 g alone.
Both ~0.39 g threshold episodes therefore qualify through the low-amplitude,
high-jerk branch. It is an impact-like motion detector, not a contact sensor.
No threshold settings were changed in this review.

## Automatic returns

First return accepted later tag checkpoints, including two agreeing final poses,
and reached its estimated contact zone. It stopped at 08:43:20 on the approach
travel/range guard with no bumper contact. Last moving estimate was center gap
124.5 mm and lateral displacement 18.1 mm from tag normal; configured robot
radius is 174 mm. Internally it thought the front bumper had passed the tag plane.

Second return accepted tag poses at the 2 m and 1.5 m checkpoints but stopped
on another phone impact at 08:44:18.771. Event #18 peak was 3680 mm/s² (~0.375 g).
It occurred while moving at +100 base, not during an off-threshold descent in
this phantom-threshold run. No bumper contact at that time.

## Why tag homing looked erratic

The first explicit return localized from tag 15 and followed the existing
cell-center route. Saved-map replay gives cells (75,17) -> (76,16) -> (77,15)
-> (78,14) -> (79,13) -> (80,12) -> (81,12) -> (82,13). Geometric polyline length
~853 mm versus ~682 mm directly to staging; the direct swept footprint checked
clear. Equal-cost diagonal BFS and unsmoothed waypoints still cause unnecessary
bends and repeated turn/settle cycles. The guard now allows these turns to finish;
it does not optimize the route.

At the final scan, three vision poses agreed within about 15 mm/1.4 degrees,
but their headings were 13.3–14.7 degrees away from the wheel-projected heading.
The strict 8-degree innovation gate rejected all three and stopped at 08:46:03.886.
Position innovation was only 42–45 mm. This is a heading-estimation disagreement;
these logs alone do not identify whether vision bias, floor slip, encoder yaw
scale or another calibration is responsible. Do not simply assume vision or
odometry is ground truth.

## Final retry and the observed 50 mm shortfall

Second explicit homing accepted a fresh initial pose, reoriented, then confirmed
final poses near (7103.3,1195.9) mm with heading 1.39 degrees. It advanced about
0.50 m at a requested 20 mm/s. Standalone tag homing still has its own 50 travel/
20 final settings; the 100/30 experiment applies to grout runs.

At the last moving sample the estimated center gap was 131.2 mm and lateral
26.1 mm, almost exactly the intended lateral offset. The next tick reached the
radius-minus-50 bound (124 mm), stopping at 08:47:17.172. Thus the position model
thought the bumper had passed the tag plane by at least 50 mm, with no bumper
signal. User observation: about 50 mm physically short. If that is front-bumper
clearance, the accumulated position estimate is roughly 0.1 m too far forward.
The numerical travel limit was not 750 mm; the range/plane bound fired first.

This is not evidence that it needed more allowed travel. Candidate causes are
encoder-to-ground travel scale/slip, biased tag range, camera-to-robot transform,
or contact-plane/body-radius geometry. A single final stationary rescan after
stopping would help separate them: vision gap versus wheel projection, alongside
an actual bumper-to-tag measurement. Repeatedly enlarging the travel bound would
hide the disagreement instead of measuring it.

## Priorities

1. Require a plausible threshold location or independent cue before treating a
   generic IMU episode as threshold arrival. Ambiguous impacts can stop without
   automatically switching to return.
2. Measure the near-tag range/encoder/contact-geometry discrepancy; re-localize
   during final approach rather than relying on a single half-meter projection.
3. Shortcut clear homing routes and retain explicit diagnostics for rejected
   heading updates. Guard removal is no longer the blocker in this session.

One sensor serial timeout and one display write timeout occurred and recovered;
neither was the logged reason for the final stops. No control changes made.
