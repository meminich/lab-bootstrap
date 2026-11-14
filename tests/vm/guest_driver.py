#!/usr/bin/env python3
"""Executable fixture driver; run only inside the disposable VM-tools container."""
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import tarfile
import time
import urllib.request
import uuid

import pexpect
from terminal_protocol import CHECKPOINT_PATTERN
from qmp import command as qmp_command

WORK = Path('/work')
META = json.loads((WORK / 'metadata.json').read_text())
SECRETS = json.loads((WORK / 'private/secrets.json').read_text())
KEY = WORK / 'private/factory_key'
REPORT = {'status': 'running', 'source_digest': META['source_digest'], 'commit': META['commit'],
          'ubuntu_image_sha256': META['ubuntu_image_sha256'], 'checks': {},
          'commercial_tailnet_tested': False, 'production_ready': False,
          'control_plane': 'Headscale ' + META['headscale_version']}
PROCESSES = []


def redact(value):
    value = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----',
                   '[fixture private key redacted]', str(value), flags=re.S)
    for secret in SECRETS.values():
        value = value.replace(secret, '[fixture secret redacted]')
    return value


def save_report():
    (WORK / 'public/report.json').write_text(json.dumps(REPORT, indent=2, sort_keys=True) + '\n')


def stage(name):
    REPORT['stage'] = name
    print('VM acceptance:', name, flush=True)
    save_report()


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def ssh_args(port, command, tty=False):
    return ['-tt' if tty else '-T', '-p', str(port), '-i', str(KEY),
            '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'UserKnownHostsFile=/work/private/factory_known_hosts',
            '-o', 'ConnectTimeout=5', '-o', 'ControlMaster=no',
            'root@127.0.0.1', command]


def factory(port, command, timeout=60):
    return run(['ssh', *ssh_args(port, command)], timeout=timeout)


def mark_json(output):
    for line in reversed(output.replace('\r', '').splitlines()):
        if line.startswith('LABJSON:'):
            return json.loads(line[len('LABJSON:'):])
    raise RuntimeError('No structured fixture result; output: ' + redact(output[-3000:]))


def py_command(code):
    return '/usr/bin/python3 -c ' + shlex.quote(code)


def peer(command, sudo=False, timeout=120, family=None, host='vpslab'):
    # Two distinct kernels: factory SSH reaches the client, then normal ssh uses
    # MagicDNS and the client's actual Tailscale interface to reach the target.
    if sudo:
        command = "sudo -k -p '[fixture-sudo] ' -- " + command
    inner = ['ssh', *(['-' + str(family)] if family in (4, 6) else []), '-tt', '-o', 'StrictHostKeyChecking=accept-new',
             '-o', 'UserKnownHostsFile=/root/.ssh/fixture_mesh_hosts',
             '-o', 'ConnectTimeout=15', '-o', 'ControlMaster=no',
             '-o', 'ControlPath=none', 'vpsadmin@' + host]
    outer = shlex.join(inner)
    child = pexpect.spawn('ssh', ssh_args(2223, outer, tty=True), encoding='utf-8',
                          codec_errors='replace', timeout=timeout, dimensions=(50, 240))
    child.setecho(False)
    transcript = io.StringIO()
    child.logfile_read = transcript
    try:
        # Exercise the documented human path: login shell first, then sudo.
        # Tailscale SSH remote-command mode can have a PTY without a controlling
        # terminal on Jammy, so tty(1) alone does not prove sudo can open /dev/tty.
        child.sendline("stty -echo; printf '\\nLAB-SHELL-READY\\n'")
        child.expect(r'\r*\nLAB-SHELL-READY\r*\n')
        child.sendline("printf '\\n'; " + command + '; fixture_rc=$?; exit "$fixture_rc"')
        if sudo:
            child.expect_exact('[fixture-sudo] ')
            child.sendline(SECRETS['admin_password'])
        child.expect(pexpect.EOF)
        text = child.before
        child.close()
        if child.exitstatus != 0:
            raise RuntimeError('Peer SSH command failed: ' + redact(text[-5000:]))
        return text
    except (pexpect.EOF, pexpect.TIMEOUT) as error:
        raise RuntimeError('Peer SSH stopped before completing interaction: '
                           + redact(transcript.getvalue()[-8000:])) from error
    finally:
        with (WORK / 'public/peer-interactions.txt').open('a') as log:
            log.write('\n--- peer interaction ---\n' + redact(transcript.getvalue()[-12000:]))
        if child.isalive():
            child.close(force=True)


