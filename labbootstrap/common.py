"""Small, auditable primitives shared by the installer and access verifier."""

import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

STATE_DIR = Path('/var/lib/lab-bootstrap')
INSTALL_DIR = Path('/opt/lab-bootstrap')
CONFIG_DEFAULTS = {
    'admin_user': 'vpsadmin', 'hostname': 'vpslab',
    'timezone': 'Asia/Jakarta', 'swap_gib': 4,
}
TS_NETWORKS = (ipaddress.ip_network('100.64.0.0/10'),
               ipaddress.ip_network('fd7a:115c:a1e0::/48'))


class SafetyError(RuntimeError):
    pass


def run(args, **kwargs):
    # No shell, no secret arguments, and no automatic retry of mutations.
    return subprocess.run(args, check=True, text=True, **kwargs)


def output(args):
    return run(args, capture_output=True).stdout.strip()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def private_file(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise SafetyError('File state harus regular, root-owned, mode 600.')
    return path


def private_directory(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise SafetyError('Direktori installer harus root-owned, mode 700, bukan symlink.')


def atomic_json(path, value, exclusive=False):
    path = Path(path)
    if path.exists() or path.is_symlink():
        private_file(path)
    fd, temporary = tempfile.mkstemp(prefix='.lab-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, path)  # Atomic create-if-absent; no receipt overwrite.
        else:
            os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validated_config(value):
    if not isinstance(value, dict) or set(value) - set(CONFIG_DEFAULTS):
        raise SafetyError('Config JSON berisi field tidak dikenal.')
    config = {**CONFIG_DEFAULTS, **value}
    user, host, timezone = (config[k] for k in ('admin_user', 'hostname', 'timezone'))
    if not isinstance(user, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,30}', user):
        raise SafetyError('Username tidak valid.')
    if user in ('root', 'ubuntu', 'nobody', 'daemon'):
        raise SafetyError('Pilih nama admin khusus, bukan account sistem/provider.')
    if not isinstance(host, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', host):
        raise SafetyError('Hostname tidak valid.')
    if not isinstance(timezone, str) or not re.fullmatch(r'[A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)+', timezone):
        raise SafetyError('Timezone tidak valid.')
    if not (Path('/usr/share/zoneinfo') / timezone).is_file():
        raise SafetyError('Timezone tidak tersedia di OS.')
    if type(config['swap_gib']) is not int or not 0 <= config['swap_gib'] <= 16:
        raise SafetyError('Swap harus integer 0–16 GiB.')
    return config


def tailnet_ip(value):
    ip = ipaddress.ip_address(value)
    return any(ip.version == network.version and ip in network for network in TS_NETWORKS)


def connection_tuple(value):
    fields = value.split()
    if len(fields) != 4:
        raise SafetyError('Jalankan verifier dari sesi SSH Tailscale di terminal kedua.')
    source, source_port, destination, port = fields
    try:
        good = (tailnet_ip(source) and tailnet_ip(destination)
                and 1 <= int(source_port) <= 65535 and int(port) == 22
                and source != destination)
    except (ValueError, TypeError):
        good = False
    if not good:
        raise SafetyError('Sesi bukan koneksi SSH dari perangkat Tailscale lain.')
    return source, destination


def validate_peer(connection, status, whois):
    source, destination = connection_tuple(connection)
    addresses = status.get('TailscaleIPs', [])
    if destination not in addresses or source in addresses:
        raise SafetyError('Sesi tidak menuju IP Tailscale host ini.')
    node = whois.get('Node', {})
    try:
        peer_addresses = [str(ipaddress.ip_interface(x).ip) for x in node.get('Addresses', [])]
    except ValueError as error:
        raise SafetyError('Alamat peer whois tidak valid.') from error
    login = whois.get('UserProfile', {}).get('LoginName')
    if source not in peer_addresses or not node.get('ID') or not login:
        raise SafetyError('Identitas client Tailscale tidak dapat dibuktikan.')
    return {'source': source, 'destination': destination,
            'peer_id': str(node['ID']), 'peer_login': login}


def identity():
    return {
        'machine_id': Path('/etc/machine-id').read_text().strip(),
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    }


def validate_challenge(challenge, state, current_identity, now=None):
    now = time.time() if now is None else now
    for key in ('run_id', 'source_digest', 'admin_user'):
        if not state.get(key) or challenge.get(key) != state.get(key):
            raise SafetyError('Checkpoint milik run/source/user yang berbeda.')
    for key in ('machine_id', 'boot_id'):
        if not current_identity.get(key) or challenge.get(key) != current_identity.get(key):
            raise SafetyError('Checkpoint milik instance/boot yang berbeda.')
    issued, expires = challenge.get('issued', 0), challenge.get('expires', 0)
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for value in (now, issued, expires)):
        raise SafetyError('Timestamp checkpoint tidak valid.')
    if not issued <= now < expires or not 0 < expires - issued <= 900:
        raise SafetyError('Checkpoint kedaluwarsa atau clock berubah; ulangi dari installer.')
    if challenge.get('purpose') not in ('before-lockdown', 'after-lockdown', 'after-foundation'):
        raise SafetyError('Tujuan checkpoint tidak valid.')
    if not re.fullmatch(r'[a-f0-9]{64}', challenge.get('nonce', '')):
        raise SafetyError('Challenge tidak valid.')
    previous = challenge.get('previous_connections', [])
    if not isinstance(previous, list) or len(previous) > 64 or not all(isinstance(x, str) for x in previous):
        raise SafetyError('Daftar sesi sebelumnya tidak valid.')


def validate_receipt(receipt, challenge, state, current_identity, now=None):
    validate_challenge(challenge, state, current_identity, now)
    for key in ('nonce', 'purpose', 'run_id', 'source_digest', 'admin_user',
                'machine_id', 'boot_id', 'issued', 'expires', 'previous_connections'):
        if receipt.get(key) != challenge.get(key):
            raise SafetyError('Receipt tidak cocok dengan challenge aktif.')
    if not receipt.get('peer_id') or not receipt.get('peer_login'):
        raise SafetyError('Receipt tidak memiliki identitas peer.')
    source, destination = connection_tuple(receipt.get('connection', ''))
    destinations = state.get('tailscale_ips', [state.get('tailscale_ip')])
    if destination not in destinations or source == destination:
        raise SafetyError('Receipt menuju host yang salah.')
    if ' '.join(receipt['connection'].split()) in challenge.get('previous_connections', []):
        raise SafetyError('Buka sesi SSH baru; sesi lama tidak membuktikan akses setelah perubahan.')
    if challenge['purpose'] == 'after-foundation' and receipt.get('docker_access') is not True:
        raise SafetyError('Akses Docker sebagai admin belum dibuktikan.')


def source_files(root):
    root = Path(root)
    names = ['install.sh', 'toolchain.json', 'requirements.lock', 'requirements.in']
    for directory in ('labbootstrap', 'playbooks', 'templates'):
        names.extend(str(p.relative_to(root)) for p in (root / directory).rglob('*')
                     if p.suffix in ('.py', '.yml', '.md', '.j2', '.sh', '.cfg'))
    for name in sorted(set(names)):
        path = root / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise SafetyError('Payload source berisi symlink/path tidak valid.')
        yield name, path


def source_digest(root):
    digest = hashlib.sha256()
    for name, path in source_files(root):
        digest.update(name.encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
