#!/usr/bin/env python3
# @(#) tof-distance.py 3.2.tof.3 2026/11/19 11:55:15
"""Print CJMCU-531 (VL53L1X) readings from Raspberry Pi I2C bus 1."""

import argparse
import time

import VL53L1X


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='Print one raw reading in millimeters.')
    args = parser.parse_args()
    sensor = VL53L1X.VL53L1X(i2c_bus=1, i2c_address=0x29)
    sensor.open()
    try:
        sensor.start_ranging(3)  # Long distance mode.
        try:
            while True:
                started = time.monotonic()
                distance_mm = sensor.get_distance()
                if args.once:
                    print(distance_mm, flush=True)
                    return
                reading = f"{distance_mm} mm" if distance_mm >= 0 else "No valid reading"
                print(reading, flush=True)
                time.sleep(max(0.0, 1.0 - (time.monotonic() - started)))
        finally:
            sensor.stop_ranging()
    finally:
        sensor.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
