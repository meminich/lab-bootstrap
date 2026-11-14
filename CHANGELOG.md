# Changelog

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
