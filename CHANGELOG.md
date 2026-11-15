# Changelog

## 2026-11-15 — Gate negatif lulus, kandidat siap untuk merge

- Run 43664621533 pada fa93d86 lulus: ACL ditolak, sudo salah tidak menghasilkan
  receipt, TTL receipt asli lewat dan ditolak, serta Ctrl-C setelah lockdown lalu
  resume melalui SSH admin dengan run ID/sesi baru. Tiga gate, Docker privat,
  integritas data dan reboot kembali lulus pada payload hardening terbaru.
- Laporan asli dipertahankan di docs/evidence/; SECURITY-REVIEW dan RECOVERY
  disertakan di kandidat + checksum. Tes lokal: 81 regresi, 4 template/Compose,
  3 playbook syntax. Gate port asing tidak dilonggarkan untuk mengejar kelulusan.
- Disetujui untuk merge kandidat eksperimental setelah CI head akhir hijau;
  production_ready tetap false. Tidak ada reinstall, rilis produksi, perubahan
  tailnet, atau mutasi layanan/VPS aktif.

## 2026-11-15 — Gate kegagalan dan review sebelum merge

- Run 43662194601 membuktikan penolakan ACL; sudo menolak password salah tetapi
  status sesi SSH nol membingungkan harness. Gunakan marker exit command dari
  shell dan pemeriksaan receipt, bukan menyamakan status sesi dengan autentikasi.
- Run 43661212671 menolak UDP wildcard port acak sebelum apply. Tambah metadata
  pemilik socket sebelum install/saat gagal; tidak mengendurkan gate port asing.
- Review menemukan digest paket tidak lengkap belum selalu ditolak; wajibkan
  semua entry point/playbook/template runtime sebelum host preflight. Tambah tes
  file hilang nyata serta batas owner/perms/symlink state. Perbarui pesan eksperimen.
- Perluas acceptance: deny ACL SSH admin → allow fixture, password sudo salah,
  receipt asli expired tanpa mengubah TTL/clock, Ctrl-C setelah lockdown dan
  resume melalui SSH admin. Hasil baru belum diklaim sebelum workflow selesai.
- Tambah SECURITY-REVIEW dan RECOVERY; sertakan di kandidat deterministik + SHA256
  dan artifact CI source-only. Tidak menerbitkan rilis produksi atau mengubah VPS.
- Merge hanya setelah gate head/payload terbaru lulus sesuai otorisasi pemilik.

## 2026-11-15 — Acceptance dua VM lulus termasuk reboot

- Run 43651778256 pada commit d4f2c73 meluluskan baseline reboot, instalasi payload
  asli, tiga SSH/sudo gate, MagicDNS, transport IPv4/IPv6, HTTP Docker privat,
  probe interface luar, integritas rerun, dan reboot pasca-install dengan boot ID
  berubah serta SSH/Docker/firewall/data pulih. Laporan asli di docs/evidence/.
- Tools QEMU 8.2.2/SeaBIOS 1.16.3; guest tetap Ubuntu 22.04 amd64. Bukti dan batas
  di docs/VERIFICATION.md. Bukan bukti akun SaaS/routing/console Contabo; seluruh
  matriks failure-injection belum lulus. Tetap eksperimental, PR belum di-merge,
  tidak ada rilis produksi atau perubahan VPS aktif.

## 2026-11-15 — Perbarui emulator fixture, guest tetap Jammy

- Run 43649254705 gagal reboot Ubuntu polos sebelum installer dieksekusi. QMP
  masih running, VGA `Guest has not initialized the display (yet)` setelah reset.
