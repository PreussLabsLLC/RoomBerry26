"""Authenticated RoomTrek control relay and loopback CLI; shares NavLink UDP port."""
# @(#)roomberry_trek_control.py 3.2.maps.1 2026/11/10 10:15:00
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import time
import uuid

COMMANDS = ('STATUS', 'SURVEY_START', 'SURVEY_SAVE', 'NAV_START', 'NAV_RETRY', 'SESSION_STOP', 'SPEAK', 'MAP_LIST', 'MAP_RENAME', 'MAP_DELETE')
MAX_DATAGRAM = 8192


def load_key(path):
    key = Path(path).read_bytes().strip()
    if not key:
        raise ValueError('NavLink key must not be empty')
    return key


def encode(body, key, now=None):
    body = dict(body, v=1, ts=time.time() if now is None else now)
    payload = json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return json.dumps({'payload': base64.b64encode(payload).decode(),
                       'mac': base64.b64encode(hmac.digest(key, payload, 'sha256')).decode()}).encode()


def decode(data, key, now=None):
    try:
        if len(data) > MAX_DATAGRAM:
            raise ValueError('oversize')
        outer = json.loads(data)
        payload = base64.b64decode(outer['payload'], validate=True)
        mac = base64.b64decode(outer['mac'], validate=True)
        if not hmac.compare_digest(mac, hmac.digest(key, payload, 'sha256')):
            raise ValueError('authentication')
        body = json.loads(payload)
        timestamp = body['ts']
        if body['v'] != 1 or not abs((time.time() if now is None else now)-timestamp) <= 30:
            raise ValueError('version/time')
        for field in ('kind', 'target', 'id', 'nonce', 'command', 'status'):
            if field in body and (not isinstance(body[field], str) or len(body[field]) > 128):
                raise ValueError('field type/length')
        if not isinstance(body.get('kind'), str):
            raise ValueError('kind')
        return body
    except (KeyError, TypeError, OverflowError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError('invalid envelope') from error


class TrekRelay:
    """Used only by the receiver thread, so the bound telemetry socket owns all I/O.

    An HMAC challenge proves the endpoint can receive packets before replacing
    the peer. Replayed hello packets alone cannot redirect commands.
    """
    def __init__(self, key, allowed_source=None):
        self.key = key
        self.allowed_source = allowed_source
        self.peer = None
        self.target = None
        self.last_peer = 0
        self.operation = {}
        self.challenges = {}
        self.routes = {}

    def handle(self, data, source, sock):
        body = decode(data, self.key)
        now = time.monotonic()
        self.challenges = {k: v for k, v in self.challenges.items() if now-v[2] < 5}
        self.routes = {k: v for k, v in self.routes.items() if now-v[2] < 90}
        kind = body['kind']
        target = body.get('target')
        if kind in ('hello', 'peer', 'response'):
            if self.allowed_source and source[0] != self.allowed_source:
                raise ValueError('unexpected source')
        if kind == 'hello':
            if not isinstance(target, str) or len(target) > 64 or len(self.challenges) >= 128:
                raise ValueError('target/capacity')
            nonce = secrets.token_hex(24)
            self.challenges[source] = (nonce, target, now, body.get('operation', {}))
            sock.sendto(encode(dict(kind='challenge', target=target, nonce=nonce), self.key), source)
        elif kind == 'peer':
            expected = self.challenges.pop(source, None)
            if expected is None or (body.get('nonce'), target) != expected[:2]:
                raise ValueError('challenge')
            self.peer, self.target, self.last_peer = source, target, now
            self.operation = expected[3] if isinstance(expected[3], dict) else {}
        elif kind == 'command':
            if source[0] != '127.0.0.1':
                raise ValueError('CLI must be loopback')
            command_id = body.get('id')
            try:
                uuid.UUID(command_id)
            except (ValueError, TypeError, AttributeError) as error:
                raise ValueError('command id') from error
            if self.peer is None or now-self.last_peer > 10:
                sock.sendto(encode(dict(kind='response', id=command_id, status='unavailable',
                                        detail='No fresh authenticated RoomTrek peer'), self.key), source)
                return
            # The CLI first asks STATUS with target omitted; bind on the Pi.
            if target is not None and target != self.target:
                raise ValueError('target changed')
            body['target'] = self.target
            old = self.routes.get(command_id)
            identity = {k: v for k, v in body.items() if k != 'ts'}
            if old and old[3] != identity:
                raise ValueError('command ID reused with different content')
            if len(self.routes) >= 1024 and old is None:
                raise ValueError('route capacity')
            self.routes[command_id] = (source, self.target, now, identity)
            sock.sendto(encode(body, self.key), self.peer)
        elif kind == 'response':
            route = self.routes.get(body.get('id'))
            if source != self.peer or target != self.target or route is None or route[1] != target:
                raise ValueError('unexpected response')
            sock.sendto(data, route[0])
        else:
            raise ValueError('unexpected kind')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=COMMANDS)
    parser.add_argument('--key-file', default=os.environ.get('ROOMTREK_KEY_FILE'))
    parser.add_argument('--port', type=int, default=5010)
    parser.add_argument('--map-id')
    parser.add_argument('--target', help='pin to an app-process UUID, especially when retrying an old ID')
    parser.add_argument('--name')
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--text', help='utterance for SPEAK, 1–500 characters')
    parser.add_argument('--id', default=str(uuid.uuid4()), help='reuse ID to inspect/retry the same operation')
    parser.add_argument('--timeout', type=float, default=45)
    args = parser.parse_args()
    if not args.key_file:
        parser.error('--key-file or ROOMTREK_KEY_FILE required')
    key = load_key(args.key_file)
    body = dict(kind='command', id=args.id, command=args.command)
    if args.command == 'SPEAK' and (not args.text or not args.text.strip() or len(args.text) > 500):
        parser.error('SPEAK requires --text with 1–500 characters')
    if args.text is not None:
        body['text'] = args.text
    if args.target:
        body['target'] = args.target
    if args.map_id:
        body['map_id'] = args.map_id
    if args.name:
        body['name'] = args.name
    if args.command == 'MAP_LIST':
        body['offset'] = args.offset
    deadline = time.monotonic()+args.timeout
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(('127.0.0.1', args.port))
        sock.settimeout(1)
        while time.monotonic() < deadline:
            sock.send(encode(body, key))
            try:
                response = decode(sock.recv(MAX_DATAGRAM+1), key)
            except socket.timeout:
                continue
            if response.get('kind') != 'response' or response.get('id') != args.id:
                continue
            if response.get('target'):
                body['target'] = response['target']
            print(json.dumps(response, sort_keys=True), flush=True)
            if response.get('status') in ('completed', 'failed', 'unavailable'):
                return 0 if response['status'] == 'completed' else 1
            # Retry with the same ID retrieves the latest acknowledgment.
            time.sleep(0.25)
    print(json.dumps(dict(id=args.id, status='unknown', detail='Response timeout; operation may still be running. Retry the same ID.')))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