def peer_sudo_shell(command, timeout=120):
    return peer('/bin/sh -c ' + shlex.quote(command), sudo=True, timeout=timeout)


def download_image():
    destination = WORK / 'ubuntu-base.img'
    digest = hashlib.sha256()
    with urllib.request.urlopen(META['ubuntu_image_url'], timeout=120) as response, destination.open('xb') as stream:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            stream.write(chunk)
    if digest.hexdigest() != META['ubuntu_image_sha256']:
        raise RuntimeError('Ubuntu image checksum mismatch; never boot it.')


def seed(name, index):
    directory = WORK / name
    directory.mkdir(mode=0o700)
    nat_mac = '52:54:00:22:00:' + ('10' if index == 10 else '20')
    lan_mac = '52:54:00:22:00:' + ('11' if index == 10 else '21')
    config = {
        'hostname': 'fresh-target' if name == 'target' else 'fixture-client',
        'manage_etc_hosts': True, 'disable_root': False, 'ssh_pwauth': False,
        'users': ['default', {'name': 'root', 'lock_passwd': False,
                              'passwd': SECRETS['root_hash'],
                              'ssh_authorized_keys': [KEY.with_suffix('.pub').read_text().strip()]}],
        'write_files': [{'path': '/usr/local/share/ca-certificates/fixture-control.crt',
                         'permissions': '0644', 'content': (WORK / 'control/ca.crt').read_text()}],
        'runcmd': [['update-ca-certificates']],
    }
    if name == 'client':
        script = """#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates
mkdir -p /etc/apt/keyrings
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg -o /etc/apt/keyrings/fixture-tailscale.gpg
echo '{key_hash}  /etc/apt/keyrings/fixture-tailscale.gpg' | sha256sum -c -
printf '%s\\n' 'deb [signed-by=/etc/apt/keyrings/fixture-tailscale.gpg] https://pkgs.tailscale.com/stable/ubuntu jammy main' > /etc/apt/sources.list.d/fixture-tailscale.list
apt-get update -qq
apt-get install -y -qq tailscale curl
systemctl enable --now tailscaled
tailscale up --login-server={control} --auth-key=file:/root/fixture-authkey --hostname=fixture-client
rm /root/fixture-authkey
""".format(key_hash=META['tailscale_key_sha256'], control=shlex.quote(META['control_url']))
        config['write_files'].extend([
            {'path': '/root/fixture-authkey', 'permissions': '0600', 'content': SECRETS['client_authkey']},
            {'path': '/root/fixture-client.sh', 'permissions': '0700', 'content': script},
        ])
        config['runcmd'].append(['/bin/bash', '/root/fixture-client.sh'])
    network = {'version': 2, 'ethernets': {
        'public0': {'match': {'macaddress': nat_mac}, 'set-name': 'eth0', 'dhcp4': True,
                    'dhcp6': False, 'accept-ra': False},
        'outside0': {'match': {'macaddress': lan_mac}, 'set-name': 'eth1',
                     'addresses': ['198.18.0.' + str(index) + '/24',
                                   'fd42:2204:1::' + str(index) + '/64'],
                     'dhcp4': False, 'dhcp6': False, 'accept-ra': False},
    }}
    (directory / 'user-data').write_text('#cloud-config\n' + json.dumps(config))
    (directory / 'meta-data').write_text(json.dumps({'instance-id': 'fixture-' + name,
                                                   'local-hostname': config['hostname']}))
    (directory / 'network').write_text(json.dumps(network))
    run(['cloud-localds', '--network-config=' + str(directory / 'network'),
         str(directory / 'seed.iso'), str(directory / 'user-data'), str(directory / 'meta-data')])
    run(['qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', str(WORK / 'ubuntu-base.img'),
         str(directory / 'disk.qcow2'), '20G'])
    return directory, nat_mac, lan_mac


