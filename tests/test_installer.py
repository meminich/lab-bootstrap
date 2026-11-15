"""Pure/mock tests only: never apply configuration to the machine running tests."""
import contextlib
import ast
import io
import json
from pathlib import Path
import subprocess
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from labbootstrap import common, firewall, installer, wait_tailnet

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_resume_only_allows_exact_local_tailscale_peerapi_endpoints(self):
        status = {'BackendState': 'Running', 'TailscaleIPs': ['100.64.0.2', 'fd7a:115c:a1e0::2'],
                  'Self': {'PeerAPIURL': ['http://100.64.0.2:34567',
                                         'http://[fd7a:115c:a1e0::2]:45678']}}
        expected = installer.tailscale_peer_listeners(status)
        self.assertEqual(expected, {('100.64.0.2', '34567'), ('fd7a:115c:a1e0::2', '45678')})
        for endpoint in ('100.64.0.2:34567', '[fd7a:115c:a1e0::2]:45678',
                         '100.64.0.2%tailscale0:34567', '[fd7a:115c:a1e0::2]%tailscale0:45678'):
            installer.check_listeners('LISTEN 0 4096 ' + endpoint + ' *:*', expected_tcp=expected)
        for endpoint in ('0.0.0.0:34567', '100.64.0.3:34567', '100.64.0.2:8080'):
            with self.assertRaises(common.SafetyError):
                installer.check_listeners('LISTEN 0 4096 ' + endpoint + ' *:*', expected_tcp=expected)
        with self.assertRaises(common.SafetyError):
            installer.check_listeners('LISTEN 0 4096 100.64.0.2:34567 *:*')
        self.assertEqual(installer.tailscale_peer_listeners({**status, 'BackendState': 'Stopped'}), set())

    def test_peerapi_urls_cannot_allow_public_or_other_nodes_listeners(self):
        status = {'BackendState': 'Running', 'TailscaleIPs': ['100.64.0.2'],
                  'Self': {'PeerAPIURL': ['http://0.0.0.0:8080', 'http://100.64.0.3:8080',
                                         'http://100.64.0.2:0', 'http://100.64.0.2:99999',
                                         'http://user@100.64.0.2:8080', 'http://100.64.0.2:8080/bad']},
                  'Peer': {'other': {'PeerAPIURL': ['http://100.64.0.2:8080']}}}
        self.assertEqual(installer.tailscale_peer_listeners(status), set())

    def test_defaults_do_not_inherit_shell_hostname(self):
        with patch.dict('os.environ', {'HOSTNAME': 'unrelated'}):
            self.assertEqual(common.validated_config({})['hostname'], 'vpslab')

    def test_invalid_or_executable_data_is_rejected(self):
        for value in (
            {'admin_user': 'root'}, {'admin_user': '../vpsadmin'},
            {'hostname': '{{ lookup("pipe", "id") }}'}, {'hostname': '-bad'},
            {'timezone': '../../etc/passwd'}, {'swap_gib': True}, {'swap_gib': 99},
            {'admin_password': 'never-store-this'}, {'unknown': 'x'}, [],
        ):
            with self.subTest(value=value), self.assertRaises(common.SafetyError):
                common.validated_config(value)

    def test_explicit_json_fields_are_supported(self):
        config = common.validated_config({'hostname': 'test-lab', 'swap_gib': 0})
        self.assertEqual(config['hostname'], 'test-lab')
        self.assertEqual(config['swap_gib'], 0)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.state = {'run_id': 'r', 'source_digest': 's', 'admin_user': 'vpsadmin',
                      'tailscale_ip': '100.100.0.2'}
        self.identity = {'machine_id': 'machine', 'boot_id': 'boot'}
        self.challenge = {**self.state, **self.identity, 'purpose': 'before-lockdown',
                          'nonce': 'a' * 64, 'issued': 1000, 'expires': 1900}
        self.receipt = {**self.challenge, 'connection': '100.100.0.1 5555 100.100.0.2 22',
                        'peer_id': '123', 'peer_login': 'owner@example.test'}

    def test_valid_receipt(self):
        common.validate_receipt(self.receipt, self.challenge, self.state, self.identity, 1100)

    def test_wrong_run_user_source_boot_machine_or_nonce_rejected(self):
        for key in ('run_id', 'source_digest', 'admin_user', 'boot_id', 'machine_id', 'nonce', 'purpose'):
            with self.subTest(key=key), self.assertRaises(common.SafetyError):
                receipt = {**self.receipt, key: 'wrong'}
                common.validate_receipt(receipt, self.challenge, self.state, self.identity, 1100)

    def test_expired_future_and_invalid_timestamp_rejected(self):
        for now in (999, 1900, 2000, float('nan')):
            with self.subTest(now=now), self.assertRaises(common.SafetyError):
                common.validate_challenge(self.challenge, self.state, self.identity, now)
        for expires in (2001, '1900', True):
            with self.subTest(expires=expires), self.assertRaises(common.SafetyError):
                common.validate_challenge({**self.challenge, 'expires': expires},
                                          self.state, self.identity, 1100)

    def test_previous_run_challenge_rejected(self):
        with self.assertRaises(common.SafetyError):
            common.validate_challenge(self.challenge, {**self.state, 'run_id': 'new'}, self.identity, 1100)

    def test_absent_identity_not_accepted(self):
        with self.assertRaises(common.SafetyError):
            common.validate_challenge(self.challenge, {}, {}, 1100)

    def test_wrong_destination_or_empty_identity_rejected(self):
        for values in ({'connection': '100.100.0.1 5555 100.100.0.9 22'}, {'peer_id': ''}):
            with self.subTest(values=values), self.assertRaises(common.SafetyError):
                common.validate_receipt({**self.receipt, **values}, self.challenge,
                                        self.state, self.identity, 1100)

    def test_final_checkpoint_requires_actual_docker_access(self):
        challenge = {**self.challenge, 'purpose': 'after-foundation'}
        receipt = {**self.receipt, 'purpose': 'after-foundation'}
        with self.assertRaises(common.SafetyError):
            common.validate_receipt(receipt, challenge, self.state, self.identity, 1100)
        common.validate_receipt({**receipt, 'docker_access': True}, challenge,
                                self.state, self.identity, 1100)

    def test_post_change_gate_requires_a_new_ssh_connection(self):
        challenge = {**self.challenge, 'previous_connections': [self.receipt['connection']]}
        receipt = {**self.receipt, 'previous_connections': [self.receipt['connection']]}
        with self.assertRaises(common.SafetyError):
            common.validate_receipt(receipt, challenge, self.state, self.identity, 1100)
        common.validate_receipt({**receipt, 'connection': '100.100.0.1 5556 100.100.0.2 22'},
                                challenge, self.state, self.identity, 1100)

    def test_connection_tuple_rejects_public_loopback_self_or_bad_port(self):
        for connection in (
            '', '127.0.0.1 5555 100.100.0.2 22', '1.2.3.4 5555 100.100.0.2 22',
            '100.100.0.1 5555 100.100.0.2 23', '100.100.0.1 0 100.100.0.2 22',
            '100.100.0.2 5555 100.100.0.2 22', 'bad 5 bad 22',
        ):
            with self.subTest(connection=connection), self.assertRaises(common.SafetyError):
                common.connection_tuple(connection)

    def test_whois_must_map_the_actual_peer(self):
        status = {'TailscaleIPs': ['100.100.0.2']}
        whois = {'Node': {'ID': 1, 'Addresses': ['100.100.0.1/32']},
                 'UserProfile': {'LoginName': 'owner@example.test'}}
        peer = common.validate_peer(self.receipt['connection'], status, whois)
        self.assertEqual(peer['source'], '100.100.0.1')
        for bad in ({}, {**whois, 'UserProfile': {}},
                    {**whois, 'Node': {'ID': 1, 'Addresses': ['100.100.0.9/32']}}):
            with self.subTest(bad=bad), self.assertRaises(common.SafetyError):
                common.validate_peer(self.receipt['connection'], status, bad)

    def test_ipv6_tailnet_tuple(self):
        result = common.connection_tuple('fd7a:115c:a1e0::1 5555 fd7a:115c:a1e0::2 22')
        self.assertEqual(result[1], 'fd7a:115c:a1e0::2')

    def test_ipv6_receipt_accepts_this_hosts_assigned_ipv6_address(self):
        state = {**self.state, 'tailscale_ips': ['100.100.0.2', 'fd7a:115c:a1e0::2']}
        receipt = {**self.receipt, 'connection': 'fd7a:115c:a1e0::1 5555 fd7a:115c:a1e0::2 22'}
        common.validate_receipt(receipt, self.challenge, state, self.identity, 1100)
        with self.assertRaises(common.SafetyError):
            common.validate_receipt({**receipt, 'connection': 'fd7a:115c:a1e0::1 5555 fd7a:115c:a1e0::9 22'},
                                    self.challenge, state, self.identity, 1100)


