# Evidence path dan syarat rilis

Status: saat ini **hanya** guard/dokumentasi/template yang diuji. Playbook baru
belum ada; tidak ada klaim pengujian instalasi Ubuntu atau jaringan nyata.

## Klaim, pemilik, dan bukti minimum

| Klaim | Pemilik bukti | Bukti minimum |
|---|---|---|
| Entry point audit tidak mengubah host | Test suite repo | Help/rencana/penolakan termasuk pipe input; config berisi sentinel tidak dieksekusi; fake privileged tools tidak terpanggil. |
| Rules tidak menjanjikan status yang belum dibuktikan | Reviewer repo | Template dan kontrak SSOT diperiksa; bukan audit aturan host aktif. |
| Installer baru berhasil di OS target | Pelaksana uji VM | Ubuntu 22.04 fresh, versi/image dicatat, install pertama dan receipt tanpa secret. |
| Gate akses benar-benar mendahului lockdown | Pelaksana uji VM + pemilik client | SSH dari perangkat Tailscale kedua, sudo, receipt tervalidasi; kegagalan/expiry receipt menolak lockdown. |
| Publik tertutup, privat bekerja | Pelaksana uji jaringan eksternal | Probe IPv4/IPv6 dari luar tailnet, SSH client dan endpoint Docker melalui tailnet; listener/socket rules juga diperiksa. |
| Rerun tidak merusak data | Pelaksana uji VM | Hash, inode, UID/GID fixture data dan config unrelated sebelum/sesudah; tidak ada restart tak perlu. |
| Reboot/recovery bekerja | Pelaksana uji VM + pemilik console | Reboot terencana, SSH dan layanan kembali; kegagalan dapat dipulihkan lewat console. |

## Tes yang boleh dijalankan di checkout sekarang

```bash
bash -n bootstrap.sh
bash -n legacy/bootstrap.sh
python3 -B -m unittest discover -s tests -v
git diff --check
```

Tidak butuh root, Docker socket, akses layanan aktif, package install, atau
rahasia. Test suite membuat fixture sementara saja, lalu membersihkan fixture
sendiri. Ini bukan verifikasi efek jaringan atau body arsip lama.

## Matriks wajib sebelum rilis installer baru

- Ubuntu 22.04 image minimal, awal root SSH password atau key sesuai provider.
- Tailscale baru, sudah login, session expired, nama vpslab bentrok, ACL menolak,
  MagicDNS mati, client belum tersambung.
- Gate tidak dijawab, receipt kedaluwarsa/salah instance/salah user, sudo gagal,
  verifier menerima input tak valid; tidak boleh menghasilkan lockdown.
- UFW belum ada, aturan ALLOW lama, IPv6 aktif/tidak aktif, SSH socket activation.
- Disk tidak cukup, apt lock, cloud-init berjalan, download terputus, package
  upgrade memutus SSH; resume harus tidak melewati pemeriksaan akses.
- Swap existing aktif/nonaktif, Docker installed tanpa Compose, daemon.json existing,
  file/symlink rules existing; jangan menimpa resource yang bukan milik bootstrap.
- Rerun dengan DB/dokumen fixture di workspace: hash/inode/ownership tidak berubah.
- Docker publish contoh eksplisit IP Tailscale; tes dari luar tailnet, bukan hanya
  curl dari host sendiri. Tidak ada listener layanan pada 0.0.0.0/::/IP publik.
- Post-lockdown SSH baru + sudo, reboot, lalu ulangi verifikasi akses dan Docker.

Ansible syntax/check mode, lint, dan Molecule dapat menambah bukti, tetapi tidak
menggantikan VM/systemd dan client eksternal untuk firewall/SSH. Tidak menjalankan
matriks ini pada VPS aktif. VM/provider mutation perlu izin pemilik terlebih dulu.

## Gate publikasi

Sebelum menulis "siap install", simpan versi source/dependency, image OS dan
arsitektur, hasil tes per klaim, batas yang belum diuji, checksum artifact,
instruksi recovery console, serta review checkpoint privilege. Secret tidak boleh
masuk receipt, log, screenshot, atau artifact. Arsitektur yang belum diuji tidak
boleh dilabeli didukung. Branch/PR ini bukan rilis installer.
