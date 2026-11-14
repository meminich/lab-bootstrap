# Changelog

## 2026-11-14 — Implementasi kandidat Ansible v2 (eksperimental)

- Tambahkan installer interaktif untuk Ubuntu 22.04 amd64, Ansible lokal dengan
  Python controller terpisah, dan dependency/tooling dipin SHA256.
- Fase prepare → checkpoint SSH/sudo → lockdown tanpa UFW reset → checkpoint →
  fondasi/Docker/workspace → checkpoint akhir dengan akses Docker sebagai admin.
- Tambahkan state/manifest milik installer, resume source yang sama, guard drift,
  tmux untuk menghadapi SSH disconnect, dan startup Docker yang menunggu IP tailnet.
- Template hanya dirender lewat allowlist; tidak ada chown/render seluruh workspace,
  auto-prune/reboot, perubahan policy tailnet, atau pemasangan aplikasi/restore data.
- Tambahkan unit/mock tests, syntax Ansible, render/Compose config checks, dan
  paket kandidat lengkap beserta manifest/checksum; bukan rilis produksi.
- Batas: belum dites install VM fresh, SSH Tailscale nyata, probe publik, atau reboot.
  Apply memerlukan --experimental pada target disposable yang disetujui.
- Tidak menjalankan apply atau mengubah layanan/rules VPS aktif. Rollback source
  lewat review Git; jangan kembali menjalankan body legacy yang tidak aman.

## 2026-11-14 — Audit keselamatan dan desain v2

- Blokir installer lama dan arsipkan source sebagai referensi. Entry point root
  hanya help/rencana, bukan instalasi; belum ada installer Ansible baru.
- Cabut klaim siap pakai/idempotent dan instruksi pipe-to-Bash dari README.
- Tambahkan desain Ubuntu 22.04, evidence path, serta template aturan host/workspace
  yang memisahkan instruksi, status, inventaris, dan otorisasi data.
- Tambahkan tes regresi tanpa privilege dan CI untuk guard/template/dokumentasi.
- Dampak: checkout versi ini tidak bisa memasang VPS. Host aktif tidak berubah.
  Rollback perubahan repo melalui review commit; jangan menjalankan source lama
  sebagai jalan pintas karena temuan keselamatan masih berlaku.
