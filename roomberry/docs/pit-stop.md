# Suspended-wheel pit-stop test

Build **3.1.pit.3**. Standalone Pi utility; no iPhone or camera required. Normal
Roomberry navigation and its safety rules are unchanged.

The default test contains 168 stages, nominally **17 minutes 58 seconds**, with a
hard **20-minute** runtime limit checked independently by the serial owner.
Slow execution may reach that limit before all stages finish; the report says
aborted rather than claiming a complete test. A short smoke profile takes about
54 seconds.

## Setup and first run

Support the chassis securely on a box with **both drive wheels fully hanging**,
free of the sides. Leave the caster alone. Remove charger/dock power connections.
Keep the physical power control accessible. This is a bench test in **Full OI
mode**: firmware cliff and wheel-drop motion protection is disabled. Do not run
it on the floor. The runner requires both wheel-drop bits throughout. Cliff and stasis readings
are recorded; cliff changes produce events without aborting the bench test.

From the project root on the Pi, stop Roomberry, then inspect the schedule:

```sh
sudo systemctl stop roomberry.service
python3 roomberry/roomberry_pitstop.py
```

The default is a dry-run: it does not open serial, change LEDs, or create files.
It prints every left/right velocity command and approximate stage start time.

For the first physical check use the short profile:

```sh
sudo python3 roomberry/roomberry_pitstop.py --run --profile smoke
```

Then run the default test:

```sh
sudo python3 roomberry/roomberry_pitstop.py --run
```

Wake the robot manually before running; an empty sensor response does not
trigger an automatic wake/reset. Each live invocation requires an interactive terminal and typing `WHEELS FREE`.
No saved authorization, auto-rearm, wake/reset sequence, or automatic retry.
The default port is `/dev/serial0` at 115200 baud; `--port` and `--baud` can
select another configured interface. The runner refuses an active Roomberry
service or another visible serial owner and requests an exclusive serial lock.
Run as root on the Pi so the process-descriptor check can see other users.
Other software must not open the device during the test; ordinary processes
that ignore advisory serial locks cannot be fenced out by this utility.

The LEDs display `pit` while the bench owner is active. **Any robot button**,
Ctrl-C, or SIGTERM stops the test. The runner commands zero, checks encoder
settling, clears the display, and restores Passive mode on exit. Inspect
`stop_verified` and `cleanup_errors` in the manifest after an abnormal exit.
A 600 ms sequence heartbeat is checked by a separate I/O thread, so a stalled
sequence/file writer causes a stop. Complete process death, SIGKILL, serial
loss, or power failure can prevent a software stop: use physical power control
if the wheels keep running. The program never claims guaranteed hardware stop.

Restart the normal service only after the bench test has exited and the robot
is back on the floor:

```sh
sudo systemctl start roomberry.service
```

## What runs

- Eight low-speed smoke stages at 20 mm/s.
- Eight patterns at each of 15, 20, 25, 30, 40, 50, 75, 100, 150, 200,
  300, 400 and 500 mm/s: each wheel alone forward/reverse, both forward/reverse,
  and both opposite directions.
- Two additional passes at 20/30/50 mm/s for repeatability.
- Eight asymmetric wheel pairs including 30/50, 50/30, 45/54 and 54/45.

Each 6.4-second slot includes a stopped baseline, 0.5 seconds of startup plus
2 seconds holding the command, then zero and measured settling. Speed must
remain within 10 nominal mm/s of zero for at least 0.5 seconds before proceeding.
Failure to settle within three seconds aborts. At this sampling resolution the
quiet threshold allows approximately one encoder tick per 50 ms sample; it is
not a precision stop-distance specification. Reversals always pass through zero.
There is no every-integer-speed or full pair-matrix sweep in this first version.

## Sensor recording and reports

Samples target 20 Hz. Five consecutive reads taking over 45 ms select a 10 Hz
poll period; actual intervals and configured period are recorded. Serial queries
never overlap. Short/implausible packets, stale data, mode loss, a powered charger source,
active charging (states 1–3), charging fault (state 5), low
battery, battery temperature >=50 C, any overcurrent bit, bumper/button contact,
or either drive wheel losing its dropped state stop the test. Cliff changes are
recorded as `cliff_change` events and do not abort suspended-wheel testing. Low battery means voltage
below 12 V or reported charge below 15% of capacity.
Charging state 4 means waiting; when no powered source is reported it is allowed.
Every charging abort includes source bits, named charging state and battery
current. A waiting/fault state alone is not described as a charger attachment.
State definitions: [iRobot OI specification, packets 21 and 34](https://www.usna.edu/Users/weaprcon/esposito/_files/roomba.matlab/MTIC2/Create2_Open_Interface_AUG_15_2015.pdf).

A new directory under `output/pit-<timestamp>/` contains:

- `manifest.json`: schedule, outcome, conversion constants, startup text observed
  without resetting, final stop verification and cleanup errors.
  `fault_sensor_sample`/`fault_packet_hex` preserve the reading at abort, before
  cleanup can replace it; `last_sensor_sample` is the final decoded reading.
- `samples.csv`: monotonic/wall timestamps, sensor read duration, requested and
  reported wheel commands, raw encoders and wrap-safe speed, motor currents,
  battery state, drop/cliff/bump/stasis bits, and full raw group-100 packet hex.
- `events.jsonl`: phase changes, command/query bytes and transmission timestamps,
  faults/outcome. Serial-send events are saved after the owner stops; a hard
  process kill can lose them. Sensor rows flush on phase changes.
- `stage-summary.csv`: measured mean speed/error/variability, peak motor current,
  startup delay, stop delay and coast ticks, separately for each wheel.
- `report.md` and, when matplotlib is installed, `telemetry.png`.

Startup/stop delay uses the 10 mm/s motion threshold. Startup below that threshold is unmeasurable and is left blank.
The 5 and 10 mm/s stages were removed after both produced zero encoder motion. Inactive-wheel mean
speed measures cross-motion; compare repeated, opposite-direction and paired
stages in the summary. Coast ticks include the first post-zero encoder interval,
which may contain up to one polling interval of motion before the command;
treat this as a sampled upper estimate, not exact mechanical coast. Requested-speed sensor fields are firmware reports,
not independently measured motion. Group 100 must be supported; unsupported or
short replies abort, with no synthesized fallback zeros. A firmware-returned
zero cannot alone establish whether a sensor is implemented correctly.

Unloaded encoders test drive regulation, sign, left/right imbalance and coast.
They do **not** measure tire slip, floor traction, chassis travel or chassis yaw.
No motion is inferred from a stationary caster's stasis reading.

## Safe local simulation

```sh
python3 roomberry/roomberry_pitstop.py --simulate --output output/pit-simulation
```

This runs the complete schedule with an accelerated synthetic motor model and
produces the same report files without accessing serial. Results and plot are
explicitly marked simulated. `--output` must be a new directory; existing
sessions are never overwritten. Plotting is optional: copy CSV files to a
computer with matplotlib if the Pi does not have it.

Implementation tests:

```sh
PYTHONPATH=roomberry:roomberry/irobot/tests python3 -m unittest roomberry_pitstop_test
```
