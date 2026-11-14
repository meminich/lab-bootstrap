#!/usr/bin/env python3
"""Own, disposable GitHub-runner resources only; no production tailnet secrets."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.build_candidate import build
from labbootstrap.common import source_digest


def command(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def write(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding='utf-8')
    path.chmod(mode)


def fixture_subnet(networks):
    used = [ipaddress.ip_network(item['Subnet']) for network in networks
            for item in (network.get('IPAM', {}).get('Config') or []) if item.get('Subnet')]
    for candidate in ipaddress.ip_network('172.16.0.0/12').subnets(new_prefix=24):
        if not any(candidate.overlaps(existing) for existing in used):
            return str(candidate)
    raise RuntimeError('No unused private Docker subnet available.')


def headscale_config(ip):
    return {
        'server_url': 'https://' + ip + ':8080', 'listen_addr': ip + ':8080',
        'metrics_listen_addr': '127.0.0.1:9090', 'grpc_listen_addr': '127.0.0.1:50443',
        'grpc_allow_insecure': False, 'disable_check_updates': True,
        'noise': {'private_key_path': '/var/lib/headscale/noise.key'},
        # Headscale 0.29.7 expands /24 into 256 reverse-DNS routes, exceeding
        # Jammy resolved's per-link domain limit. /28 needs only 16 routes.
        'prefixes': {'v4': '100.64.0.0/28', 'v6': 'fd7a:115c:a1e0::/48', 'allocation': 'sequential'},
        'database': {'type': 'sqlite', 'sqlite': {'path': '/var/lib/headscale/db.sqlite',
                                              'write_ahead_log': True}},
        'tls_cert_path': '/etc/headscale/server.crt', 'tls_key_path': '/etc/headscale/server.key',
        'tls_letsencrypt_hostname': '',
        'unix_socket': '/var/run/headscale/headscale.sock', 'unix_socket_permission': '0700',
        'log': {'level': 'warn', 'format': 'json'}, 'logtail': {'enabled': False},
        'policy': {'mode': 'file', 'path': '/etc/headscale/policy.json'},
        'dns': {'magic_dns': True, 'base_domain': 'fixture.test', 'override_local_dns': False,
                'nameservers': {'global': [], 'split': {}}, 'search_domains': [], 'extra_records': []},
        'derp': {'server': {'enabled': True, 'region_id': 999, 'region_code': 'fixture',
                            'region_name': 'Disposable fixture DERP', 'verify_clients': True,
                            'stun_listen_addr': ip + ':3478',
                            'private_key_path': '/var/lib/headscale/derp.key',
                            'automatically_add_embedded_derp_region': True},
                 'urls': [], 'paths': [], 'auto_update_enabled': False},
        'node': {'expiry': '0', 'ephemeral': {'inactivity_timeout': '30m'}},
    }


def make_certificates(directory, ip):
    command(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
             '-subj', '/CN=Disposable bootstrap fixture CA', '-keyout', str(directory / 'ca.key'),
             '-out', str(directory / 'ca.crt')])
    command(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes',
             '-subj', '/CN=fixture-control', '-keyout', str(directory / 'server.key'),
             '-out', str(directory / 'server.csr')])
    write(directory / 'extensions', 'subjectAltName=IP:' + ip + '\nextendedKeyUsage=serverAuth\n')
    command(['openssl', 'x509', '-req', '-days', '2', '-in', str(directory / 'server.csr'),
             '-CA', str(directory / 'ca.crt'), '-CAkey', str(directory / 'ca.key'), '-CAcreateserial',
             '-extfile', str(directory / 'extensions'), '-out', str(directory / 'server.crt')])


def main(work):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('VM harness is restricted to disposable GitHub-hosted runners; do not run on VPS.')
    if work.exists():
        raise RuntimeError('Work directory must be new; never reuse or clear someone else\'s directory.')
    work.mkdir(parents=True, mode=0o700)
    private = work / 'private'
    private.mkdir(mode=0o700)
    public = work / 'public'
    public.mkdir()
    lock = json.loads((ROOT / 'tests/vm/fixtures.lock.json').read_text())
    toolchain = json.loads((ROOT / 'toolchain.json').read_text())
    suffix = secrets.token_hex(6)
    network = 'lab-bootstrap-test-' + suffix
    control = 'lab-bootstrap-control-' + suffix
    runner = 'lab-bootstrap-vms-' + suffix
    image = 'lab-bootstrap-vm-tools:' + suffix
    created_network = False
    stage = 'build-tools'
    fixture_secrets = {'root_password': 'Fixture!' + secrets.token_hex(16),
                       'admin_password': 'Fixture!' + secrets.token_hex(16)}

    def redact(text):
        for value in fixture_secrets.values():
            if isinstance(value, str) and len(value) > 4:
                text = text.replace(value, '[fixture secret redacted]')
        return text

    def control_cli(*args):
        return json.loads(command(['docker', 'exec', control, 'headscale', '--config',
                                   '/etc/headscale/config.json', '--output', 'json', *args]))

    try:
        subprocess.run(['docker', 'build', '-t', image, '-f', str(ROOT / 'tests/vm/Dockerfile'),
                        str(ROOT / 'tests/vm')], check=True)
        stage = 'create-private-network'
        network_ids = command(['docker', 'network', 'ls', '-q']).splitlines()
        networks = json.loads(command(['docker', 'network', 'inspect', *network_ids])) if network_ids else []
        subnet = fixture_subnet(networks)
        command(['docker', 'network', 'create', '--subnet', subnet, network])
        created_network = True
        subnet = json.loads(command(['docker', 'network', 'inspect', network]))[0]['IPAM']['Config'][0]['Subnet']
        ip = str(ipaddress.ip_network(subnet)[2])
        control_dir = work / 'control'
        control_dir.mkdir(mode=0o700)
        make_certificates(control_dir, ip)
        write(control_dir / 'config.json', json.dumps(headscale_config(ip), indent=2))
        policy = {'acls': [{'action': 'accept', 'src': ['autogroup:member'], 'dst': ['autogroup:self:*']}],
                  'ssh': [{'action': 'accept', 'src': ['autogroup:member'], 'dst': ['autogroup:self'],
                           'users': ['autogroup:nonroot']}]}
        write(control_dir / 'policy.json', json.dumps(policy))
        (work / 'control-state').mkdir(mode=0o700)
        stage = 'start-private-control'
        command(['docker', 'run', '-d', '--name', control, '--user', '0:0', '--network', network,
                 '--ip', ip, '-v', str(control_dir) + ':/etc/headscale:ro',
                 '-v', str(work / 'control-state') + ':/var/lib/headscale',
                 '--tmpfs', '/var/run/headscale:mode=0700',
                 lock['headscale_image'], 'serve', '--config', '/etc/headscale/config.json'])
        deadline = time.monotonic() + 90
        while True:
            try:
                control_cli('users', 'list')
                break
            except (subprocess.CalledProcessError, ValueError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('Fixture control plane did not become healthy.')
                time.sleep(2)
        stage = 'create-fixture-identity'
        user = control_cli('users', 'create', 'fixture', '--email', 'fixture@example.test')
        user_id = str(user['id'])  # v0.29 requires numeric ID, NOT a username.
        for node in ('client', 'target'):
            key = control_cli('preauthkeys', 'create', '--user', user_id, '--expiration', '2h')
            fixture_secrets[node + '_authkey'] = key['key']
        command(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(private / 'factory_key')])
        root_hash = command(['openssl', 'passwd', '-6', '-stdin'], input=fixture_secrets['root_password'] + '\n')
        fixture_secrets['root_hash'] = root_hash
        write(private / 'secrets.json', json.dumps(fixture_secrets))
        artifact = build(work / 'candidate')
        metadata = {**lock, 'source_digest': source_digest(ROOT),
                    'commit': command(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']),
                    'control_url': 'https://' + ip + ':8080', 'candidate': str(artifact.relative_to(work)),
                    'tailscale_key_sha256': toolchain['tailscale_key_sha256'],
                    'commercial_tailnet_tested': False, 'production_ready': False}
        write(work / 'metadata.json', json.dumps(metadata, indent=2))
        stage = 'run-real-vms'
        devices = ['--device', '/dev/kvm'] if os.access('/dev/kvm', os.R_OK | os.W_OK) else []
        print('Starting two genuine Ubuntu VMs; acceleration:', 'KVM' if devices else 'TCG', flush=True)
        result = subprocess.run(['docker', 'run', '--name', runner, '--network', network,
                                 *devices, '-v', str(work) + ':/work',
                                 '-v', str(ROOT / 'tests/vm') + ':/harness:ro', image], check=False)
        if result.returncode:
            raise RuntimeError('VM acceptance failed; inspect sanitized public report.')
        print('Disposable VM acceptance completed. No production tailnet was used.')
    except Exception as error:
        failure = {'status': 'failed', 'host_stage': stage, 'error': redact(str(error)),
                   'commercial_tailnet_tested': False, 'production_ready': False}
        if isinstance(error, subprocess.CalledProcessError):
            failure['stderr'] = redact((error.stderr or '')[-12000:])
        write(public / 'harness-failure.json', json.dumps(failure, indent=2), 0o644)
        if stage.startswith(('start-private-control', 'create-fixture')):
            logs = subprocess.run(['docker', 'logs', control], capture_output=True, text=True, check=False)
            write(public / 'control-error.txt', redact((logs.stdout + logs.stderr)[-12000:]), 0o644)
        raise
    finally:
        # Names are unique and created by this invocation; no broad prune/delete.
        for name in (runner, control):
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, check=False)
        if created_network:
            subprocess.run(['docker', 'network', 'rm', network], capture_output=True, check=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    main(parser.parse_args().work.resolve())
