"""Recognize installer prompts across tmux cursor movement and line wrapping."""
import re

TERMINAL_GAP = r'(?:\s|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[()][0-2A-Z])*'
CHECKPOINT_PATTERN = r'CHECKPOINT:' + TERMINAL_GAP + r'(before-lockdown|after-lockdown|after-foundation)'


def command_exit_status(transcript):
    values = re.findall(r'^LAB-PEER-EXIT:([0-9]+)$', transcript.replace('\r', ''), re.M)
    if len(values) != 1 or not 0 <= int(values[0]) <= 255:
        raise RuntimeError('Missing or ambiguous remote command exit status.')
    return int(values[0])
