<!-- @(#)approach-rocking.md 3.2.analysis.9 2026/11/12 15:44:40 -->
# Tag15 final-approach rocking

Approach interval15:29:05–15:29:46 shows repeated alternating left/right
pivots and stop/settle phases. Straight translation is commanded forward20mm/s;
pivot wheel targets are opposite-sign40mm/s. No straight reverse was commanded
in this phase. The visual back-and-forth is consistent with yaw hunting.

Low-speed mismatch is present: among35encoder-speed windows with applied
forward20mm/s unchanged across three sensor samples, measured centre speed
p10/median/p90is39.36/41.60/44.95mm/s. Speeds use cumulative encoder-derived
position difference divided by the two-poll time span, not the Roomba requested
velocity fields. Those requested fields are command telemetry, not measurements.
Thus this is approximately twice the intended low straight speed; it does not
prove every40mm/s pivot runs twice as fast. Logical pivot intervals include
ramp-up and braking; their measured wheel-equivalent speeds are not steady-state.

Example15:29:06.439: stop command completes in6ms. Logged heading error at the
stop decision is+1.89deg, then-4.68deg during settling, provoking a reverse
correction. The next opposite correction similarly crosses the target and
reverses again. Actual gyro rotation after the first stop-decision log until
settled15:29:07.033 is+2.11deg,AR+2.01deg. Second stop-to-next-pivot window
15:29:08.637–15:29:09.034 gyro-2.51deg,AR-2.51deg. Overshoot is physical;
the entire6.57deg logged error swing must not be described as post-brake coast:
sensor snapshot/decision timing accounts for part of it.

The controller uses5deg to enter pivot mode and2deg to remain turning, at a
200ms mission period. Some later reversals happen inside the wider5deg entry
band because the turning state persists. SettledTurn safely waits for quiet
before reversing, but that guard does not prevent overshoot or hunting.

Conclusion: slow-speed mapping contributes, with real post-stop rotation and
feedback timing. It is not explained by wheel-heading bias alone. Next control
work should calibrate the approach speed and use earlier braking/shorter bounded
turn pulses, with appropriate direction-entry hysteresis. No controller changes
were made for this read-only diagnosis.
