"""RoomTrek wire, endpoint authentication, and bound-socket relay regressions."""
# @(#)roomberry_trek_control_test.py 3.2 2026/11/09 22:00:00
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from roomberry_trek_control import TrekRelay, encode, decode, load_key
from roomberry_navlink import (NavLinkReceiver, TREK_PACKET, decode_packet,
                                packet_fields, export_csv)

KEY = b'A' * 32
TARGET = str(uuid.uuid4())


def packet():
    return TREK_PACKET.pack(b'NVLK', 1, 6, 128, 42, 1, 1, 2, 0,
                            100, 110, uuid.uuid4().bytes,
                            1, 2, 3, 0, 0, 0, 1, 0, 10, 12, 2, 0, bytes(32))


class FakeSocket:
    def __init__(self):
        self.sent = []

    def sendto(self, data, address):
        self.sent.append((decode(data, KEY), address))


class TrekControlTests(unittest.TestCase):
    def setUp(self):
        self.relay = TrekRelay(KEY)
        self.sock = FakeSocket()
        self.phone = ('192.0.2.10', 45000)
        self.cli = ('127.0.0.1', 55000)

    def handle(self, body, source=None):
        self.relay.handle(encode(body, KEY), source or self.phone, self.sock)

    def authenticate(self, source=None):
        self.handle(dict(kind='hello', target=TARGET), source)
        challenge = self.sock.sent[-1][0]
        self.handle(dict(kind='peer', target=TARGET, nonce=challenge['nonce']), source)

    def test_short_key_file_and_empty_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'navlink.key'
            path.write_text('1701\n')
            self.assertEqual(load_key(path), b'1701')
            data = encode(dict(kind='hello'), load_key(path))
            self.assertEqual(decode(data, b'1701')['kind'], 'hello')
            path.write_text(' \n')
            with self.assertRaises(ValueError): load_key(path)

    def test_authentication_and_clock(self):
        data = encode(dict(kind='hello', target=TARGET), KEY, now=100)
        self.assertEqual(decode(data, KEY, now=129)['kind'], 'hello')
        for now in (69, 131):
            with self.assertRaises(ValueError):
                decode(data, KEY, now=now)
        with self.assertRaises(ValueError):
            decode(data, b'B'*32, now=100)
        with self.assertRaises(ValueError):
            decode(data+b'x', KEY, now=100)
        for value in ([], {}, {'payload': 'bad', 'mac': 'bad'}):
            with self.assertRaises(ValueError):
                decode(json.dumps(value).encode(), KEY)
        with self.assertRaises(ValueError):
            decode(encode(dict(kind='response', id=[]), KEY), KEY)

    def test_challenge_and_endpoint_migration(self):
        self.authenticate()
        self.assertEqual(self.relay.peer, self.phone)
        other = ('192.0.2.11', 45001)
        self.handle(dict(kind='hello', target=TARGET), other)
        self.assertEqual(self.relay.peer, self.phone)
        challenge = self.sock.sent[-1][0]
        with self.assertRaises(ValueError):
            self.handle(dict(kind='peer', target=TARGET, nonce='bad'), other)
        self.authenticate(other)
        self.assertEqual(self.relay.peer, other)
        with self.assertRaises(ValueError):
            self.handle(dict(kind='peer', target=TARGET, nonce=challenge['nonce']), other)

    def test_relay_retries_and_unexpected_peers(self):
        self.authenticate()
        command = dict(kind='command', id=str(uuid.uuid4()), command='SURVEY_START')
        self.handle(command, self.cli)
        forwarded = self.sock.sent[-1]
        self.assertEqual(forwarded[1], self.phone)
        self.assertEqual(forwarded[0]['target'], TARGET)
        self.handle(command, self.cli)
        self.assertEqual(self.sock.sent[-1][0]['id'], command['id'])
        with self.assertRaises(ValueError):
            self.handle(dict(command, command='SESSION_STOP'), self.cli)
        response = dict(kind='response', id=command['id'], target=TARGET, status='completed')
        with self.assertRaises(ValueError):
            self.handle(response, ('192.0.2.99', 123))
        self.handle(response)
        self.assertEqual(self.sock.sent[-1][1], self.cli)
        with self.assertRaises(ValueError):
            self.handle(command, ('192.0.2.99', 123))
        self.relay.last_peer -= 11
        self.handle(dict(command, id=str(uuid.uuid4())), self.cli)
        self.assertEqual(self.sock.sent[-1][0]['status'], 'unavailable')

    def test_allowlist(self):
        self.relay.allowed_source = '192.0.2.99'
        with self.assertRaises(ValueError):
            self.authenticate()

    def test_type6_validation(self):
        values = decode_packet(packet())
        self.assertEqual(dict(zip(packet_fields(values), values))['x_m'], 1)
        for offset, value in ((22, 4), (94, 4), (96, 1), (20, 2)):
            data = bytearray(packet()); data[offset] = value
            with self.assertRaises(ValueError):
                decode_packet(data)

    def test_live_receiver_shared_socket_and_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            keyfile = Path(directory)/'key'; keyfile.write_bytes(KEY)
            receiver = NavLinkReceiver(directory, '127.0.0.1', 0, command_key_file=keyfile)
            self.assertTrue(receiver.start())
            try:
                address = ('127.0.0.1', receiver.port)
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as phone, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as cli:
                    phone.settimeout(2); cli.settimeout(2)
                    phone.connect(address); cli.connect(address)
                    phone.send(packet())
                    phone.send(encode(dict(kind='hello', target=TARGET), KEY))
                    challenge = decode(phone.recv(8192), KEY)
                    phone.send(encode(dict(kind='peer', target=TARGET, nonce=challenge['nonce']), KEY))
                    # Ensure the receive thread consumes the proof before CLI traffic.
                    deadline = time.monotonic()+2
                    while receiver.trek_control.peer is None and time.monotonic() < deadline:
                        time.sleep(.005)
                    command_id = str(uuid.uuid4())
                    cli.send(encode(dict(kind='command', id=command_id, command='STATUS'), KEY))
                    command = decode(phone.recv(8192), KEY)
                    self.assertEqual(command['id'], command_id)
                    self.assertEqual(command['target'], TARGET)
                    self.assertEqual(phone.getpeername(), address)
                    for state in ('accepted', 'completed'):
                        phone.send(encode(dict(kind='response', target=TARGET, id=command_id, status=state), KEY))
                        self.assertEqual(decode(cli.recv(8192), KEY)['status'], state)
                    self.assertEqual(receiver.trek_source, phone.getsockname())
                    script = Path(__file__).resolve().parents[2]/'roomberry_trek_control.py'
                    process = subprocess.Popen([sys.executable, str(script), 'SPEAK', '--text', 'G’day, Captain! I’m running a bit low on juice!',
                                                '--key-file', str(keyfile), '--port', str(receiver.port),
                                                '--timeout', '3'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    try:
                        request = decode(phone.recv(8192), KEY)
                        self.assertEqual(request['command'], 'SPEAK')
                        self.assertEqual(request['text'], 'G’day, Captain! I’m running a bit low on juice!')
                        for state in ('accepted', 'completed'):
                            phone.send(encode(dict(kind='response', target=TARGET, id=request['id'], status=state), KEY))
                        stdout, stderr = process.communicate(timeout=5)
                        self.assertEqual(process.returncode, 0, stderr)
                        self.assertEqual(json.loads(stdout.splitlines()[-1])['status'], 'completed')
                    finally:
                        if process.poll() is None:
                            process.kill(); process.communicate()

                    # Malformed control and oversize binary packets do not stop recording.
                    phone.send(encode(dict(kind='response', id=[]), KEY))
                    phone.send(bytes(9000))
                    phone.send(packet())
                    deadline = time.monotonic()+2
                    while (receiver.received < 2 or receiver.rejected < 2) and time.monotonic() < deadline:
                        time.sleep(.005)
            finally:
                receiver.close()
            self.assertEqual(receiver.received, 2)
            self.assertGreaterEqual(receiver.rejected, 2)
            output = io.StringIO(); export_csv(receiver.path, output)
            self.assertIn('map_uuid', output.getvalue())
            self.assertEqual(len(output.getvalue().splitlines()), 3)


if __name__ == '__main__':
    unittest.main()
