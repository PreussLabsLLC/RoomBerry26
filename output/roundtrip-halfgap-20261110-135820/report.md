<!-- @(#)report.md 3.2.analysis.4 2026/11/10 14:10:28 -->
# Half-second-gap run, 2026-11-10 13:58–14:07

- One serial write timeout event at14:01:23.312 while requesting the dedicated
  buttons packet18 during a stationary scan14:01:21.312–14:01:28.155. The
  traceback contains the text twice (raise statement and exception), not two
  events. It coincided with detection after the capture cool-off; temporal
  association does not establish CPU or scan causality. GridRunner aborted
  at14:01:23.507 on stale sensors/safety readiness. Other11scans no poll faults.
- Startup connection attempt at13:57:58.903 received0/1bytes and retried.
  One separate sensor short read72/80bytes at13:58:25.489, before first scan.
- Twelve scan results announced clear mapped tags; all12speech completions.
  Cool-offs requested0.500s, mostly measured500–517ms; last postarchive682ms.
  Cold scan16.227s; warm6.030–7.222s, median6.581s versus7.924s previously.
- Live map archive confirmed both wheel and iPhone trails and legend. Initial
  phone/tag16 alignment succeeded with6ms capture pairing. Screenshot at
  roomberry/logs/maps/roomberry-maps-20261110-135820-262688/
  map-20261110-140636-556878-000022.png. This archive snapshot predates the
  final scan's localization publication.
- One phone session,5434packets, all normal tracking, one sequence gap;
  median9features. Wheel travel9.061m. Offline initial-tag16-only alignment
  yields final phone error407mm/-3.87deg and wheel317mm/+12.25deg versus
  final tag. Final tag itself104mm/-8.22deg from the start. Stationary pairing
  checks passed. Final heading error improved on wheels versus prior20.88deg;
  phone position error improved from705mm, wheel position worsened from124mm.
- Retried tag15 approach reached final validated robot-centre range339.8mm,
  outside300mm, so stopped again at14:04:15.586. Spoken camera range23cm
  uses a different origin. Final tag innovation75.7mm. No successful arrival.
- Battery estimate jumped99.7%→62.4% at13:59:40.185 (126ms), charge2688→1682mAh
  while voltage remained14.667V. Finished60.5%. Current integration across the
  whole9minute recording gives58.3mAh consumed, not1064mAh. The abrupt change
  is inconsistent with literal physical discharge and suggests charge estimate
  recalculation or telemetry corruption; logs do not distinguish those causes.

Analysis script, metrics, tag checks, comparison plots and map preview accompany
this report. Raw recordings preserved; no controller/runtime changes.
