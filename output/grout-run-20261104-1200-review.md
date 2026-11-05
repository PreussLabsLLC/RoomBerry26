# November 4, 12:00 grout out-and-back review

Analysis only; no robot commands or control changes.

Sources: roomberry/logs/roomberry.log; sensors/roomberry-sensors-20261104-120011.csv; navlink/roomberry-navlink-20261104-120011-0000.bin, under roomberry/logs.

Outbound started 12:00:23.972 and ran without an intervening stop. Phone impact count advanced 2→3 at Pi receipt 12:01:40.601; the mission recorded threshold contact at 12:01:40.613 with 4624.327 mm outbound wheel travel. Braking settled at 4629.711 mm. This is 4.630 m / 15.19 ft of outbound center travel, including braking, using the current wheel scale. The impact-time value is within 0.7 mm of the provisional 4625 mm reference, but that agreement is not independent calibration evidence.

Return began 12:01:41.641 in Safe-mode GridRunner, at 20 mm/s because line detection was absent. Phone impact count advanced again, 3→4, at 12:01:42.396. The mission explicitly aborted at 12:01:42.427: "phone impact detected during return". Recorded impact peaks were approximately 0.271 g for threshold contact and 0.267 g for the later event. Telemetry establishes two detector events, not which physical objects or vibrations caused them. No Roomba bumper contact was recorded in this interval. This was a safety abort, not a wheel-progress timeout or a tag-scan stall. The robot had not reached its first return scan checkpoint.

Return motion, including braking, was approximately 24.0 mm. Final signed wheel distance was −4605.7 mm; cumulative absolute travel was 4653.7 mm (4.654 m / 15.27 ft). Thus the robot remained approximately 4.606 m along its wheel path from its starting position. A later web start at 12:02:49 ended with waiting timeout at 12:02:59 and added no travel.

Integrating signed sensor distance at midpoint wheel heading gives outbound endpoint displacement approximately (−4628.3, −27.8) mm relative to the original robot heading. Maximum lateral departure from that initial heading line was about 42.0 mm. Settled threshold heading was −2.30°. This is wheel-derived drift relative to the initial heading, not a surveyed deviation from the actual grout grid; wheel slip and initial alignment are not independently measured.

Camera offsets in outbound controller samples had median magnitude 17.7 mm, 95th percentile magnitude 26.4 mm, and initial magnitude 30.5 mm. A brief low-confidence near-threshold reading reached 77.1 mm (confidence 0.574); the last available reading was 17.1 mm (confidence 0.465). Near-threshold line loss prevents certifying the endpoint's actual grout offset. These camera offsets and wheel-derived displacement measure different things and should not be added together.

Follow-up: inspect whether the second impact was another physical threshold contact during withdrawal, chassis/phone vibration, or a detector event-splitting issue before changing the return impact guard. Logs alone cannot distinguish these causes.
