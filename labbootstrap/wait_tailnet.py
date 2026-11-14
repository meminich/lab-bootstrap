#!/usr/bin/env python3
"""Docker start fails closed if its explicit Tailscale bind address is absent."""

import json
from pathlib import Path
import subprocess
import sys
import time


def address_ready(expected):
    result = subprocess.run(['/usr/bin/tailscale', 'ip', '-4'],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0 or expected not in result.stdout.splitlines():
        return False
    addresses = subprocess.run(['ip', '-j', '-4', 'addr', 'show', 'dev', 'tailscale0'],
                               env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'},
                               capture_output=True, text=True, check=False)
    if addresses.returncode != 0:
        return False
    try:
        return any(info.get('local') == expected for interface in json.loads(addresses.stdout)
                   for info in interface.get('addr_info', []))
    except (ValueError, TypeError, AttributeError):
        return False


def main():
    expected = json.loads(Path('/var/lib/lab-bootstrap/state.json').read_text())['tailscale_ip']
    for _ in range(60):
        if address_ready(expected):
            return 0
        time.sleep(1)
    print('IP Tailscale belum tersedia; Docker tidak dimulai.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