- Ada laporan upstream Q35/TCG SeaBIOS reset loop (#766), cocok dengan gejala
  tetapi belum membuktikan sebab pasti pada fixture ini. Ganti base tools ke
  Ubuntu 24.04 digest terkunci, tetap guest Ubuntu 22.04 dan gate reboot baseline.
- Rekam versi paket QEMU/SeaBIOS di laporan. Tidak mengubah installer, kernel
  guest, konfigurasi reboot OS, atau memakai reset paksa sebagai bukti sukses.

## 2026-11-15 — Isolasi masalah reboot emulator/OS awal

- Run 43643713232 meluluskan hostname SSH, IPv4/IPv6 transport, tiga gate, Docker
  privat, dan integritas rerun, tetapi reboot tetap offline setelah 900 detik.
- Tambah reboot baseline Ubuntu polos sebelum installer dan observasi QMP/VGA
  melalui socket Unix fixture. Tidak tambah timeout lagi atau reset paksa guest;
  kegagalan baseline harus menghentikan uji sebelum menyalahkan installer.

## 2026-11-15 — Docker/rerun terbukti, koreksi asumsi DNS IPv6

- Run 43638905586 meluluskan tiga gate, HTTP Docker privat/tidak bocor pada
  interface luar, serta hash/inode/UID/GID data fixture tetap setelah rerun.
- Source Tailscale v1.104.7 mengonfirmasi AAAA MagicDNS sengaja disaring pada node
  dengan IPv4 (issue 1152). Pisahkan tes hostname wajib dari transport IPv6 yang
  memakai alamat node yang dilaporkan; bukan fallback login atau override DNS.
- Reboot belum lulus: console mencapai `Restarting system` setelah shutdown
  lambat; anggaran observasi TCG naik 300→900 detik, workflow 60→90 menit.

## 2026-11-15 — Tiga checkpoint nyata lulus, diagnosis IPv6 lanjutan

- Run 43634852921 menerima tiga receipt SSH/sudo terpisah, termasuk akses Docker
  admin; probe SSH non-tailnet IPv4/IPv6 diblokir. Payload digest cocok.
- Tes tambahan `ssh -6 vpslab` gagal resolusi alamat. Rekam query AAAA/rute IPv6;
  lanjutkan bukti Docker/rerun/reboot yang independen, tetapi hasil akhir tetap
  gagal jika tes keluarga alamat gagal (bukan skip atau fallback).
- Boot ID dibaca dari output JSON dan divalidasi UUID, bukan baris terakhir
  transkrip login shell yang dapat berupa pesan logout. Tambah regresi parser.

## 2026-11-15 — Pisahkan output UFW dari protokol JSON

- Run 43632146448 membuktikan SSH login shell, password sudo, dan receipt pertama
  diterima installer. Firewall aktif, tetapi Ansible gagal membaca JSON karena
  progress UFW ikut stdout. Checkpoint kedua/foundation/reboot belum terbukti.
- Kirim progress UFW ke stderr; stdout helper tetap JSON tunggal. Tambah regresi
  stream output dan simpan checkpoint VM bertahap agar hasil parsial tidak hilang.

## 2026-11-15 — Diagnostik terminal SSH/sudo

- Run 43629470570 menunjukkan PTY ada tetapi sudo tidak mendapat controlling
  terminal pada remote-command SSH. Harness sekarang membuka login shell dahulu,
  lalu mengetik command, sesuai alur manusia yang didokumentasikan. Password sudo
  tetap wajib, tanpa `-S`, NOPASSWD, atau perubahan verifier produksi.
- Run 43627357056 membuktikan MagicDNS nama pendek sudah berhasil; interaksi
  SSH/sudo berakhir sebelum prompt terbaca. Belum ada receipt checkpoint positif.
- Simpan transkrip output peer tersanitasi (tanpa input password), laporkan EOF
  lengkap, dan tampilkan `tty` sebelum sudo. Tidak mengubah policy autentikasi.

## 2026-11-15 — Diagnostik MagicDNS acceptance

- Run 43625046658 menemukan `setLinkDomains: Too many search domains per link`.
  Headscale v0.29.7 menghasilkan 256 reverse-DNS routes untuk `/24`; gunakan `/28`
  pada fixture (16 routes). Tidak mengubah DNS host aktif atau installer produksi.
- Run 43622487097 melewati preflight resume, tetapi client gagal resolve vpslab
  sebelum koneksi SSH checkpoint. Belum ada bukti checkpoint positif/lockdown.
- Tambah status mesh tersaring dan diagnostik resolver fixture; tunggu propagasi
  DNS maksimal 90 detik. Tidak fallback ke IP, hosts file, atau receipt palsu.

## 2026-11-15 — Resume setelah Tailscale aktif

- Tangani format `ss` IPv6 `[alamat]%interface:port`; regresi memakai format
  listener dari run 43620070683, bukan hanya alamat IPv6 tanpa scope.
- Preflight resume mengenali hanya endpoint TCP PeerAPI node lokal yang dilaporkan
  daemon Tailscale Running, setelah identitas/manifest resume tervalidasi.
  Listener wildcard, node lain, dan port layanan asing tetap ditolak.
- Tambah regresi dan diagnostik alamat/protokol listener pada kegagalan VM.
- Run 43617417505 membuktikan missing-receipt menghentikan installer tanpa
  memutus akses awal; resume ditolak pemeriksaan listener. Belum lulus end-to-end.

## 2026-11-14 — Koreksi penyiapan dan pembaca checkpoint VM

- Simpan stderr Docker tersanitasi; gunakan subnet eksplisit yang tidak tumpang
  tindih dan tangani IPAM null pada jaringan bawaan Docker.
- Kenali checkpoint yang terpisah kode cursor/wrapping tmux; tambah regresi dari
  rekaman kegagalan nyata. Tidak mengubah atau melewati verifier produksi.
- Run 43613122739 membuktikan boot dua VM TCG, enrollment fixture, dan tahap
  prepare installer; belum membuktikan lockdown, foundation, atau reboot.

## 2026-11-14 — Harness fresh VM tanpa kredensial produksi

- Tambahkan workflow disposable dua VM Ubuntu 22.04 dan Headscale HTTPS privat,
  dengan image/checksum terkunci dan kredensial fixture baru.
- Jalur uji mencakup missing-receipt failure, resume, tiga SSH/sudo nyata, probe
  IPv4/IPv6 non-tailnet, container privat, integritas data, dan reboot kernel.
- Tidak memakai tailnet pemilik, provider API, VM berbayar, atau menjalankan
  installer pada VPS aktif. Hasil belum boleh dianggap lulus sebelum run selesai.
- Batas: tidak membuktikan browser login SaaS, policy akun pemilik, routing publik
  Contabo, atau recovery console. Detail: docs/VM-ACCEPTANCE.md.

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
