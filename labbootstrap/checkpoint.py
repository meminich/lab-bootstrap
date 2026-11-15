#!/usr/bin/env python3
"""Fixed-purpose root verifier. No sudoers exception or arbitrary execution."""

import argparse
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labbootstrap.common import (  # noqa: E402
    SafetyError, STATE_DIR, atomic_json, identity, load_json, output,
    private_directory, private_file, validate_challenge, validate_peer, validate_receipt,
)


def main():
    parser = argparse.ArgumentParser(description='Buktikan sesi SSH Tailscale dan akses sudo.')
    parser.add_argument('--connection', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not sys.stdin.isatty():
        raise SafetyError('Jalankan melalui sudo dari terminal SSH kedua.')
    private_directory(STATE_DIR)
    state = load_json(private_file(STATE_DIR / 'state.json'))
    challenge = load_json(private_file(STATE_DIR / 'challenge.json'))
    account = pwd.getpwnam(state['admin_user'])
    if (os.environ.get('SUDO_USER') != account.pw_name
            or os.environ.get('SUDO_UID') != str(account.pw_uid)):
        raise SafetyError('Verifier harus dipanggil melalui sudo oleh admin yang dibuat installer.')
    validate_challenge(challenge, state, identity())
    status = json.loads(output(['/usr/bin/tailscale', 'status', '--json']))
    from labbootstrap.common import connection_tuple
    source, _ = connection_tuple(args.connection)
    peer = validate_peer(args.connection, status,
                         json.loads(output(['/usr/bin/tailscale', 'whois', '--json', source])))
    if (STATE_DIR / 'receipt.json').exists():
        raise SafetyError('Checkpoint sudah digunakan. Kembali ke terminal installer.')
    receipt = {**challenge, **peer, 'connection': ' '.join(args.connection.split())}
    if challenge['purpose'] == 'after-foundation':
        # Prove access to THIS host, not an inherited remote Docker context.
        # Empty root-owned directory is readable, but not writable, by the admin.
        with tempfile.TemporaryDirectory(prefix='lab-docker-check-', dir='/run') as config:
            os.chmod(config, 0o755)
            environment = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8',
                           'HOME': account.pw_dir, 'DOCKER_CONFIG': config,
                           'DOCKER_HOST': 'unix:///var/run/docker.sock'}
            subprocess.run(['/usr/sbin/runuser', '-u', account.pw_name, '--',
                            '/usr/bin/docker', 'info'], check=True, env=environment,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        receipt['docker_access'] = True
    validate_receipt(receipt, challenge, state, identity())
    atomic_json(STATE_DIR / 'receipt.json', receipt, exclusive=True)
    print('Akses Tailscale dan sudo terbukti. Kembali ke terminal installer, tekan Enter.')


if __name__ == '__main__':
    try:
        main()
    except (SafetyError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print('STOP:', str(error), file=sys.stderr)
        sys.exit(1)
