<!-- @(#)README.md 2.3.13 2026/10/28 20:00:00 -->
# Roomberry Utils

**Utils** contains several low-level utilities to inspect the roomba via serial interface.

## Examples:

- status.py:	run "python status.py | tee status.txt" to capture a bunch of sensor data
- version.py:	run "python version.py | tee version.txt" to capture Roomba startup messages

Stop the Roomberry service before running these utilities: only one process may own
the serial port. `version.py` sends START and RESET, captures up to 15 seconds of
boot output, then enters and verifies Safe mode. It sends no drive or beep commands.

Save a separate identity record for each robot:

```sh
python utils/version.py --output /tmp/roomba-600-a.json
```

The JSON includes the full release string, the parsed version, and the boot stream.
Unrecognized firmware is recorded as `null`; no firmware quirks are guessed.
`--port` and `--baud` override the serial defaults. Serial reset cannot guarantee
wake-up on every model; a robot that ignores serial while asleep may still require
a physical wake or a connected wake pin.

Roomberry now requests this reset sequence on each new serial connection, logs the
firmware identity, and exposes `firmware_version` and `firmware_release` through
`/status.json`. Startup verifies Safe mode, then restores Passive mode for idle physical button
input. Idle feedback enters verified Safe mode for the tone and restores Passive
mode afterward in one serialized operation. During an active mission, feedback
requires Safe mode and cannot rearm a robot that has left it. A wheel-drop
OI STOP remains suspended until explicit restart; ordinary polling never resets it.

The startup reset is implemented in `roomberry/roomberry_startup.py`, included by
`roomberry/tools/sync-up` through its `roomb*.py` pattern. It captures the boot
stream and closes its serial connection before the existing Create2 driver opens
the port. No updated driver constructor or installed library is required. Allow
up to 15 seconds for boot capture before the normal OI connection and Safe check.
