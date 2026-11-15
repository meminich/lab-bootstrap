import importlib.util
import ipaddress
import ast
import io
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('vm_fixture_host', ROOT / 'tests/vm/run.py')
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


class VmHarnessSafety(unittest.TestCase):
    def test_policy_starts_with_real_ssh_denial_and_only_allows_fixture_admin(self):
        self.assertEqual(FIXTURE.fixture_policy(False)['ssh'], [])
        self.assertEqual(FIXTURE.fixture_policy(True)['ssh'][0]['users'], ['vpsadmin'])
        self.assertEqual(FIXTURE.fixture_policy(False)['acls'], FIXTURE.fixture_policy(True)['acls'])

    def test_policy_request_has_one_action_and_ack_only_after_reload(self):
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary)
            (private / 'allow-admin.request').write_text('allow-admin\n')
            process = MagicMock()
            process.wait.side_effect = [subprocess.TimeoutExpired('fixture', 1), 0]
            allow = MagicMock()
            self.assertEqual(FIXTURE.wait_guest(process, private, allow), 0)
            allow.assert_called_once_with()
            self.assertEqual((private / 'allow-admin.ack').read_text(), 'allow-admin\n')

    def test_failed_policy_reload_never_acknowledges_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary)
            (private / 'allow-admin.request').write_text('allow-admin\n')
            with self.assertRaises(RuntimeError):
                FIXTURE.wait_guest(MagicMock(), private, MagicMock(side_effect=RuntimeError('reload failed')))
            self.assertFalse((private / 'allow-admin.ack').exists())

    def test_policy_request_rejects_arbitrary_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary)
            (private / 'allow-admin.request').write_text('run arbitrary command')
            allow = MagicMock()
            with self.assertRaises(RuntimeError):
                FIXTURE.wait_guest(MagicMock(), private, allow)
            allow.assert_not_called()

    def test_modern_emulator_tools_do_not_change_jammy_guest_target(self):
        dockerfile = (ROOT / 'tests/vm/Dockerfile').read_text()
        self.assertTrue(dockerfile.startswith('FROM ubuntu:24.04@sha256:'))
        lock = json.loads((ROOT / 'tests/vm/fixtures.lock.json').read_text())
        self.assertIn('/jammy/', lock['ubuntu_image_url'])

    def test_qmp_observation_requires_matching_reply_and_rejects_errors(self):
        spec = importlib.util.spec_from_file_location('fixture_qmp', ROOT / 'tests/vm/qmp.py')
        qmp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(qmp)
        stream = io.BytesIO(b'{"event":"RESET"}\n{"id":1,"return":{"status":"running"}}\n')
        self.assertEqual(qmp.read_reply(stream, 1), {'status': 'running'})
        for data in (b'', b'{"id":1,"error":{"desc":"failed"}}\n'):
            with self.assertRaises(RuntimeError):
                qmp.read_reply(io.BytesIO(data), 1)

    def test_boot_id_parser_ignores_login_and_logout_text(self):
        tree = ast.parse((ROOT / 'tests/vm/guest_driver.py').read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'mark_json')
        namespace = {'json': json, 'redact': lambda text: text}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<mark_json>', 'exec'), namespace)
        boot_id = 'c6e6bdbc-7da2-4666-9663-b6c62cbe8f1a'
        output = 'Welcome\r\nLABJSON:' + json.dumps(boot_id) + '\r\nlogout\r\nConnection closed.\r\n'
        self.assertEqual(namespace['mark_json'](output), boot_id)
        with self.assertRaises(RuntimeError):
            namespace['mark_json']('logout\r\nConnection closed.\r\n')

    def test_peer_opens_login_shell_before_sudo_password_interaction(self):
        # Load only this function; importing the executable driver would read
        # generated fixture metadata and is deliberately not a host-safe API.
        tree = ast.parse((ROOT / 'tests/vm/guest_driver.py').read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'peer')
        child = MagicMock()
        child.before = 'verifier output'
        child.exitstatus = 0
        child.isalive.return_value = False
        pexpect = MagicMock()
        pexpect.spawn.return_value = child
        pexpect.EOF = EOFError
        pexpect.TIMEOUT = TimeoutError
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / 'public').mkdir()
            namespace = {'shlex': shlex, 'io': io, 'pexpect': pexpect, 'WORK': work,
                         'SECRETS': {'admin_password': 'generated-fixture-only'},
                         'redact': lambda text: text.replace('generated-fixture-only', '[redacted]'),
                         'ssh_args': lambda port, command, tty=False: [command]}
            exec(compile(ast.Module(body=[function], type_ignores=[]), '<peer>', 'exec'), namespace)
            self.assertEqual(namespace['peer']('/usr/local/sbin/lab-verify-access', sudo=True), 'verifier output')
            outer = pexpect.spawn.call_args.args[1][0]
            self.assertEqual(shlex.split(outer)[-1], 'vpsadmin@vpslab')
            self.assertNotIn('sudo', outer)
            sent = [call.args[0] for call in child.sendline.call_args_list]
            self.assertIn('LAB-SHELL-READY', sent[0])
            self.assertIn('sudo -k', sent[1])
            self.assertNotIn('sudo -S', sent[1])
            self.assertEqual(sent[2], 'generated-fixture-only')
            ready_pattern = child.expect.call_args_list[0].args[0]
            for ending in ('\n', '\r\n', '\r\r\n'):
                self.assertIsNotNone(re.search(ready_pattern, ending + 'LAB-SHELL-READY' + ending))
            namespace['peer']('printf mesh-family-ok', family=6, host='fd7a:115c:a1e0::2')
            ipv6 = shlex.split(pexpect.spawn.call_args.args[1][0])
            self.assertEqual(ipv6[-1], 'vpsadmin@fd7a:115c:a1e0::2')
            self.assertIn('-6', ipv6)
            child.exitstatus = 1
            namespace['peer']('/usr/local/sbin/lab-verify-access', sudo=True, reject_password=True)
            self.assertEqual(child.sendline.call_args.args[0], 'generated-fixture-only-wrong')
            child.sendcontrol.assert_called_with('d')
            child.exitstatus = 0
            with self.assertRaisesRegex(RuntimeError, 'Wrong sudo password unexpectedly succeeded'):
                namespace['peer']('/usr/local/sbin/lab-verify-access', sudo=True, reject_password=True)

    def test_fixture_reverse_dns_fits_jammy_resolved_domain_limit(self):
        prefix = ipaddress.ip_network(FIXTURE.headscale_config('172.30.0.2')['prefixes']['v4'])
        # Headscale v0.29.7 util.GenerateIPv4DNSRootDomain expands the next octet,
        # including an entire octet when prefixlen is byte-aligned (e.g. /24).
        reverse_domains = 1 << (8 - prefix.prefixlen % 8)
        self.assertLessEqual(reverse_domains + 2, 32)  # IPv6 route + base domain.
        self.assertIn(ipaddress.ip_address('100.64.0.1'), prefix)
        self.assertIn(ipaddress.ip_address('100.64.0.2'), prefix)

    def test_checkpoint_survives_tmux_cursor_movement_and_wrap(self):
        spec = importlib.util.spec_from_file_location('terminal_protocol', ROOT / 'tests/vm/terminal_protocol.py')
        protocol = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(protocol)
        gap = '\x1b[K\x1b[1;50r\x1b[49;12H\x1b[1;49r\x1b[49;1H\n\x1b[48;12H '
        for purpose in ('before-lockdown', 'after-lockdown', 'after-foundation'):
            for separator in (' ', gap):
                match = re.search(protocol.CHECKPOINT_PATTERN, 'CHECKPOINT:' + separator + purpose)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), purpose)

    def test_explicit_subnet_avoids_existing_docker_ranges(self):
        networks = [{'IPAM': {'Config': None}}, {'IPAM': {'Config': [{'Subnet': '172.16.0.0/16'},
                                         {'Subnet': '172.17.0.0/16'},
                                         {'Subnet': 'fd42::/64'}]}}]
        self.assertEqual(FIXTURE.fixture_subnet(networks), '172.18.0.0/24')

    def test_refuses_current_vps_before_creating_files_or_docker_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary) / 'must-not-be-created'
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}), \
                    patch.object(FIXTURE.subprocess, 'run') as run:
                with self.assertRaises(RuntimeError):
                    FIXTURE.main(work)
                run.assert_not_called()
                self.assertFalse(work.exists())

    def test_control_plane_has_no_public_derp_or_logtail(self):
        config = FIXTURE.headscale_config('172.30.0.2')
        self.assertEqual(config['derp']['urls'], [])
        self.assertFalse(config['derp']['auto_update_enabled'])
        self.assertFalse(config['logtail']['enabled'])
        self.assertTrue(config['server_url'].startswith('https://'))
        self.assertEqual(config['listen_addr'], '172.30.0.2:8080')

    def test_guest_image_is_dated_and_sha256_pinned(self):
        import json
        lock = json.loads((ROOT / 'tests/vm/fixtures.lock.json').read_text())
        self.assertNotIn('/current/', lock['ubuntu_image_url'])
        self.assertEqual(len(lock['ubuntu_image_sha256']), 64)
        self.assertIn('@sha256:', lock['headscale_image'])


if __name__ == '__main__':
    unittest.main()