def boot(name, index, port):
    directory, nat_mac, lan_mac = seed(name, index)
    accelerated = os.access('/dev/kvm', os.R_OK | os.W_OK)
    REPORT['acceleration'] = 'kvm' if accelerated else 'tcg'
    args = ['qemu-system-x86_64', '-machine', 'q35', '-accel', 'kvm' if accelerated else 'tcg',
            '-cpu', 'host' if accelerated else 'max', '-m', '2048' if name == 'target' else '1024',
            '-smp', '2' if name == 'target' else '1', '-display', 'none',
            '-serial', 'file:' + str(directory / 'console.log'),
            '-qmp', 'unix:' + str(directory / 'qmp.sock') + ',server=on,wait=off',
            '-drive', 'file=' + str(directory / 'disk.qcow2') + ',if=virtio,format=qcow2',
            '-drive', 'file=' + str(directory / 'seed.iso') + ',format=raw,media=cdrom,readonly=on',
            '-netdev', 'user,id=wan,hostfwd=tcp:127.0.0.1:' + str(port) + '-:22',
            '-device', 'virtio-net-pci,netdev=wan,mac=' + nat_mac,
            '-netdev', 'socket,id=lan,' + ('listen=127.0.0.1:4321' if name == 'target' else 'connect=127.0.0.1:4321'),
            '-device', 'virtio-net-pci,netdev=lan,mac=' + lan_mac]
    log = (directory / 'qemu.log').open('w')
    process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
    PROCESSES.append((process, log))
    return process


def wait_factory(port, process, timeout=900):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('QEMU exited before SSH readiness.')
        try:
            text = factory(port, 'cloud-init status --wait', timeout=30)
            if 'status: done' in text:
                return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        time.sleep(5)
    raise RuntimeError('Fresh guest did not finish cloud-init.')


def vm_diagnostics():
    for name in ('target', 'client'):
        path = WORK / name / 'qmp.sock'
        if not path.exists():
            continue
        observation = {}
        try:
            observation['status'] = qmp_command(path, 'query-status')
            # Capture only the VGA display, never memory/disks/daemon state.
            # Fixture passwords are entered over SSH, not on this console.
            qmp_command(path, 'screendump', {'filename': str(WORK / 'public' / (name + '-display.ppm'))})
        except (OSError, ValueError, RuntimeError) as error:
            observation['error'] = redact(str(error))
        (WORK / 'public' / (name + '-qmp.json')).write_text(json.dumps(observation, indent=2))


