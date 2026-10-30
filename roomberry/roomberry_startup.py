# @(#)roomberry_startup.py 2.3.12 2026/10/28 19:40:00
"""Capture the reset boot stream before the OI driver owns the serial port."""
import re
from time import monotonic, sleep


def reset_and_identify(port, logger, baud_rate=115200, serial_factory=None):
    if serial_factory is None:
        from serial import Serial
        serial_factory = Serial
    output = bytearray()
    with serial_factory(port=port, baudrate=baud_rate, timeout=0.1,
                        write_timeout=1) as connection:
        connection.reset_input_buffer()
        logger.info('Roomba startup: sending START then RESET; capturing boot stream.')
        connection.write(b'\x80')
        sleep(0.1)
        connection.write(b'\x07')
        connection.flush()
        deadline = monotonic() + 15
        while monotonic() < deadline:
            output.extend(connection.read(1024))
    text = output.decode('utf-8', errors='replace')
    match = re.search(r'r3[_-]robot/tags/release-(\d+\.\d+\.\d+)[^\r\n]*', text)
    identity = dict(boot_message=text,
                    firmware_version=match.group(0) if match else None,
                    firmware_release=match.group(1) if match else None)
    logger.info('Roomba startup firmware: %s (release=%s; boot_bytes=%d).',
                identity['firmware_version'] or 'unknown',
                identity['firmware_release'] or 'unknown', len(output))
    return identity
