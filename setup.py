#!/usr/bin/env python3
"""Download a pinned release and guide a fresh-host installation.

Standalone entry point: only Ubuntu's standard-library Python is required.
Never import code from the download until its archive checksum is verified.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

RELEASE = 'v0.1.0'
ARCHIVE = 'lab-bootstrap-candidate-6496587cfee8.tar.gz'
SHA256 = '12d9131fa818c9f84d3b4cd26a226b25ac2a32cfce13b35569b7f497aedd0cc9'
BASE_URL = 'https://github.com/meminich/lab-bootstrap/releases/download/' + RELEASE
MAX_ARCHIVE = 16 * 1024 * 1024
MAX_UNPACKED = 64 * 1024 * 1024


def download(destination):
    """Bound the download and compare against the digest pinned in this launcher."""
    digest = hashlib.sha256()
    total = 0
    request = urllib.request.Request(BASE_URL + '/' + ARCHIVE,
                                     headers={'User-Agent': 'lab-bootstrap-launcher'})
    with urllib.request.urlopen(request, timeout=60) as response:
        if not response.geturl().startswith('https://'):
            raise ValueError('Download dialihkan ke koneksi non-HTTPS.')
        with destination.open('xb') as stream:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE:
                    raise ValueError('Ukuran download melebihi batas paket.')
                stream.write(chunk)
                digest.update(chunk)
    if digest.hexdigest() != SHA256:
        raise ValueError('Checksum paket tidak cocok. Installer tidak dijalankan.')


def unpack(archive, destination):
    """Reject links, traversal, duplicates and oversized archives before extraction."""
    prefix = ARCHIVE.removesuffix('.tar.gz')
    with tarfile.open(archive, 'r:gz') as bundle:
        members = []
        seen = set()
        total = 0
        for member in bundle:
            if len(members) >= 2048:
                raise ValueError('Terlalu banyak file di paket.')
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or '..' in path.parts
                    or len(path.parts) < 2 or path.parts[0] != prefix
                    or member.name != path.as_posix() or member.name in seen):
                raise ValueError('Entry arsip tidak aman: ' + member.name)
            seen.add(member.name)
            total += member.size
            if member.size < 0 or total > MAX_UNPACKED:
                raise ValueError('Ukuran ekstraksi paket melebihi batas.')
            members.append(member)
        for member in members:
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with bundle.extractfile(member) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o600)
    root = destination / prefix
    for name in ('install.sh', 'labbootstrap/installer.py', 'labbootstrap/common.py'):
        if not (root / name).is_file():
            raise ValueError('Paket installer tidak lengkap: ' + name)
    return root


def ask_config(root):
    # Load defaults and validation only from the checksum-verified release.
    sys.path.insert(0, str(root))
    from labbootstrap.common import CONFIG_DEFAULTS, SafetyError, validated_config

    print('\nTekan Enter untuk memakai nilai dalam kurung siku.')
    while True:
        config = {}
        for key, label in (('admin_user', 'Nama user admin'), ('hostname', 'Nama VPS'),
                           ('timezone', 'Timezone'), ('swap_gib', 'Swap GiB (0–16)')):
            value = input(f'{label} [{CONFIG_DEFAULTS[key]}]: ').strip()
            config[key] = value or CONFIG_DEFAULTS[key]
        try:
            config['swap_gib'] = int(config['swap_gib'])
            return validated_config(config)
        except (ValueError, SafetyError) as error:
            print('Konfigurasi belum valid:', error)
            print('Isi ulang konfigurasi; belum ada perubahan sistem.')


def check_host():
    if os.geteuid() != 0:
        raise ValueError('Login sebagai root di VPS fresh, lalu jalankan lagi. Jangan gunakan di VPS aktif.')
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError('Perlu terminal interaktif. Download file dahulu; jangan curl | python/bash.')
    release = Path('/etc/os-release').read_text()
    values = dict(line.split('=', 1) for line in release.splitlines() if '=' in line)
    if (values.get('ID', '').strip('"') != 'ubuntu'
            or values.get('VERSION_ID', '').strip('"') != '22.04'
            or platform.machine() != 'x86_64'):
        raise ValueError('Target hanya Ubuntu Server 22.04 LTS amd64.')
    if Path('/var/lib/lab-bootstrap').exists() or Path('/opt/lab-bootstrap').exists():
        raise ValueError('Instalasi existing terdeteksi. Jangan mulai ulang atau hapus state. '
                         'Gunakan panduan resume di README / docs/RECOVERY.md.')


def main():
    parser = argparse.ArgumentParser(description='Installer terpandu VPS fresh Ubuntu 22.04 amd64.')
    parser.add_argument('--dry-run', action='store_true', help='lihat alur tanpa download/perubahan')
    args = parser.parse_args()
    if args.dry_run:
        print('RENCANA: download ' + RELEASE + ' → checksum SHA256 → konfigurasi → preflight')
        print('→ konfirmasi → admin/Tailscale → tes SSH/sudo → lockdown → Docker/workspace.')
        print('Tidak ada download atau perubahan. Paket tetap eksperimental; hanya VPS fresh.')
        return 0
    check_host()
    print('VPS Lab — instalasi terpandu, paket ' + RELEASE)
    print('Hanya VPS FRESH. Paket masih eksperimental; akun Tailscale/Contabo belum diuji penuh.')
    print('Siapkan console/VNC provider dan terminal kedua di laptop yang terhubung Tailscale.')
    if input('Lanjut mengambil paket dan mengisi konfigurasi? [y/N] ').strip().lower() not in ('y', 'yes'):
        print('Dibatalkan. Tidak ada download atau perubahan sistem.')
        return 0
    os.umask(0o077)
    # Retain the private download for diagnosis. No cleanup of unrelated resources.
    work = Path(tempfile.mkdtemp(prefix='lab-bootstrap-', dir='/root'))
    print('Mengunduh paket versi tetap dan memeriksa SHA256…', flush=True)
    archive = work / ARCHIVE
    download(archive)
    root = unpack(archive, work)
    print('Checksum cocok. Paket tersimpan di ' + str(work))
    config = ask_config(root)
    config_path = work / 'config.json'
    config_path.write_text(json.dumps(config) + '\n')
    print('\nMemeriksa VPS. Perubahan sistem masih memerlukan konfirmasi installer.', flush=True)
    print('Sesudah mulai, ikuti URL login dan perintah SSH yang muncul di terminal.', flush=True)
    # The existing installer preserves all preflight, access gates and confirmations.
    return subprocess.run(['/bin/bash', str(root / 'install.sh'), '--apply', '--experimental',
                           '--config', str(config_path)], check=False).returncode


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nDibatalkan. Jika instalasi sudah dimulai, ikuti panduan resume.', file=sys.stderr)
        sys.exit(130)
    except (OSError, ValueError, tarfile.TarError) as error:
        print('STOP:', error, file=sys.stderr)
        sys.exit(1)