def baseline_reboot(process):
    previous = factory(2222, 'cat /proc/sys/kernel/random/boot_id')
    try:
        factory(2222, 'systemctl reboot', timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass  # Boot-ID change below is the required evidence, not SSH closure.
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('QEMU exited during vanilla Ubuntu reboot.')
        try:
            observed = factory(2222, 'cat /proc/sys/kernel/random/boot_id', timeout=15)
            uuid.UUID(observed)
            if observed != previous:
                wait_factory(2222, process)
                REPORT['checks']['vanilla_ubuntu_reboot'] = True
                return
        except (subprocess.SubprocessError, ValueError):
            pass
        time.sleep(5)
    raise RuntimeError('Vanilla Ubuntu did not return after reboot, before installer execution.')


def outside_probe(port):
    code = """import json,socket
result={}
for ip in ['198.18.0.10','fd42:2204:1::10']:
 try:
  s=socket.create_connection((ip,PORT),3);s.close();result[ip]=True
 except OSError:result[ip]=False
print('LABJSON:'+json.dumps(result))
""".replace('PORT', str(port))
    return mark_json(factory(2223, py_command(code)))


def enroll_target():
    # Genuine enrollment at the ordinary password/login pause. Production code
    # is unchanged; no bypass flag or fabricated access receipt is used.
    file = WORK / 'private/target-authkey'
    file.write_text(SECRETS['target_authkey'])
    file.chmod(0o600)
    run(['scp', '-P', '2222', '-i', str(KEY), '-o', 'BatchMode=yes',
         '-o', 'StrictHostKeyChecking=accept-new', '-o', 'UserKnownHostsFile=/work/private/factory_known_hosts',
         str(file), 'root@127.0.0.1:/root/fixture-authkey'])
    factory(2222, 'tailscale up --login-server=' + shlex.quote(META['control_url'])
            + ' --auth-key=file:/root/fixture-authkey --hostname=vpslab --ssh && rm /root/fixture-authkey', timeout=90)
    REPORT['checks']['fixture_enrollment_without_production_credentials'] = True


def mesh_diagnostics(label):
    # Explicitly select non-secret fixture network fields, never daemon state/keys.
    status_code = """import json,subprocess
s=json.loads(subprocess.check_output(['tailscale','status','--json']))
fields=('HostName','DNSName','TailscaleIPs','Online')
print(json.dumps({'BackendState':s.get('BackendState'),'Health':s.get('Health'),
 'MagicDNSSuffix':s.get('MagicDNSSuffix'),
 'Self':{k:(s.get('Self') or {}).get(k) for k in fields},
 'Peer':[{k:p.get(k) for k in fields} for p in (s.get('Peer') or {}).values()]},indent=2))
"""
    for name, port in (('target', 2222), ('client', 2223)):
        text = ''
        try:
            text = factory(port, py_command(status_code), timeout=30)
            text += '\n' + factory(port, 'resolvectl status; cat /etc/resolv.conf; '
                                   'getent ahosts vpslab; resolvectl query vpslab; '
                                   'resolvectl query vpslab.fixture.test; '
                                   'resolvectl query --type=AAAA vpslab.fixture.test; '
                                   'getent ahostsv6 vpslab; ip -6 addr; ip -6 route', timeout=30)
        except (subprocess.SubprocessError, OSError) as error:
            text += '\n' + str(error)
            if isinstance(error, subprocess.CalledProcessError):
                text += '\n' + (error.stdout or '') + (error.stderr or '')
        (WORK / 'public' / (label + '-' + name + '-mesh.txt')).write_text(redact(text))


def wait_magicdns():
    deadline = time.monotonic() + 90
    while True:
        try:
            factory(2223, 'getent ahosts vpslab', timeout=15)
            REPORT['checks']['client_magicdns_resolves_target'] = True
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if time.monotonic() >= deadline:
                mesh_diagnostics('dns-failure')
                raise RuntimeError('Client MagicDNS did not resolve vpslab; inspect mesh diagnostics.')
            time.sleep(3)


def installer_session(fail_first=False):
    executable = '/root/candidate/install.sh' if fail_first else '/usr/bin/python3 -I -B /opt/lab-bootstrap/source/labbootstrap/installer.py'
    command = ('bash ' if fail_first else '') + executable + ' --apply --experimental' + ('' if fail_first else ' --resume')
    child = pexpect.spawn('ssh', ssh_args(2222, command, tty=True), encoding='utf-8',
                          codec_errors='replace', timeout=1200, dimensions=(50, 240))
    child.setecho(False)
    buffer = io.StringIO()
    child.logfile_read = buffer
    checkpoints = []
    enrolled = not fail_first
    expected_stop = False
    patterns = [r'Console/VNC provider[^\r\n]*\[y/N\]', r'Setuju membuat admin[^\r\n]*\[y/N\]',
                r'(?i)New password:', r'(?i)Retype new password:',
                CHECKPOINT_PATTERN, r'STOP:', pexpect.EOF]
    try:
        while True:
            event = child.expect(patterns)
            if event in (0, 1):
                child.sendline('y')
            elif event == 2:
                if not enrolled:
                    enroll_target()
                    enrolled = True
                child.sendline(SECRETS['admin_password'])
            elif event == 3:
                child.sendline(SECRETS['admin_password'])
            elif event == 4:
                purpose = child.match.group(1)
                child.expect(r'Sesudah verifier berhasil[^\r\n]*Enter:')
                if fail_first:
                    expected_stop = True
                    child.sendline('')
                    continue
                wait_magicdns()
                if purpose == 'after-lockdown':
                    probe = outside_probe(22)
                    if any(probe.values()):
                        raise RuntimeError('Non-tailnet SSH remained reachable after lockdown.')
                    REPORT['checks']['outside_ssh_blocked_ipv4_ipv6'] = probe
                output = peer('/usr/local/sbin/lab-verify-access --connection "$SSH_CONNECTION"', sudo=True)
                if 'Akses Tailscale dan sudo terbukti' not in output:
                    raise RuntimeError('Genuine access verifier did not confirm the peer.')
                checkpoints.append(purpose)
                REPORT['checks']['checkpoints'] = list(checkpoints)
                save_report()
                child.sendline('')
            elif event == 5:
                if not expected_stop:
                    raise RuntimeError('Installer reported STOP: ' + redact(buffer.getvalue()[-8000:]))
            else:
                break
        child.close()
        if fail_first:
            if not expected_stop or 'STOP:' not in buffer.getvalue():
                raise RuntimeError('Expected missing-receipt failure did not occur.')
        elif checkpoints != ['before-lockdown', 'after-lockdown', 'after-foundation']:
            raise RuntimeError('Not all three real SSH/sudo checkpoints completed.')
        REPORT['checks']['checkpoints'] = checkpoints
    finally:
        (WORK / 'public' / ('installer-first.txt' if fail_first else 'installer-resume.txt')).write_text(
            redact(buffer.getvalue())[-70000:])
        if child.isalive():
            child.close(force=True)


def acceptance():
    REPORT['emulator_packages'] = run(['dpkg-query', '-W', '-f=${Package} ${Version}\n',
                                      'qemu-system-x86', 'seabios'])
    stage('download-verified-ubuntu')
    download_image()
    stage('boot-two-real-guests')
    target = boot('target', 10, 2222)
    # Inspect our container's listen table without consuming the virtual Ethernet
    # stream intended for the second QEMU process.
    deadline = time.monotonic() + 30
    while not any(line.split()[1].endswith(':10E1') and line.split()[3] == '0A'
                  for line in Path('/proc/net/tcp').read_text().splitlines()[1:]):
        if target.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError('Target virtual Ethernet listener did not start.')
        time.sleep(0.2)
    client = boot('client', 20, 2223)
    wait_factory(2222, target)
    wait_factory(2223, client)
    stage('vanilla-ubuntu-reboot-before-installer')
    baseline_reboot(target)
    baseline = outside_probe(22)
    if not all(baseline.values()):
        raise RuntimeError('Fixture outside IPv4/IPv6 link was not reachable before lockdown.')
    REPORT['checks']['outside_ssh_open_before_install'] = baseline
    initial_boot = factory(2222, 'cat /proc/sys/kernel/random/boot_id')
    REPORT['target_initial_boot_id'] = initial_boot
    stage('stage-unmodified-candidate')
    candidate = WORK / META['candidate']
    run(['scp', '-P', '2222', '-i', str(KEY), '-o', 'BatchMode=yes',
         '-o', 'StrictHostKeyChecking=accept-new', '-o', 'UserKnownHostsFile=/work/private/factory_known_hosts',
         str(candidate), 'root@127.0.0.1:/root/candidate.tar.gz'])
    factory(2222, 'mkdir /root/candidate && tar -xzf /root/candidate.tar.gz -C /root/candidate --strip-components=1')
    stage('negative-checkpoint-must-not-lock-out')
    installer_session(fail_first=True)
    factory(2222, 'test ! -e /etc/ssh/sshd_config.d/00-lab-bootstrap.conf')
    if not all(outside_probe(22).values()):
        raise RuntimeError('Missing receipt caused premature lockdown.')
    REPORT['checks']['missing_receipt_preserves_initial_access'] = True
    REPORT['listeners_after_prepare'] = factory(2222, 'ss -H -ltn; ss -H -lun')
    mesh_diagnostics('after-prepare')
    stage('resume-and-three-genuine-checkpoints')
    installer_session(fail_first=False)
    receipt = mark_json(peer_sudo_shell(py_command(
        "import json;print('LABJSON:'+json.dumps(json.load(open('/var/lib/lab-bootstrap/result.json'))))")))
    if receipt['source_digest'] != META['source_digest']:
        raise RuntimeError('Installed source differs from candidate.')
    REPORT['checks']['unmodified_production_source_digest'] = True
    target_v6 = mark_json(peer(py_command(
        "import json,subprocess;print('LABJSON:'+json.dumps(subprocess.check_output(['tailscale','ip','-6'],text=True).strip()))")))
    if ipaddress.ip_address(target_v6) not in ipaddress.ip_network('fd7a:115c:a1e0::/48'):
        raise RuntimeError('Target did not report a fixture Tailscale IPv6 address.')
    REPORT['explicit_ipv6_transport_target'] = target_v6
    family_failures = {}
    for family in (4, 6):
        try:
            # Separate claims: ordinary hostname path remains mandatory above.
            # MagicDNS deliberately omits AAAA on dual-stack nodes (issue 1152),
            # so the explicit IPv6 transport probe uses the node's reported IP.
            if 'mesh-family-ok' not in peer('printf mesh-family-ok', family=family,
                                            host=target_v6 if family == 6 else 'vpslab'):
                raise RuntimeError('Private SSH address family check failed.')
            REPORT['checks']['private_ssh_ipv' + str(family)] = True
        except RuntimeError as error:
            family_failures[str(family)] = redact(str(error))
            REPORT['checks']['private_ssh_ipv' + str(family)] = False
            mesh_diagnostics('family-' + str(family) + '-failure')
        save_report()
    REPORT['checks']['private_ssh_ipv4_ipv6'] = not family_failures
    REPORT['family_failures'] = family_failures
    stage('real-private-container-and-public-side-probes')
    peer('cp -r ~/playground/_template ~/playground/fixture-web && cd ~/playground/fixture-web '
         '&& cp .env.example .env && chmod 600 .env && docker compose up -d', timeout=240)
    body = factory(2223, 'curl -4 --retry 10 --retry-connrefused --retry-delay 2 --max-time 10 -fsS http://vpslab:8080/', timeout=90)
    if 'Layanan contoh berjalan' not in body:
        raise RuntimeError('Private template service did not answer.')
    if any(outside_probe(8080).values()):
        raise RuntimeError('Docker service leaked onto a non-tailnet IPv4/IPv6 interface.')
    REPORT['checks']['private_http_works_public_side_blocked'] = True
    stage('rerun-preserves-fixture-data')
    fixture = """import hashlib,json,pathlib,sqlite3
p=pathlib.Path.home()/'playground/_fixture-do-not-touch';p.mkdir(exist_ok=True)
d=p/'sentinel.sqlite'
if not d.exists():
 c=sqlite3.connect(d);c.execute('create table fixture(value text)');c.execute('insert into fixture values (?)',('__TS_IP__ __HOSTNAME__',));c.commit();c.close()
f=p/'sentinel.pdf'
if not f.exists():f.write_bytes(b'%PDF-1.4 fixture __TS_IP__ __HOSTNAME__')
print('LABJSON:'+json.dumps({x.name:[hashlib.sha256(x.read_bytes()).hexdigest(),x.stat().st_ino,x.stat().st_uid,x.stat().st_gid] for x in p.iterdir()}))
"""
    before = mark_json(peer(py_command(fixture)))
    peer_sudo_shell('/usr/bin/python3 -I -B /opt/lab-bootstrap/source/labbootstrap/installer.py --apply --experimental --resume')
    after = mark_json(peer(py_command(fixture)))
    if before != after:
        raise RuntimeError('Rerun changed fixture data, inode, or ownership.')
    REPORT['checks']['rerun_preserves_hash_inode_uid_gid_with_container_running'] = True
    stage('reboot-and-reconnect')
    try:
        peer_sudo_shell('/usr/bin/systemctl reboot', timeout=30)
    except (RuntimeError, pexpect.EOF):
        pass  # Connection closure is normal; boot-ID change is the actual proof.
    REPORT['reboot_wait_seconds'] = 900
    deadline = time.monotonic() + REPORT['reboot_wait_seconds']
    while True:
        if target.poll() is not None:
            raise RuntimeError('Target QEMU process exited during reboot.')
        try:
            observed = mark_json(peer(py_command(
                "import json,pathlib;print('LABJSON:'+json.dumps(pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()))"),
                timeout=25))
            # Login-shell banners/logout text must never count as a changed ID.
            uuid.UUID(observed)
            if observed != initial_boot:
                REPORT['target_rebooted_boot_id'] = observed
                break
        except (RuntimeError, pexpect.TIMEOUT, pexpect.EOF):
            pass
        if time.monotonic() >= deadline:
            mesh_diagnostics('reboot-failure')
            raise RuntimeError('Target did not return through Tailscale after reboot.')
        time.sleep(5)
    factory(2223, 'curl -4 --retry 20 --retry-connrefused --retry-delay 2 --max-time 10 -fsS http://vpslab:8080/', timeout=120)
    if any(outside_probe(22).values()) or any(outside_probe(8080).values()):
        raise RuntimeError('Non-tailnet exposure reappeared after reboot.')
    if mark_json(peer(py_command(fixture))) != before:
        raise RuntimeError('Fixture data changed after reboot.')
    REPORT['checks']['reboot_ssh_docker_dns_and_firewall'] = True
    if family_failures:
        raise RuntimeError('Independent checks completed, but private SSH address family checks failed: '
                           + json.dumps(family_failures))
    REPORT['status'] = 'passed-isolated-control-plane'
    REPORT['limitations'] = ['Commercial Tailscale browser/account login not exercised',
                             'Outside NIC is simulated, not Contabo public routing',
                             'Provider reinstall panel and recovery console not exercised']
    stage('completed')


if __name__ == '__main__':
    try:
        acceptance()
    except Exception as error:
        REPORT['status'] = 'failed'
        REPORT['error'] = redact(str(error))
        save_report()
        vm_diagnostics()
        try:
            (WORK / 'public/listeners-at-failure.txt').write_text(
                redact(factory(2222, 'ss -H -ltn; ss -H -lun', timeout=15)))
        except (subprocess.SubprocessError, OSError):
            pass
        for name in ('target', 'client'):
            for filename in ('console.log', 'qemu.log'):
                path = WORK / name / filename
                if path.exists():
                    (WORK / 'public' / (name + '-' + filename)).write_text(
                        redact(path.read_text(errors='replace')[-40000:]))
        print('VM acceptance failed at', REPORT.get('stage'), ':', redact(str(error))[-12000:], flush=True)
        raise SystemExit(1)
    finally:
        for process, log in PROCESSES:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
            log.close()
        save_report()
