"""Recognize installer prompts across tmux cursor movement and line wrapping."""

TERMINAL_GAP = r'(?:\s|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[()][0-2A-Z])*'
CHECKPOINT_PATTERN = r'CHECKPOINT:' + TERMINAL_GAP + r'(before-lockdown|after-lockdown|after-foundation)'
