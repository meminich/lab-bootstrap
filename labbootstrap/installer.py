#!/usr/bin/env python3
"""Interactive fresh-host installer. Safe plan is the default; apply is opt-in."""

import sys
sys.dont_write_bytecode = True  # Plan/preflight must not create __pycache__, even via direct entry.

import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import pwd
import secrets
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.request
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labbootstrap.common import (  # noqa: E402
    CONFIG_DEFAULTS, INSTALL_DIR, STATE_DIR, SafetyError, atomic_json,
    identity, load_json, output, private_directory, private_file, run,
    source_digest, source_files, tailnet_ip, validated_config, validate_receipt,
)

SOURCE = Path(__file__).resolve().parents[1]
SAFE_ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root', 'LANG': 'C.UTF-8',
            'DEBIAN_FRONTEND': 'noninteractive', 'NEEDRESTART_MODE': 'l'}


def managed_paths(config):
    home = Path('/home') / config['admin_user']
    workspace = home / 'playground'
    system = [
        '/etc/cloud/cloud.cfg.d/99-lab-bootstrap-hostname.cfg',
        '/etc/apt/keyrings/lab-tailscale.gpg', '/etc/apt/sources.list.d/lab-tailscale.list',
        '/etc/ssh/sshd_config.d/00-lab-bootstrap.conf',
        '/etc/apt/apt.conf.d/99-lab-bootstrap', '/etc/docker/daemon.json',
        '/etc/apt/keyrings/lab-docker.asc', '/etc/apt/sources.list.d/lab-docker.list',
        '/etc/systemd/system/docker.service.d/10-lab-bootstrap.conf',
        '/usr/local/sbin/lab-verify-access',
    ]
    paths = [Path(p) for p in system] + [home / 'AGENTS.md', workspace / 'AGENTS.md',
                                      workspace / 'README.md']
    paths.extend(workspace / '_template' / name for name in (
        'compose.yaml', '.env.example', '.gitignore', 'README.md', 'data/index.html'))
    return paths


