#!/usr/bin/env bash
# Run from a reviewed checkout/release directory, never from a stdin pipe.
set -eu
if [[ ! -f "${BASH_SOURCE[0]:-}" ]]; then
  echo 'Download/unpack seluruh paket installer dahulu; jangan gunakan curl | bash.' >&2
  exit 1
fi
DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 -I -B "$DIR/labbootstrap/installer.py" "$@"
