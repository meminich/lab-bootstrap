#!/usr/bin/env python3
"""Converge UFW without reset/disable or a fail-open rollback."""

import json
import os
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labbootstrap.common import SafetyError, output, run  # noqa: E402

DESIRED = ['allow', 'in', 'on', 'tailscale0']


def rules_to_remove(report):
    result = []
    for line in report.splitlines():
        if not line.startswith('ufw '):
            continue
        arguments = shlex.split(line)[1:]
        if arguments == DESIRED:
            continue
        if not arguments or arguments[0] not in ('allow', 'deny', 'reject', 'limit', 'route'):
            raise SafetyError('Format aturan UFW tidak dikenal; perlu review melalui console.')
        result.append(arguments)
    return result


def ufw_command(args):
    # stdout is a machine-readable JSON protocol consumed by Ansible.
    # Keep UFW progress on stderr, including when invoked directly from the CLI.
    return run(args, stdout=sys.stderr)


def converge(invoke=ufw_command, read=output):
    # Add and activate the recovery interface BEFORE deleting public allowances.
    before = read(['/usr/sbin/ufw', 'show', 'added'])
    stale = rules_to_remove(before)
    invoke(['/usr/sbin/ufw', *DESIRED])
    invoke(['/usr/sbin/ufw', 'default', 'deny', 'incoming'])
    invoke(['/usr/sbin/ufw', 'default', 'allow', 'outgoing'])
    invoke(['/usr/sbin/ufw', '--force', 'enable'])
    for rule in stale:
        invoke(['/usr/sbin/ufw', '--force', 'delete', *rule])
    invoke(['/usr/sbin/ufw', 'reload'])
    remaining = read(['/usr/sbin/ufw', 'show', 'added'])
    status = read(['/usr/sbin/ufw', 'status', 'verbose'])
    if rules_to_remove(remaining) or 'ufw allow in on tailscale0' not in remaining:
        raise SafetyError('UFW belum konvergen. Jangan membuka publik; gunakan console.')
    if 'Status: active' not in status or 'deny (incoming)' not in status:
        raise SafetyError('UFW belum aktif dengan default deny.')
    return {'changed': bool(stale) or before != remaining, 'firewall': 'configured'}


if __name__ == '__main__':
    try:
        if os.geteuid() != 0:
            raise SafetyError('Firewall helper memerlukan root.')
        from labbootstrap.gate import check
        check()
        print(json.dumps(converge()))
    except (SafetyError, OSError, ValueError) as error:
        print('STOP:', error, file=sys.stderr)
        sys.exit(1)
