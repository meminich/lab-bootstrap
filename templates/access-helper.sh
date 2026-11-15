#!/bin/sh
# Root-owned, fixed path, no NOPASSWD sudoers rule.
exec /usr/bin/python3 -I -B /opt/lab-bootstrap/source/labbootstrap/checkpoint.py "$@"