class FirewallTests(unittest.TestCase):
    def test_ufw_progress_does_not_contaminate_json_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        def noisy_command(args, **kwargs):
            print('Rules updated', file=kwargs['stdout'])
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                patch.object(firewall, 'run', side_effect=noisy_command):
            firewall.ufw_command(['/usr/sbin/ufw', 'reload'])
            print(json.dumps({'changed': True, 'firewall': 'configured'}))
        self.assertEqual(json.loads(stdout.getvalue()), {'changed': True, 'firewall': 'configured'})
        self.assertIn('Rules updated', stderr.getvalue())

    def test_recovery_allowance_and_enable_precede_public_rule_removal(self):
        calls = []
        before = 'Added user rules (see ufw status for running firewall):\nufw allow 22/tcp\nufw allow 80/tcp\n'
        after = 'ufw allow in on tailscale0\n'
        responses = iter((before, after, 'Status: active\nDefault: deny (incoming), allow (outgoing)'))
        result = firewall.converge(invoke=lambda args: calls.append(args), read=lambda args: next(responses))
        self.assertTrue(result['changed'])
        first_delete = next(i for i, call in enumerate(calls) if 'delete' in call)
        enable = calls.index(['/usr/sbin/ufw', '--force', 'enable'])
        self.assertLess(enable, first_delete)
        self.assertEqual(calls[0], ['/usr/sbin/ufw', 'allow', 'in', 'on', 'tailscale0'])
        self.assertFalse(any('reset' in call or 'disable' in call for call in calls))

    def test_unknown_rule_is_rejected_before_mutation(self):
        calls = []
        with self.assertRaises(common.SafetyError):
            firewall.converge(invoke=lambda args: calls.append(args), read=lambda args: 'ufw unexpected 22')
        self.assertEqual(calls, [])

    def test_rule_deletion_failure_never_opens_firewall(self):
        calls = []
        def invoke(args):
            calls.append(args)
            if 'delete' in args:
                raise subprocess.CalledProcessError(1, args)
        with self.assertRaises(subprocess.CalledProcessError):
            firewall.converge(invoke=invoke, read=lambda args: 'ufw allow 22/tcp')
        self.assertFalse(any('disable' in call or 'reset' in call for call in calls))

    def test_public_allowances_remaining_fail_validation(self):
        responses = iter(('ufw allow 80/tcp', 'ufw allow 80/tcp', 'Status: active\ndeny (incoming)'))
        with self.assertRaises(common.SafetyError):
            firewall.converge(invoke=lambda args: None, read=lambda args: next(responses))

    def test_routes_and_comments_are_data_not_shell(self):
        report = "ufw route allow from 10.0.0.0/8\nufw allow 80/tcp comment 'example; not a shell'"
        self.assertEqual(firewall.rules_to_remove(report)[0][0], 'route')
        self.assertEqual(firewall.rules_to_remove(report)[1][-1], 'example; not a shell')


