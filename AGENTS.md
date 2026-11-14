# Kontribusi ke lab-bootstrap

Aturan ini untuk **source repo**, bukan aturan operasional VPS tujuan.
Template aturan VPS ada di `templates/`; jangan menerapkannya ke mesin kerja.

- Baca README, `docs/DESIGN.md`, dan `docs/VERIFICATION.md` sebelum mengubah kode.
- Target pertama Ubuntu Server 22.04 LTS. Jangan mengklaim dukungan distro lain.
- Jangan menjalankan bootstrap, playbook yang memodifikasi host, reset firewall,
  atau restart Docker/SSH di mesin kerja. Gunakan VM disposable dengan izin.
- Installer lama di `legacy/` hanya bukti audit. Jangan menghapus guard eksekusinya.
- Jangan membaca kredensial GitHub/provider, `.env`, private key, atau data layanan.
- Jangan mengubah AGENTS.md host aktif sebagai bagian dari perubahan template.
- Jangan bypass checkpoint akses, menambahkan `--skip-verify`, atau menganggap
  keberhasilan `tailscale ip` sebagai bukti login dari client.
- Konfigurasi adalah data, bukan shell yang di-`source`. Rahasia lewat prompt
  tersembunyi; jangan dimasukkan ke argumen CLI/log atau repo.
- Perubahan minimal dan bisa direview. Jangan menambah panel, daemon, atau cron
  tanpa kebutuhan yang disetujui.
- Tes aman saat ini: `bash -n bootstrap.sh`, `bash -n legacy/bootstrap.sh`, dan
  `python3 -B -m unittest discover -s tests -v`.
- Tes statis bukan bukti jaringan, keamanan, atau kesiapan rilis. Nyatakan batas
  hasil tes dan jangan menyebut installer siap sebelum syarat rilis terpenuhi.
- Perubahan repo dicatat di CHANGELOG.md repo, bukan changelog host.
