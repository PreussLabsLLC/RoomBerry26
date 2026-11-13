<!-- @(#)report.md 3.1.wall.6 2026/11/08 19:00:00 -->
# DIN plug snag during WALL approach

Source: uploaded application log and
roomberry/logs/sensors/roomberry-sensors-20261108-185925.csv,463 rows spanning
18:59:25.763–19:00:36.143. User identified the contact as the DIN plug catching
on kitchen cabinet doors above the bumper, and has added wood planks to prevent
the robot entering underneath. This explains why front bumper contact was not
reported; it is not evidence of a failed bumper switch.

## Recorded behavior

- Tag16 anchor qualified18:59:52.547; left90.13 encoder degrees, forward195.61mm,
  right43.21degrees; acquisition began19:00:07.616 at220.51mm session distance.
- Acquisition signal stayed0–24, below target30. No IR candidate/alignment
  event occurred in this run. The right sensor was not looking at an acquired
  side wall when the DIN plug snagged ahead.
- Both physical bumper bits, binary right light-bumper bit, hard-hazard and
  safety-latch flags remained zero throughout. There was no bumper event for
  either the I/O owner or mission to react to.
- Encoder translation flattened at572.24mm session distance around19:00:18.18.
  Both wheel currents reached roughly0.77–0.81A while requested/applied forward
  commands continued. At19:00:20.163, WALL's two-second no-progress check aborted.
  The first subsequent sensor row showing zero applied speeds is19:00:20.355.
- Motion against the snag therefore lasted until the existing stall timeout;
  no retreat or left-turn recovery occurred. Encoders cannot certify body travel
  or wheel slip, but the high load/no-progress interval is clear.

## wall.6 changes

The serial owner now latches a WALL-specific stop on the first polled physical
bumper assertion. Even a transient contact blocks new forward or turn commands
until the coordinator has reversed clear and acknowledged a stop. Existing
cliff/wheel-drop/stale-sensor protections are preserved and take priority.

There is also a narrowly scoped forward-stall fallback for non-bumper snags:
both wheels commanded forward, both currents>=350mA, and absolute translational
encoder delta<0.5mm per new poll, sustained for200ms. Reverse, turns, moving
encoders and disabled WALL mode do not qualify. This reports stalled drive,
not a physical bumper event. Replaying the recorded values triggers at
19:00:18.505,0.322seconds after the first flat/high-load sample, about1.66seconds
before the original abort. This is software replay timing, not a physical trial.

In WALL acquisition/alignment/following, either event first stops, then reverses
at25mm/s for approximately30mm. It requires clear bumpers/safety and another
acknowledged stop before unlatching, turning left15degrees and beginning another
approach. Retreat is limited to50mm/5seconds if the bumper remains held. Contact
recovery shares the four-retry budget and overall mission limits. Contact in
initial departure aborts; a hard hazard never initiates automatic recovery.

Target30 right light-bumper units and alternating WALL/raw-value LED remain.
The physical DIN/cabinet clearance is not measured by this target. The operator's
wood planks are a physical change, not validated by these pre-change logs.

Implementation is local only; no deployment or robot motion was performed.
