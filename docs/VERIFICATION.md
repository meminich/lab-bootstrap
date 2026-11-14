# Evidence path dan syarat rilis

Status: installer/playbook **eksperimental** tersedia. Guard, validasi config,
receipt, urutan gate/firewall, manifest, dependency lock, syntax Ansible, serta
render template dapat diuji tanpa privilege. Uji dua VM menghasilkan bukti parsial
di bawah; instalasi end-to-end belum lulus. Protokol: [CHECKPOINT](CHECKPOINT.md).

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
bash -n install.sh
python3 -B -m unittest discover -s tests -v
git diff --check
```

Tidak butuh root, Docker socket, akses layanan aktif, package install, atau
rahasia. Test suite membuat fixture sementara saja, lalu membersihkan fixture
sendiri. Ini bukan verifikasi efek jaringan atau body arsip lama.

Untuk syntax/render/dependency checks dengan controller terisolasi:

```bash
python3 -B scripts/check_playbooks.py --tooling-dir /tmp/opencode/lab-bootstrap-ci
```

Perintah ini mengunduh tooling/dependency yang dikunci hash ke direktori eksplisit,
tidak memasang paket OS, menjalankan playbook apply, atau memakai Docker socket.
Jika Docker CLI tersedia, tes Compose hanya menjalankan `config`, bukan `up`.

Paket kandidat untuk review/tes (bukan rilis produksi):

```bash
python3 -B scripts/build_candidate.py --output /tmp/opencode/lab-bootstrap-candidate
```

Artifact berisi seluruh payload, manifest file SHA256, status production_ready=false,
dan checksum archive. Tidak mengandung data runtime/secret atau source legacy.
Checksum konsistensi bukan pengganti autentikasi publisher; rilis resmi belum dibuat.

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

## Bukti VM parsial — 15 November 2026

Run [43643713232](https://github.com/meminich/lab-bootstrap/actions/runs/43643713232)
menguji commit `2ac8051e7f978a9406b022fce8d85e8ce5837b57`, payload sama. Semua gate,
hostname SSH, transport IPv4/IPv6, Docker privat/tidak bocor, dan integritas rerun
lulus. Reboot tetap tidak kembali setelah 900 detik; console berhenti di
`Restarting system`, QEMU belum exit, client melihat target offline. Uji berikutnya
memeriksa reboot Ubuntu polos dan mengambil observasi QMP/VGA; sebab belum pasti.

Run [43638905586](https://github.com/meminich/lab-bootstrap/actions/runs/43638905586)
menguji commit `ffb47659e0bd996e66fb728303488cd3ee3e94cc`, payload sama dengan digest
di bawah. Selain tiga checkpoint, HTTP container melalui tailnet/tidak melalui
interface luar lulus; rerun mempertahankan hash/inode/UID/GID fixture SQLite/PDF
saat container berjalan. Reboot belum kembali dalam 300 detik; serial console
terakhir mencapai `Restarting system`. Tes `ssh -6 vpslab` memakai asumsi AAAA
yang bertentangan dengan default Tailscale (issue 1152); tes berikutnya memisahkan
hostname normal dan transport IPv6 tanpa override DNS. Belum lulus end-to-end.

Run [43634852921](https://github.com/meminich/lab-bootstrap/actions/runs/43634852921)
menguji commit `93fdb238f6b63eb889171d24e27ab047d8c8925a`, dengan payload digest
di bawah. Ketiga checkpoint SSH/sudo terpisah lulus, termasuk bukti Docker group.
Probe client non-tailnet SSH IPv4/IPv6 berubah dari terbuka menjadi tertutup.
Installer menyelesaikan foundation dan result digest cocok. Tes lanjutan gagal
pada resolusi alamat `ssh -6 vpslab`; Docker HTTP/rerun/reboot belum dijalankan.
Ini bukti parsial, bukan kelulusan end-to-end atau kelulusan akun/provider pemilik.

Run [43632146448](https://github.com/meminich/lab-bootstrap/actions/runs/43632146448)
menguji commit `2e2e59a050dd32836e2484ef3d7faeabee191a0e` (payload sebelum koreksi
stream UFW). Dua kernel Ubuntu 22.04 berjalan dengan QEMU TCG dan Headscale privat.

- Lulus: boot, enrollment fixture, MagicDNS nama pendek, missing-receipt menolak
  lockdown sambil menjaga akses awal, SSH login shell + password sudo nyata,
  receipt before-lockdown diterima installer.
- Berhenti: UFW aktif tetapi progress stdout merusak parsing JSON Ansible.
- Belum terbukti: SSH baru setelah lockdown, checkpoint foundation, Docker privat,
  integritas rerun, dan reboot. Bukti sebelum perubahan bukan bukti payload terbaru.
- Tidak diuji: login SaaS/ACL akun pemilik, routing/image/console Contabo.

## Bukti lokal — diperbarui 15 November 2026

Payload digest: `586b2b46155719ff36d9f5c0bd6511eabc8380cb38b940ea1132e9245351c8b6`.

- **72 unit/regression tests lulus**: parser config, challenge/receipt kedaluwarsa
  dan salah instance/user/run, koneksi baru per checkpoint, urutan gate/failure,
  UFW tidak reset/disable, manifest drift/symlink, guard legacy, serta bundle
  roundtrip/checksum dan build berulang identik. Installer dari paket yang
  diekstrak benar-benar menjalankan plan tanpa membaca config.env atau membuat
  file tambahan, termasuk bytecode __pycache__ (wrapper dan direct Python entry).
  Readiness Docker juga menolak metadata IP yang belum benar-benar terpasang di
  interface kernel; perilaku API sebenarnya tetap perlu uji boot pada VM.
- **4 template/Compose checks lulus**: seluruh template dirender, YAML valid,
  mapping IP wajib, tanpa container_name tetap; Docker Compose `config` menerima
  env lengkap dan menolak IP kosong. Docker host diarahkan ke socket yang tidak
  ada dan config CLI kosong, sehingga tes tidak memakai daemon/credential nyata.
- **3 playbook lolos syntax-check** dengan ansible-core terkunci. Tidak ada
  playbook apply yang dijalankan.
- Bootstrap tooling dari direktori kosong diuji: uv wheel/binary SHA256, managed
  Python dan 9 dependency controller dipasang di direktori temporer eksplisit.
  Tidak mengganti Python OS atau memasang paket OS.

Ini bukti lokal kode/packaging, **bukan** bukti install Ubuntu 22.04 atau keamanan
jaringan. CI Ubuntu 22.04 menjalankan suite/syntax yang sama, bukan install host.
Belum ada uji VM fresh, PAM/Tailscale login nyata, probe dari luar tailnet, reboot,
atau percobaan recovery console. Tidak ada rilis produksi atau perubahan VPS aktif.
