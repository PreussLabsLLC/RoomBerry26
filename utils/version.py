# @(#)version.py 2.3.11 2026/10/28 18:00:00
"""Reset a Roomba and capture its boot firmware identity (exclusive serial use)."""
import argparse
import json
import re
import time

import serial

SERIAL_PORT = "/dev/serial0"
BAUD_RATE = 115200


def parse_firmware(output):
    text = output.decode('utf-8', errors='replace')
    match = re.search(r'r3[_-]robot/tags/release-(\d+\.\d+\.\d+)[^\r\n]*', text)
    return {
        'firmware_version': match.group(0) if match else None,
        'firmware_release': match.group(1) if match else None,
        'boot_message': text,
    }


def capture_firmware_version(port=SERIAL_PORT, baud_rate=BAUD_RATE):
    print(f"Connecting to Roomba on {port} at {baud_rate} baud...")
    with serial.Serial(port, baud_rate, timeout=0.1, write_timeout=1) as ser:
        ser.reset_input_buffer()
        # START can recover an OI STOP; RESET then stops native activity and reboots.
        ser.write(b'\x80')
        time.sleep(0.1)
        print('Sending reset command (Opcode 7)...')
        ser.write(b'\x07')
        ser.flush()
        print('Listening for boot messages (up to 15 seconds)...')
        deadline = time.monotonic() + 15
        output = bytearray()
        while time.monotonic() < deadline:
            output.extend(ser.read(max(1, ser.in_waiting)))
        result = parse_firmware(output)
        print('\n--- Captured Boot Stream ---')
        print(result['boot_message'])
        print('----------------------------')
        print('Firmware:', result['firmware_version'] or 'unknown')
        # Reset leaves OI off. Re-enter OI, select Safe, and verify packet 35.
        ser.reset_input_buffer()
        ser.write(b'\x80')
        time.sleep(0.1)
        ser.write(b'\x83')
        time.sleep(0.1)
        ser.reset_input_buffer()
        ser.write(b'\x8e\x23')
        if ser.read(1) != b'\x02':
            raise RuntimeError('Unable to verify Safe mode; no beeps sent')
        result['oi_mode'] = 2
        print('Safe mode verified. No drive commands sent.')
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default=SERIAL_PORT)
    parser.add_argument('--baud', type=int, default=BAUD_RATE)
    parser.add_argument('--output', help='Save firmware identity and boot stream as JSON')
    args = parser.parse_args()
    try:
        result = capture_firmware_version(args.port, args.baud)
        if args.output:
            with open(args.output, 'w') as stream:
                json.dump(result, stream, indent=2)
                stream.write('\n')
    except (OSError, serial.SerialException, RuntimeError) as error:
        parser.exit(1, f'Error: {error}\n')
