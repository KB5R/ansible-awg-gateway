#!/usr/bin/env python3
"""Atomic local AWG registry and Qt-compatible profile export.

Keys never appear in argv. The calling role holds the deployment lock while
applying the returned state to the server. Requires cryptography and qrcode.
"""
import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import zlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


def keypair():
    key = X25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {'private': base64.b64encode(private).decode(), 'public': base64.b64encode(public).decode()}


def atomic_write(path, data):
    path = Path(path)
    if path.exists() and path.read_bytes() == data:
        os.chmod(path, 0o600)
        return False
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        return True
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def vpn_url(config):
    raw = config.encode('utf-8')
    packed = struct.pack('>I', len(raw)) + zlib.compress(raw, 8)
    return 'vpn://' + base64.urlsafe_b64encode(packed).decode().rstrip('=')


def allocate(state, name):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}', name):
        raise ValueError('Client name must use 1-48 letters, digits, hyphens or underscores')
    if name in state['clients']:
        if state['clients'][name].get('revoked', False):
            raise ValueError('Client revocation is pending; finish client_remove first')
        return False
    network = ipaddress.ip_network(state['client_subnet'])
    occupied = {c['address'] for c in state['clients'].values()}
    occupied.update(state['reserved'])
    for address in network.hosts():
        if str(address) not in occupied:
            state['clients'][name] = dict(keypair(), address=str(address))
            return True
    raise ValueError('Client address pool exhausted')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['init', 'read', 'add', 'revoke', 'remove', 'export'])
    parser.add_argument('--state')
    parser.add_argument('--name')
    parser.add_argument('--conf')
    args = parser.parse_args()
    if args.operation == 'export':
        import qrcode
        path = Path(args.conf)
        config = path.read_text()
        changed = atomic_write(path.with_suffix('.url'), (vpn_url(config) + '\n').encode())
        # Native .conf QR is accepted by the standalone AWG apps.
        import io
        image = qrcode.make(config)
        output = io.BytesIO()
        image.save(output, format='PNG')
        changed = atomic_write(path.with_suffix('.png'), output.getvalue()) or changed
        print(json.dumps({'changed': changed}))
        return
    path = Path(args.state)
    changed = False
    if args.operation == 'init':
        import sys
        settings = json.load(sys.stdin)
        client_net = ipaddress.ip_network(settings['client_subnet'])
        backbone_net = ipaddress.ip_network(settings['backbone_subnet'])
        if client_net.version != 4 or backbone_net.version != 4 or client_net.overlaps(backbone_net):
            raise ValueError('Expected disjoint IPv4 networks')
        if any(ipaddress.ip_address(a) not in client_net for a in settings['reserved']):
            raise ValueError('Reserved client addresses must belong to client subnet')
        if path.exists():
            state = json.loads(path.read_text())
            for field in ('client_subnet', 'backbone_subnet', 'reserved'):
                if state[field] != settings[field]:
                    raise ValueError('Address plan changed; migrate existing state explicitly')
        else:
            state = dict(settings, version=1, clients={}, nodes={
                'jump': {'client': keypair(), 'backbone': keypair()},
                'gateway': {'backbone': keypair()}},
                headers={'client': keypair()['private'], 'backbone': keypair()['private']})
            changed = True
    else:
        state = json.loads(path.read_text())
    if args.operation == 'add':
        changed = allocate(state, args.name)
    elif args.operation == 'revoke':
        client = state['clients'].get(args.name)
        if client is not None and not client.get('revoked', False):
            client['revoked'] = True
            changed = True
    elif args.operation == 'remove':
        changed = state['clients'].pop(args.name, None) is not None
    if changed:
        atomic_write(path, (json.dumps(state, indent=2) + '\n').encode())
    print(json.dumps({'changed': changed, 'state': state}))


if __name__ == '__main__':
    main()
