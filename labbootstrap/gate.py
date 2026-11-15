#!/usr/bin/env python3
"""Validate the current before-lockdown receipt immediately before mutations."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from labbootstrap.common import (STATE_DIR, identity, load_json, private_directory,
                                 private_file, validate_receipt, SafetyError)


def check(purpose='before-lockdown'):
    private_directory(STATE_DIR)
    state = load_json(private_file(STATE_DIR / 'state.json'))
    challenge = load_json(private_file(STATE_DIR / 'challenge.json'))
    receipt = load_json(private_file(STATE_DIR / 'receipt.json'))
    validate_receipt(receipt, challenge, state, identity())
    if challenge['purpose'] != purpose:
        raise SafetyError('Receipt tidak cocok dengan fase yang akan dijalankan.')
    if state.get('prepared') is not True:
        raise SafetyError('Fase persiapan belum selesai.')
    if (purpose == 'before-lockdown' and state.get('locked_down')) or (
            purpose == 'after-lockdown' and not state.get('locked_down')):
        raise SafetyError('State fase tidak cocok dengan gate.')


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('--foundation', action='store_true')
        args = parser.parse_args()
        check('after-lockdown' if args.foundation else 'before-lockdown')
    except (SafetyError, OSError, ValueError, KeyError) as error:
        print('STOP:', error, file=sys.stderr)
        sys.exit(1)
