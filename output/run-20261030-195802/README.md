# Run 2026-10-30 19:58:02

Roomba cumulative travel before pickup: 1217.8 cm. User reports most travel was on hard floor; logs do not identify every floor transition. Navigation positions below include AprilTag fixes and phone aiding, rather than raw wheel odometry alone. The comparison holds the phone room transform fixed at the retreat tag fix (19:58:52), uses the deployed 93.6-degree mounting yaw and measured lens offset, and corrects packet timing. Neither source is surveyed ground truth.

| Point | Roomba travel (cm) | Position disagreement (cm) | Disagreement / travel |
|---|---:|---:|---:|
| Approaching tag 2, 19:59:06 | 132.5 | 14.7 | 11.1% |
| After tag 2 fix, 19:59:21 | 134.2 | 28.8 | 21.5% |
| 19:59:44 | 228.3 | 27.1 | 11.9% |
| 20:02:12 | 1030.0 | 40.3 | 3.9% |
| Before tag 15 fix, 20:02:47 | 1091.4 | 19.6 | 1.8% |
| First accepted tag 15 fix, 20:02:50 | 1091.4 | 137.5 | 12.6% |
| Second tag 15 fix, 20:03:17 | 1105.4 | 152.2 | 13.8% |
| Stationary before pickup | 1217.8 | 158.2 | 13.0% |

Travel includes absolute forward and reverse center displacement, not pure rotational wheel travel. Percentages divide separation by travel since recording began. A falling percentage can reflect a growing denominator. Zero at the retreat anchor is imposed by alignment.

## Correction behavior

All 6303 phone packets have valid poses, with one session/alignment and no sequence discontinuities. Median feature count 9. Maximum excess receipt delay 1.508 seconds. Phone aiding was active and its logged accumulated step lengths reached 93.82 cm (this is a sum of correction magnitudes, not net displacement or proven accuracy improvement). The largest logged live residual was 58.23 cm at 20:01:53 after 965.2 cm of travel. The 5 mm/s correction could not keep that residual small during this leg.

At 20:02:50 the accepted tag 15 fix changed robot position from approximately (5697,172) to (6332,1244) mm, about 1.25 m. It passed a two-scan large-relocation confirmation. Phone position stayed continuous. At 20:03:17 another tag 15 fix moved the estimate about 29 cm relative to its immediately preceding logged scan pose. These tag updates reset the phone-to-room anchor too. Consequently the live residual returned near zero while the fixed-reference disagreement grew to 1.4–1.5 m. Consistent tag detection does not independently validate the room pose/calibration, and phone drift remains possible. Investigate the tag 15 room transform and pose calibration before increasing phone correction gain.

The last correction log was at 20:04:12 (live residual 1.53 cm). Packet bursts around 20:04:13–19 include frame ages over the 250 ms correction threshold, despite valid AR tracking. The implementation drops its anchor on a stale observation and needs a new accepted tag to resume. No later anchor or correction is logged. Exact disable time/reason is not logged; stale-data suspension is the likely explanation.

## No route

The recovery cleared two local mapped cells at 20:04:01. A bumper contact at 20:04:05 mapped an obstacle near (5582,1441) mm. Repeated no-route waits began at 20:04:07 and continued until pickup at 20:07:37. The same recovery permits only one map reset. Offline replay of the final saved map at the final logged pose has no route to (3100,1450) mm; clearing one cell within 500 mm restores a 31-cell path. This identifies a local map blockage, not proof that the physical obstacle can be ignored. No robot code was changed during this analysis.

## Scan/serial performance

15 full scans averaged 3.540 seconds (2.972–4.065 seconds); detection averaged 1.275 seconds. 31 captures skipping detection averaged 0.510 seconds. Two sensor polls failed: 19:58:06 before scanning and 20:02:53 after the tag 15 scan had completed.

Artifacts: analyze.py regenerates the trajectory, fixed-reference CSV/table and summary. analyze-corrections.py also extracts logged live residuals and tag anchors. mission.log and map-state.json preserve the analyzed inputs; binary phone/sensor inputs remain under roomberry/logs.
