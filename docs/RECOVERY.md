# Recovery kandidat — jangan membuka publik untuk menyelamatkan akses

Panduan ini untuk **target installer yang diizinkan**, bukan instruksi mengubah
VPS lab aktif. Console/VNC provider dan akses akun eksternal harus tersedia sebelum
mulai. Prosedur console Contabo belum diuji otomatis; acceptance hanya memakai VM.

## Sebelum menginstal

- Simpan backup data di luar VPS dan verifikasi pemulihannya. Repo/kandidat ini
  hanya fondasi: tidak memulihkan data layanan, token, atau akun eksternal.
- Simpan seluruh archive kandidat + file `.sha256` dari sumber GitHub terpercaya.
  Di folder download, jalankan `sha256sum -c NAMA-ARCHIVE.tar.gz.sha256` dengan
  nama file sebenarnya. Hasil harus `OK`, lalu ekstrak seluruh archive, bukan
  hanya `install.sh`. Cek target Ubuntu 22.04 amd64 dan baca `CANDIDATE.json`.
- Checksum mendeteksi perubahan, bukan tanda tangan publisher. Jika archive dan
  checksum sama-sama diganti penyerang, checksum saja tidak melindungi.
- Jangan memakai URL `main` yang bergerak untuk rebuild. Catat commit/source
  digest kandidat, bukti acceptance yang cocok, serta batas pengujiannya.

## 1. Koneksi putus, installer mungkin masih hidup

Jangan langsung menjalankan installer kedua atau membunuh proses APT.

- Sebelum lockdown: login root melalui jalur awal, lalu `tmux attach -t lab-bootstrap`.
- Setelah Tailscale siap: `ssh vpsadmin@vpslab`, lalu
  `sudo tmux attach -t lab-bootstrap`.
- Jika nama admin/host diubah melalui config, gunakan identitas yang dipilih itu.
- Jika sesi tmux masih ada, lanjutkan di sana. Buka **sesi client baru** untuk
  checkpoint; sesi lama yang tetap terhubung tidak membuktikan akses baru.

## 2. Proses installer benar-benar berhenti

Gunakan **payload terpasang yang sama**, bukan source terbaru dari GitHub:

```bash
sudo /usr/bin/python3 -I -B /opt/lab-bootstrap/source/labbootstrap/installer.py --apply --experimental --resume
```

Dari console root, perintah sama tanpa `sudo`. Resume menolak source/config atau
file kelolaan yang berubah; jangan menghapus state/manifest agar lolos. Sesudah
lockdown, kegagalan tidak membuka firewall publik lagi. Resume meminta gate baru.

- Receipt expired: jangan edit TTL/clock/receipt. Hentikan proses yang sedang
  menunggu bila perlu, lalu resume untuk challenge baru dan ulangi verifier dari
  sesi SSH baru. Receipt lama tidak berlaku untuk run/boot berikutnya.
- Sudo gagal: periksa password/identitas admin secara normal. Jangan menambah
  `NOPASSWD` untuk memaksa verifier berhasil.
- ACL/MagicDNS menolak: pemilik memperbaiki policy/nama/login pada tailnet yang
  benar. Jangan ganti checkpoint dengan IP palsu, receipt buatan, atau hosts file.

## 3. SSH/Tailscale tidak bisa diakses

Masuk melalui **console provider**, bukan membuka port publik. Mulai dengan
diagnostik read-only berikut pada target:

```bash
systemctl status tailscaled ssh docker --no-pager
tailscale status
ip -br addr
ss -ltnp
ss -lunp
ufw status verbose
/usr/sbin/sshd -t
tmux list-sessions
```

- Jangan `ufw disable/reset`, menambah public ALLOW, mematikan Tailscale, atau
  mereset password/ACL tanpa keputusan pemilik.
- Jika preflight menolak socket asing/port acak, inspeksi pemiliknya dengan
  `ss -lunp`/`ss -ltnp`. Jangan memberi whitelist rentang port acak agar lolos;
  gate konservatif boleh menolak target yang belum bisa dibuktikan fresh.
- Docker sengaja gagal start bila IP bind Tailscale belum benar-benar ada.
  Perbaiki login/interface Tailscale terlebih dahulu; jangan mengganti bind ke
  wildcard atau menghapus guard Docker untuk mengejar status hijau.
- Playbook memvalidasi SSH sebelum reload dan membatasi rollback pada drop-in
  miliknya sendiri. Jika rollback/validasi gagal, inspeksi dari console; jangan
  menyalin konfigurasi SSH lain atau me-restart secara buta.
- Jangan mengunggah `.env`, private key, state daemon, atau database saat meminta
  bantuan. Bagikan hanya error/metadata yang sudah diperiksa dan disensor.

## 4. APT atau filesystem bermasalah

Tunggu pemegang lock selesai. Jangan menghapus lock APT/dpkg atau mematikan proses
yang sedang menulis paket. `dpkg --audit`, ruang disk, dan log paket bisa membantu
review. Kegagalan upgrade di tengah operasi dpkg tidak disamakan dengan tes
interupsi aman pada batas fase; perbaikan paket memerlukan review terpisah.

Jangan menjalankan bootstrap ulang untuk memperbaiki instalasi asing. Jika data
atau ownership berubah, berhenti dan gunakan backup/snapshot yang sudah diverifikasi.
Restore snapshot/reinstall adalah keputusan destruktif pemilik, bukan fallback
otomatis installer. Simpan bukti kegagalan terlebih dahulu.
