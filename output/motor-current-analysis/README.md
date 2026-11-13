<!-- @(#)motor-current-analysis.md 2.3.8 2026/10/28 16:00:00 -->
# Motor current analysis: 2026-10-28, 14:20 run

Matched `roomberry.log` to `roomberry-sensors-20261028-142005.csv` using their shared local timestamps. No robot commands were sent and no runtime control code was changed.

- [Full run: commands, wheel currents, battery discharge and voltage](01-run-overview.png)
- [Responses around starts, stops, speed changes and direction changes](02-transition-responses.png)
- [Four largest excursions with individual samples and command traces](03-largest-spikes.png)
- [Typical transitions without nearby physical bumper contact](04-typical-transitions.png)
- [Aligned event table](aligned-events.csv), [summary statistics](summary.json), [excluded malformed sample](rejected-samples.csv)

## Findings

There are 13,209 valid sensor rows. The typical interval is 126 ms (about 8 Hz), with a 99th percentile of 160 ms and occasional longer gaps. The median delay from a logged transition to the first following CSV sample is 78 ms. Subsample electrical transients may be missed entirely; these plots show measured excursions, not true instantaneous peak currents.

The 805 raw command transitions include 118 stop/start pairs less than 150 ms apart. Those are grouped as 110 direction changes and eight same-command restart pulses, not counted as starts from physical rest. The raw command trace still shows the zero pulses. Remaining event counts are 280 starts, 280 stops and nine speed changes. A commanded zero does not prove the wheels physically stopped.

Current below means the larger absolute current of the two wheel motors, not their sum. Event peaks use samples in the first 0.6 seconds, truncated before the next transition.

| Transition | Median measured peak, A | Median peak without nearby bumper contact, A |
| --- | ---: | ---: |
| Start | 0.216 | 0.230 |
| Stop | 0.079 | 0.057 |
| Speed change | 0.153 | 0.153 |
| Direction change | 0.231 | 0.231 |

A stricter near-rest subset requires the recorded wheel currents in the preceding 200–20 ms to remain below 0.02 A and no nearby bumper contact. Its 53 starts have a median measured peak of 0.233 A. Later moving samples 0.6–1.5 seconds after non-contact starts have a median of 0.157 A. These are descriptive subsets, not a controlled motor experiment: speed, load, turning and floor surface differ.

The largest valid wheel currents were **0.781 A left** and **0.699 A right**. The four largest excursions separated by at least five seconds all coincided with physical bumper contact and a safety stop:

| Time | Left A | Right A |
| --- | ---: | ---: |
| 14:29:00.582 | 0.781 | 0.294 |
| 14:33:12.514 | 0.552 | 0.699 |
| 14:32:19.694 | 0.655 | 0.366 |
| 14:40:07.806 | 0.477 | 0.626 |

The sensor packet is acquired before the safety brake, but its CSV timestamp is assigned after that handling. These current samples therefore appear a few milliseconds after the stop log even though they triggered the stop. They are consistent with increased mechanical load at contact; they do **not** establish a braking-induced surge. Normal stops show current falling toward zero in the sampled response. Only nine speed changes were available, too few to generalize confidently.

No valid samples asserted wheel overcurrent. One malformed post-pickup row has OI mode 57, apparent motor currents of 29.556/24.948 A, and both overcurrent flags. The entire row was excluded because the OI mode is invalid; it must not be interpreted as a genuine electrical event.

## Interpretation limits

The plots reconstruct requested wheel velocities from accepted actuator logs and logged stop/safety events. The CSV requested-velocity fields were not used: they remained at 43/43 across starts, stops and turns. The command trace is not measured wheel velocity, and unlogged internal braking cannot be reconstructed. Log times are completion/notification times, not exact hardware transmission times. The response bands show variation between events, not confidence intervals. Bins use actual samples without interpolation, stop at neighboring transitions, and can contain different event subsets.

The recordings support a modest startup rise and much larger contact-associated excursions. They do not show a reproducible large surge from ordinary braking, and cannot rule out short braking or startup transients below the sampling resolution. A ramp comparison would require comparable surface/load runs with and without ramping; fast electrical peaks require faster current acquisition.

## Reproduce

From the repository root:

```bash
python roomberry/tools/analyze-motor-currents.py \
  --log roomberry/logs/roomberry.log \
  --sensors roomberry/logs/sensors/roomberry-sensors-20261028-142005.csv \
  --output output/motor-current-analysis
```

Requires NumPy and Matplotlib. Keep the matching log alongside the CSV: the next upload may replace `roomberry.log`.
