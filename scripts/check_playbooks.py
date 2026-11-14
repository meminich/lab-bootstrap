#!/usr/bin/env python3
"""Unprivileged CI: pinned controller, syntax only, and offline template checks."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from labbootstrap.tooling import prepare


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tooling-dir', type=Path, required=True)
    args = parser.parse_args()
    args.tooling_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = args.tooling_dir.resolve()
    ansible = prepare(ROOT, directory)
    environment = {
        'PATH': '/usr/bin:/bin', 'HOME': str(directory), 'LANG': 'C.UTF-8',
        'ANSIBLE_CONFIG': str(ROOT / 'playbooks/ansible.cfg'),
        'ANSIBLE_LOCAL_TEMP': str(directory / 'ansible-tmp'),
        'PYTHONDONTWRITEBYTECODE': '1',
    }
    for name in ('prepare', 'lockdown', 'foundation'):
        subprocess.run([str(ansible), '-i', 'localhost,', '-c', 'local', '--syntax-check',
                        str(ROOT / 'playbooks' / (name + '.yml'))], env=environment, check=True)
    subprocess.run([str(directory / 'venv/bin/python'), '-B',
                    str(ROOT / 'tests/check_templates.py')], env=environment, check=True)


if __name__ == '__main__':
    main()
