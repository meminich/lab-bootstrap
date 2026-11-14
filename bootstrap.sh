#!/usr/bin/env bash
# Compatibility entry point. No config loading, privileged commands, or writes.
set -eu

case "${1:-}" in
  --help|-h)
    [[ $# -eq 1 ]] || { echo 'Gunakan --help atau --dry-run saja.' >&2; exit 2; }
    printf '%s\n' \
      'VPS Lab Bootstrap — installer baru BELUM tersedia.' \
      'Target desain: Ubuntu Server 22.04 LTS.' \
      'bash bootstrap.sh --dry-run : lihat desain, tanpa perubahan.' \
      'Script lama diblokir; lihat docs/AUDIT.md dan docs/DESIGN.md.'
    ;;
  --dry-run)
    [[ $# -eq 1 ]] || { echo 'Mode rencana tidak menerima opsi lain.' >&2; exit 2; }
    printf '%s\n' \
      'RENCANA DESAIN — BUKAN simulasi playbook yang sudah diimplementasikan.' \
      '1. Cek Ubuntu 22.04 fresh, akses console, dan kesiapan Tailscale client.' \
      '2. Siapkan admin vpsadmin, hostname vpslab, dan Ansible lokal.' \
      '3. Login Tailscale; buktikan SSH dari terminal kedua.' \
      '4. Lockdown setelah bukti akses; tes ulang SSH melalui Tailscale.' \
      '5. Docker + Compose, update policy, swap bila perlu, dan workspace.' \
      '6. Verifikasi akhir dan reboot terencana sebelum rilis dinyatakan siap.' \
      'Tidak membaca config, memasang paket, menulis log, atau mengubah host.'
    ;;
  *)
    printf '%s\n' \
      'STOP: installer baru belum dibuat dan diuji.' \
      'Script lama memiliki risiko perubahan data dan akses server.' \
      'Tidak ada konfigurasi host yang diubah. Baca README.md.' >&2
    exit 1
    ;;
esac