def file_record(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise SafetyError('Path kelolaan bukan regular file: ' + str(path))
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'uid': info.st_uid, 'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode)}


def validate_manifest(state):
    allowed = {str(p) for p in managed_paths(state['config'])}
    manifest = state.get('managed', {})
    if set(manifest) - allowed:
        raise SafetyError('Manifest berisi path tidak dikenal.')
    for path in allowed:
        file = Path(path)
        if file.exists() or file.is_symlink():
            if path not in manifest or file_record(file) != manifest[path]:
                raise SafetyError('File existing berubah di luar installer: ' + path)
        elif path in manifest:
            raise SafetyError('File kelolaan hilang: ' + path)


def snapshot(state):
    state['managed'] = {str(p): file_record(p) for p in managed_paths(state['config'])
                        if p.exists() or p.is_symlink()}
    try:
        account = pwd.getpwnam(state['admin_user'])
    except KeyError:
        pass
    else:
        state['admin_identity'] = {'uid': account.pw_uid, 'gid': account.pw_gid,
                                   'home': account.pw_dir}
    atomic_json(STATE_DIR / 'state.json', state)


def parse_os(text):
    result = {}
    for line in text.splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            result[key] = value.strip('"')
    return result


def tailscale_peer_listeners(status):
    """Only the running local node's advertised PeerAPI endpoints, never peers."""
    if status.get('BackendState') != 'Running':
        return set()
    assigned = {ip for ip in status.get('TailscaleIPs', []) if tailnet_ip(ip)}
    endpoints = set()
    for value in (status.get('Self') or {}).get('PeerAPIURL') or []:
        try:
            url = urllib.parse.urlsplit(value)
            if (url.scheme == 'http' and url.hostname in assigned and url.port
                    and not url.username and not url.password and url.path in ('', '/')
                    and not url.query and not url.fragment):
                endpoints.add((url.hostname, str(url.port)))
        except ValueError:
            continue
    return endpoints


def check_listeners(report, udp=False, expected_tcp=()):
    # ss -H -ltn: State Recv-Q Send-Q Local Peer. Only public SSH is expected.
    for line in report.splitlines():
        fields = line.split()
        if len(fields) < 5:
            raise SafetyError('Format listener tidak dikenal.')
        address, port = fields[3].rsplit(':', 1)
        address = address.split('%', 1)[0].strip('[]')
        if not udp and (address, port) in expected_tcp:
            continue
        if port in (('68', '546', '41641') if udp else ('22',)):
            continue
        try:
            local = ipaddress.ip_address(address).is_loopback
        except ValueError:
            local = False
        permitted_loopback = port in (('53', '123', '323') if udp else ('53',))
        if not local or not permitted_loopback:
            raise SafetyError('Ada listener di luar baseline; target tidak fresh: '
                              + ('UDP ' if udp else 'TCP ') + fields[3])


def check_package_locks():
    keys = set()
    for name in ('/var/lib/dpkg/lock', '/var/lib/dpkg/lock-frontend', '/var/lib/apt/lists/lock'):
        path = Path(name)
        if path.exists():
            info = path.stat()
            keys.add((os.major(info.st_dev), os.minor(info.st_dev), info.st_ino))
    for line in Path('/proc/locks').read_text().splitlines():
        for word in line.split():
            fields = word.split(':')
            if len(fields) == 3:
                try:
                    key = (int(fields[0], 16), int(fields[1], 16), int(fields[2]))
                except ValueError:
                    continue
                if key in keys:
                    raise SafetyError('APT sedang dipakai. Tunggu lalu ulangi; jangan hapus lock.')


def preflight(config, state=None):
    if os.geteuid() != 0:
        raise SafetyError('Apply/preflight dijalankan dari sesi root VPS fresh.')
    os_info = parse_os(Path('/etc/os-release').read_text())
    if os_info.get('ID') != 'ubuntu' or os_info.get('VERSION_ID') != '22.04':
        raise SafetyError('Target wajib Ubuntu Server 22.04 LTS.')
    if platform.machine() != 'x86_64':
        raise SafetyError('Implementasi pertama hanya amd64; arm64 belum diuji/didukung.')
    if Path('/.dockerenv').exists() or Path('/proc/1/comm').read_text().strip() != 'systemd':
        raise SafetyError('Apply harus pada host/VM systemd, bukan container biasa.')
    if shutil.disk_usage('/').free < 3 * 1024**3:
        raise SafetyError('Disk kosong kurang dari 3 GiB.')
    if shutil.which('cloud-init'):
        result = subprocess.run(['cloud-init', 'status'], capture_output=True, text=True, check=False)
        if result.returncode != 0 or not any(x in result.stdout for x in ('status: done', 'status: disabled')):
            raise SafetyError('Tunggu/perbaiki cloud-init sebelum melanjutkan.')
    check_package_locks()
    for url in ('https://pypi.org/simple/ansible-core/',
                'https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg',
                'https://download.docker.com/linux/ubuntu/gpg'):
        # Public GET/TLS check only; no config or identity is sent.
        with urllib.request.urlopen(url, timeout=15) as response:
            response.read(1)
    if state:
        if state['machine_id'] != identity()['machine_id']:
            raise SafetyError('State berasal dari VPS berbeda.')
        validate_manifest(state)
        if state.get('admin_identity'):
            try:
                account = pwd.getpwnam(config['admin_user'])
            except KeyError as error:
                raise SafetyError('User admin kelolaan hilang; jangan dibuat ulang diam-diam.') from error
            actual = {'uid': account.pw_uid, 'gid': account.pw_gid, 'home': account.pw_dir}
            if actual != state['admin_identity']:
                raise SafetyError('UID/GID/home admin berubah di luar installer.')
        if shutil.which('docker') and output(['docker', 'ps', '-aq']):
            raise SafetyError('Resume ditolak: sudah ada container. Data tidak disentuh.')
    else:
        try:
            pwd.getpwnam(config['admin_user'])
        except KeyError:
            pass
        else:
            raise SafetyError('User admin sudah ada. Target bukan fresh untuk installer ini.')
        for p in [Path('/home') / config['admin_user'], Path('/usr/bin/tailscale'), Path('/var/lib/docker'),
                  Path('/var/lib/containerd'), *managed_paths(config)]:
            if p.exists() or p.is_symlink():
                raise SafetyError('Resource existing tidak diambil alih: ' + str(p))
        if INSTALL_DIR.exists() or INSTALL_DIR.is_symlink():
            raise SafetyError('Direktori installer existing tanpa state yang cocok.')
    expected_tcp = set()
    if state and state.get('prepared'):
        expected_tcp = tailscale_peer_listeners(json.loads(output(['tailscale', 'status', '--json'])))
    check_listeners(output(['ss', '-H', '-ltn']), expected_tcp=expected_tcp)
    check_listeners(output(['ss', '-H', '-lun']), udp=True)
    return os_info


def confirm(prompt):
    if input(prompt + ' [y/N] ').strip().lower() not in ('y', 'yes'):
        raise SafetyError('Dibatalkan. Tidak melanjutkan fase berikutnya.')


def install_source(state):
    destination = INSTALL_DIR / 'source'
    if destination.exists():
        if source_digest(destination) != state['source_digest']:
            raise SafetyError('Source terpasang berubah; perlu review, bukan overwrite.')
        return destination
    with tempfile.TemporaryDirectory(prefix='.source-', dir=INSTALL_DIR) as temporary:
        staged = Path(temporary) / 'payload'
        staged.mkdir(mode=0o700)
        for name, path in source_files(SOURCE):
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with target.open('xb') as stream:
                stream.write(path.read_bytes())
            target.chmod(0o600)
        if source_digest(staged) != state['source_digest']:
            raise SafetyError('Source berubah selama staging; tidak menjalankannya.')
        staged.rename(destination)
    return destination


def playbook(name, state, root, ansible):
    if name not in ('prepare', 'lockdown', 'foundation'):
        raise SafetyError('Playbook tidak dikenal.')
    variables = {**state['config'], 'source_dir': str(root),
                 'tailscale_ip': state.get('tailscale_ip', ''),
                 **load_json(root / 'toolchain.json')}
    variables['ansible_python_interpreter'] = '/usr/bin/python3'
    atomic_json(STATE_DIR / 'ansible-vars.json', variables)
    environment = {**SAFE_ENV, 'ANSIBLE_CONFIG': str(root / 'playbooks/ansible.cfg'),
                   'ANSIBLE_LOCAL_TEMP': str(STATE_DIR / 'ansible-tmp'),
                   'ANSIBLE_NOCOLOR': '1'}
    try:
        run([str(ansible), '-i', 'localhost,', '-c', 'local',
             str(root / 'playbooks' / (name + '.yml')), '-e',
             '@' + str(STATE_DIR / 'ansible-vars.json')], cwd=root, env=environment)
    finally:
        # Preflight proved these specific paths absent or already owned by us.
        # Snapshot even a partial play so resume can detect subsequent drift.
        snapshot(state)


def connect_tailscale(state):
    try:
        status = json.loads(output(['/usr/bin/tailscale', 'status', '--json']))
    except subprocess.CalledProcessError:
        status = {}
    if status.get('BackendState') != 'Running':
        print('Buka link Tailscale yang muncul di browser, login, lalu kembali ke sini.')
        run(['/usr/bin/tailscale', 'up', '--ssh', '--hostname', state['config']['hostname']])
    else:
        run(['/usr/bin/tailscale', 'set', '--ssh', '--hostname', state['config']['hostname']])
    for attempt in range(30):
        try:
            status = json.loads(output(['/usr/bin/tailscale', 'status', '--json']))
        except subprocess.CalledProcessError:
            status = {}
        name = status.get('Self', {}).get('DNSName', '').rstrip('.')
        if (status.get('BackendState') == 'Running' and name
                and name.split('.')[0] == state['config']['hostname']
                and status.get('TailscaleIPs')):
            break
        if attempt < 29:
            time.sleep(1)
    if (status.get('BackendState') != 'Running' or not name
            or name.split('.')[0] != state['config']['hostname']):
        raise SafetyError('Nama Tailscale tidak sesuai/MagicDNS belum siap. Cek perangkat lama/ACL.')
    addresses = [ip for ip in status.get('TailscaleIPs', [])
                 if ipaddress.ip_address(ip).version == 4 and tailnet_ip(ip)]
    if len(addresses) != 1:
        raise SafetyError('IP Tailscale IPv4 tidak tersedia; tidak membuat fallback.')
    previous = state.get('tailscale_ip')
    if previous and previous != addresses[0]:
        raise SafetyError('IP Tailscale berubah saat resume; perlu review binding.')
    state['tailscale_ip'] = addresses[0]
    state['tailscale_ips'] = [ip for ip in status.get('TailscaleIPs', []) if tailnet_ip(ip)]
    atomic_json(STATE_DIR / 'state.json', state)


def checkpoint(state, purpose):
    for name in ('receipt.json', 'challenge.json'):
        path = STATE_DIR / name
        if path.exists() or path.is_symlink():
            private_file(path).unlink()
    now = time.time()
    challenge = {**identity(), 'run_id': state['run_id'],
                 'source_digest': state['source_digest'], 'admin_user': state['admin_user'],
                 'nonce': secrets.token_hex(32), 'issued': now, 'expires': now + 900,
                 'purpose': purpose, 'previous_connections': state.get('used_connections', [])[-64:]}
    atomic_json(STATE_DIR / 'challenge.json', challenge)
    print('\nCHECKPOINT:', purpose)
    print('Buka terminal client BARU (Tailscale aktif), jangan tutup terminal installer:')
    print('  ssh ' + state['admin_user'] + '@' + state['config']['hostname'])
    print('Lalu jalankan di terminal client tersebut:')
    print('  sudo -k -- /usr/local/sbin/lab-verify-access --connection "$SSH_CONNECTION"')
    print('Masukkan password sudo di terminal client, bukan di sini.')
    input('Sesudah verifier berhasil, kembali ke sini dan tekan Enter: ')
    receipt = load_json(private_file(STATE_DIR / 'receipt.json'))
    validate_receipt(receipt, challenge, state, identity())
    state['used_connections'] = (state.get('used_connections', []) + [receipt['connection']])[-64:]
    atomic_json(STATE_DIR / 'state.json', state)
    print('Peer terverifikasi:', receipt['peer_login'], '(' + receipt['source'] + ')')
    return receipt


def configure(state, root):
    from labbootstrap.tooling import prepare
    ansible = prepare(root, INSTALL_DIR)
    if not state.get('prepared'):
        playbook('prepare', state, root, ansible)
        state['prepared'] = True
        snapshot(state)
    if output(['passwd', '-S', state['admin_user']]).split()[1] != 'P':
        print('Buat password admin untuk sudo. Password tidak disimpan oleh installer.')
        run(['passwd', state['admin_user']])
    if output(['passwd', '-S', state['admin_user']]).split()[1] != 'P':
        raise SafetyError('Password sudo belum siap; tidak akan melakukan lockdown.')
    connect_tailscale(state)
    if not state.get('locked_down'):
        checkpoint(state, 'before-lockdown')
        playbook('lockdown', state, root, ansible)
        state['locked_down'] = True
        snapshot(state)
    checkpoint(state, 'after-lockdown')
    # Destructive/access changes remain behind the external gates, also on resume.
    playbook('foundation', state, root, ansible)
    run(['docker', 'compose', '--env-file', '/home/' + state['admin_user']
         + '/playground/_template/.env.example', '-f', '/home/' + state['admin_user']
         + '/playground/_template/compose.yaml', 'config', '--quiet'],
        env={**SAFE_ENV, 'DOCKER_CONFIG': str(STATE_DIR / 'docker-cli')})
    checkpoint(state, 'after-foundation')
    result = {'source_digest': state['source_digest'], 'os': 'Ubuntu 22.04',
              'architecture': 'amd64', 'status': 'configured-not-release-verified',
              'access_checkpoints': ['before-lockdown', 'after-lockdown', 'after-foundation'],
              'pending': ['probe dari luar tailnet (IPv4/IPv6)', 'reboot terencana dan tes ulang']}
    atomic_json(STATE_DIR / 'result.json', result)
    state['configured'] = True
    snapshot(state)
    print('\nFondasi terkonfigurasi. BUKAN bukti semua tes rilis sudah lulus.')
    print('Login harian: ssh ' + state['admin_user'] + '@' + state['config']['hostname'])
    print('Masih perlu tes dari luar tailnet dan reboot terencana. Tidak reboot otomatis.')


def main():
    parser = argparse.ArgumentParser(description='VPS Lab v2 — Ubuntu 22.04 amd64 (EXPERIMENTAL)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='rencana saja; default, tanpa penulisan')
    mode.add_argument('--preflight', action='store_true', help='cek host read-only, perlu root')
    mode.add_argument('--apply', action='store_true', help='ubah host fresh, belum untuk produksi')
    parser.add_argument('--experimental', action='store_true', help='akui kandidat belum menjadi rilis produksi')
    parser.add_argument('--resume', action='store_true', help='lanjutkan run milik installer dengan source sama')
    parser.add_argument('--config', type=Path, help='JSON eksplisit; tidak membaca config.env')
    args = parser.parse_args()
    if not args.apply and not args.preflight:
        print('RENCANA SAJA: belum ada mutasi host atau unduhan dependency.')
        print('Ubuntu 22.04 amd64 → admin → Tailscale → checkpoint → lockdown → checkpoint → Docker/workspace.')
        print('Kandidat eksperimental, bukan rilis produksi. Lihat docs/VERIFICATION.md untuk bukti dan batas tes.')
        return
    if args.apply and not args.experimental:
        raise SafetyError('Belum rilis teruji. Apply memerlukan --experimental pada VPS uji fresh.')
    if os.geteuid() != 0:
        raise SafetyError('Perlu root untuk pemeriksaan host/apply.')
    current_digest = source_digest(SOURCE)  # Validate complete payload before any host changes.
    state = None
    if args.resume:
        private_directory(STATE_DIR)
        state = load_json(private_file(STATE_DIR / 'state.json'))
        config = validated_config(state['config'])
        if args.config:
            raise SafetyError('Resume memakai config tersimpan; jangan mengganti config saat resume.')
        if state['source_digest'] != current_digest:
            raise SafetyError('Resume wajib memakai source versi yang sama.')
        if state['machine_id'] != identity()['machine_id']:
            raise SafetyError('State berasal dari VPS lain.')
        if state.get('configured'):
            print('Sudah terkonfigurasi. Rerun tidak menyentuh data/config/layanan.')
            print('Untuk audit hasil: /var/lib/lab-bootstrap/result.json. Ini bukan mekanisme update.')
            return
    else:
        if STATE_DIR.exists() or STATE_DIR.is_symlink():
            raise SafetyError('Ada state existing. Gunakan --resume, bukan mulai ulang.')
        config = validated_config(load_json(args.config) if args.config else CONFIG_DEFAULTS)
    preflight(config, state)
    if args.preflight:
        print('Preflight read-only lolos. Tidak ada paket/file/firewall yang diubah.')
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SafetyError('Apply memerlukan terminal interaktif; jangan pipe installer.')
    print('EXPERIMENTAL — hanya untuk Ubuntu 22.04 amd64 fresh yang boleh diubah.')
    print('Pengaturan:', json.dumps(config, ensure_ascii=False))
    confirm('Console/VNC provider bisa dibuka dan client sudah tersambung ke Tailscale?')
    confirm('Setuju membuat admin, mengatur SSH/firewall, upgrade paket, memasang Docker, dan restart service bila perlu?')
    os.umask(0o077)
    if state is None:
        STATE_DIR.mkdir(mode=0o700)
        INSTALL_DIR.mkdir(mode=0o700)
        state = {'config': config, 'admin_user': config['admin_user'],
                 'machine_id': identity()['machine_id'], 'source_digest': current_digest,
                 'run_id': secrets.token_hex(32), 'managed': {}}
        atomic_json(STATE_DIR / 'state.json', state)
    private_directory(STATE_DIR)
    private_directory(INSTALL_DIR)
    # One installer at a time. flock is released across exec into tmux.
    lock_path = STATE_DIR / 'installer.lock'
    if lock_path.exists() or lock_path.is_symlink():
        private_file(lock_path)
    with lock_path.open('a') as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = install_source(state)
        if not os.environ.get('TMUX'):
            # No upgrades before tmux. Keep the process alive through SSH reconnects.
            run(['apt-get', 'update'], env=SAFE_ENV)
            run(['apt-get', 'install', '-y', '--no-install-recommends', 'tmux', 'ca-certificates'],
                env={**SAFE_ENV, 'DEBIAN_FRONTEND': 'noninteractive'})
            print('Setup berjalan di tmux, jadi proses tetap hidup jika SSH putus.')
            print('Sebelum Tailscale siap: login root seperti awal, lalu tmux attach -t lab-bootstrap.')
            print('Sesudah Tailscale siap: ssh ' + state['admin_user'] + '@' + config['hostname']
                  + ', lalu sudo tmux attach -t lab-bootstrap.', flush=True)
            os.execv('/usr/bin/tmux', ['tmux', 'new-session', '-s', 'lab-bootstrap',
                     '/usr/bin/python3', '-I', '-B', str(root / 'labbootstrap/installer.py'),
                     '--apply', '--experimental', '--resume'])
        state['run_id'] = secrets.token_hex(32)
        atomic_json(STATE_DIR / 'state.json', state)
        configure(state, root)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nDihentikan; tidak membuka publik otomatis. Resume dengan source yang sama.', file=sys.stderr)
        sys.exit(130)
    except (SafetyError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print('STOP:', str(error), file=sys.stderr)
        print('Jangan hapus state/bypass gate. Gunakan console jika akses terganggu.', file=sys.stderr)
        sys.exit(1)