class InstallerSafetyTests(unittest.TestCase):
    def test_private_state_file_rejects_symlink_wrong_owner_and_public_permissions(self):
        path = Path('/fixture/state.json')
        good = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0)
        with patch.object(Path, 'lstat', return_value=good):
            self.assertEqual(common.private_file(path), path)
        for mode, uid in ((stat.S_IFLNK | 0o600, 0), (stat.S_IFREG | 0o644, 0),
                          (stat.S_IFREG | 0o600, 1000)):
            with self.subTest(mode=mode, uid=uid), \
                    patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=mode, st_uid=uid)):
                with self.assertRaises(common.SafetyError):
                    common.private_file(path)

    def test_private_state_directory_rejects_symlink_wrong_owner_and_public_permissions(self):
        for mode, uid in ((stat.S_IFLNK | 0o700, 0), (stat.S_IFDIR | 0o755, 0),
                          (stat.S_IFDIR | 0o700, 1000)):
            with self.subTest(mode=mode, uid=uid), \
                    patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=mode, st_uid=uid)):
                with self.assertRaises(common.SafetyError):
                    common.private_directory(Path('/fixture/state'))

    def test_docker_waits_for_actual_interface_not_just_cached_tailnet_metadata(self):
        responses = [subprocess.CompletedProcess([], 0, '100.100.0.2\n'),
                     subprocess.CompletedProcess([], 0, '[]')]
        with patch.object(wait_tailnet.subprocess, 'run', side_effect=responses):
            self.assertFalse(wait_tailnet.address_ready('100.100.0.2'))

    def test_docker_bind_wait_accepts_assigned_tailnet_ip(self):
        responses = [subprocess.CompletedProcess([], 0, '100.100.0.2\n'),
                     subprocess.CompletedProcess([], 0, '[{"addr_info":[{"local":"100.100.0.2"}]}]')]
        with patch.object(wait_tailnet.subprocess, 'run', side_effect=responses):
            self.assertTrue(wait_tailnet.address_ready('100.100.0.2'))

    def test_all_python_source_parses_without_writing_bytecode(self):
        for path in ROOT.rglob('*.py'):
            with self.subTest(path=str(path.relative_to(ROOT))):
                ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

    def test_default_help_and_plan_need_no_root_network_or_mutations(self):
        for args in ([], ['--help'], ['--dry-run']):
            with self.subTest(args=args), patch.object(installer, 'preflight') as preflight, \
                    patch.object(installer, 'configure') as configure, \
                    patch('sys.argv', ['install', *args]), contextlib.redirect_stdout(io.StringIO()):
                if args == ['--help']:
                    with self.assertRaises(SystemExit) as result:
                        installer.main()
                    self.assertEqual(result.exception.code, 0)
                else:
                    installer.main()
                preflight.assert_not_called()
                configure.assert_not_called()

    def test_production_apply_is_blocked_before_any_preflight(self):
        with patch('sys.argv', ['install', '--apply']), patch.object(installer, 'preflight') as preflight:
            with self.assertRaises(common.SafetyError):
                installer.main()
            preflight.assert_not_called()

    def test_incomplete_payload_is_rejected_before_host_preflight(self):
        with patch('sys.argv', ['install', '--apply', '--experimental']), \
                patch('os.geteuid', return_value=0), \
                patch.object(installer, 'source_digest', side_effect=common.SafetyError('incomplete')), \
                patch.object(installer, 'preflight') as preflight:
            with self.assertRaises(common.SafetyError):
                installer.main()
            preflight.assert_not_called()

    def test_real_missing_runtime_files_are_rejected_by_source_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, source in common.source_files(ROOT):
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
            self.assertEqual(common.source_digest(root), common.source_digest(ROOT))
            for name in ('playbooks/lockdown.yml', 'labbootstrap/gate.py',
                         'templates/workspace/compose.yml.j2', 'requirements.lock'):
                file = root / name
                content = file.read_bytes()
                file.unlink()
                with self.subTest(missing=name), self.assertRaises(common.SafetyError):
                    common.source_digest(root)
                file.write_bytes(content)

    def test_no_skip_verify_or_yes_flag(self):
        for flag in ('--skip-verify', '--yes', '--force'):
            with self.subTest(flag=flag), patch('sys.argv', ['install', flag]), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    installer.main()
                self.assertEqual(result.exception.code, 2)

    def test_only_ssh_is_allowed_as_public_tcp_listener(self):
        installer.check_listeners('LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\nLISTEN 0 128 127.0.0.53:53 0.0.0.0:*')
        for report in ('LISTEN 0 128 0.0.0.0:80 0.0.0.0:*', 'LISTEN 0 128 [::]:443 [::]:*'):
            with self.subTest(report=report), self.assertRaises(common.SafetyError):
                installer.check_listeners(report)

    def test_unknown_public_udp_is_rejected(self):
        installer.check_listeners('UNCONN 0 0 0.0.0.0:68 0.0.0.0:*', udp=True)
        with self.assertRaises(common.SafetyError):
            installer.check_listeners('UNCONN 0 0 [::]:5353 [::]:*', udp=True)

    def test_loopback_application_is_not_mistaken_for_a_fresh_host(self):
        with self.assertRaises(common.SafetyError):
            installer.check_listeners('LISTEN 0 128 127.0.0.1:3306 0.0.0.0:*')

    def test_managed_file_manifest_never_includes_user_data_or_secrets(self):
        paths = installer.managed_paths(common.CONFIG_DEFAULTS)
        self.assertNotIn(Path('/root/AGENTS.md'), paths)
        self.assertFalse(any(p.name == '.env' or '.config/opencode' in str(p) for p in paths))
        self.assertTrue(all('/data/' not in str(p) or p.name == 'index.html' for p in paths))

    def test_manifest_detects_drift_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / 'managed'
            file.write_text('original')
            state = {'config': common.CONFIG_DEFAULTS, 'managed': {str(file): installer.file_record(file)}}
            with patch.object(installer, 'managed_paths', return_value=[file]):
                installer.validate_manifest(state)
                file.write_text('user edit')
                with self.assertRaises(common.SafetyError):
                    installer.validate_manifest(state)
                self.assertEqual(file.read_text(), 'user edit')

    def test_manifest_rejects_a_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'data'
            target.write_text('protected')
            link = Path(temporary) / 'managed'
            link.symlink_to(target)
            with self.assertRaises(common.SafetyError):
                installer.file_record(link)
            self.assertEqual(target.read_text(), 'protected')

    def test_digest_includes_ansible_configuration_but_not_legacy(self):
        names = {name for name, path in common.source_files(ROOT)}
        self.assertIn('playbooks/ansible.cfg', names)
        self.assertIn('requirements.lock', names)
        self.assertNotIn('legacy/bootstrap.sh', names)
        self.assertEqual(len(common.source_digest(ROOT)), 64)

    def test_failed_external_checkpoint_prevents_lockdown_and_foundation(self):
        state = {'config': common.CONFIG_DEFAULTS, 'admin_user': 'vpsadmin', 'prepared': True}
        with patch('labbootstrap.tooling.prepare', return_value='ansible'), \
                patch.object(installer, 'connect_tailscale'), \
                patch.object(installer, 'output', return_value='vpsadmin P'), \
                patch.object(installer, 'checkpoint', side_effect=common.SafetyError('missing')), \
                patch.object(installer, 'playbook') as playbook:
            with self.assertRaises(common.SafetyError):
                installer.configure(state, ROOT)
            playbook.assert_not_called()

    def test_failed_after_lockdown_checkpoint_prevents_foundation(self):
        state = {'config': common.CONFIG_DEFAULTS, 'admin_user': 'vpsadmin',
                 'prepared': True, 'locked_down': True}
        with patch('labbootstrap.tooling.prepare', return_value='ansible'), \
                patch.object(installer, 'connect_tailscale'), \
                patch.object(installer, 'output', return_value='vpsadmin P'), \
                patch.object(installer, 'checkpoint', side_effect=common.SafetyError('missing')), \
                patch.object(installer, 'playbook') as playbook:
            with self.assertRaises(common.SafetyError):
                installer.configure(state, ROOT)
            playbook.assert_not_called()

    def test_happy_path_order_requires_all_three_checkpoints(self):
        state = {'config': common.CONFIG_DEFAULTS, 'admin_user': 'vpsadmin',
                 'prepared': True, 'source_digest': 'digest'}
        events = []
        with patch('labbootstrap.tooling.prepare', return_value='ansible'), \
                patch.object(installer, 'connect_tailscale'), \
                patch.object(installer, 'output', return_value='vpsadmin P'), \
                patch.object(installer, 'checkpoint', side_effect=lambda s, phase: events.append(phase)), \
                patch.object(installer, 'playbook', side_effect=lambda phase, *args: events.append(phase)), \
                patch.object(installer, 'snapshot'), patch.object(installer, 'atomic_json'), \
                patch.object(installer, 'run'), contextlib.redirect_stdout(io.StringIO()):
            installer.configure(state, ROOT)
        self.assertEqual(events, ['before-lockdown', 'lockdown', 'after-lockdown',
                                  'foundation', 'after-foundation'])
        self.assertTrue(state['configured'])

    def test_single_use_receipt_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'receipt.json'
            common.atomic_json(path, {'nonce': 'first'}, exclusive=True)
            with patch.object(common, 'private_file', return_value=path):
                with self.assertRaises(FileExistsError):
                    common.atomic_json(path, {'nonce': 'second'}, exclusive=True)
            self.assertEqual(json.loads(path.read_text())['nonce'], 'first')


if __name__ == '__main__':
    unittest.main()
