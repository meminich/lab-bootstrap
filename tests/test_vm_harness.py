import importlib.util
import ipaddress
import os
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('vm_fixture_host', ROOT / 'tests/vm/run.py')
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


class VmHarnessSafety(unittest.TestCase):
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
