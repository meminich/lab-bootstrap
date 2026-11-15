# Review keamanan kandidat

Status: review kode dan tes lokal diselesaikan; acceptance failure-injection
terbaru harus lulus sebelum keputusan merge. Bukan audit pihak ketiga atau klaim
siap produksi. Bukti runtime dan digest ada di [VERIFICATION](VERIFICATION.md).

## Lingkup dan metode

Review entry point, config/schema, tooling/download, manifest/resume, checkpoint,
gate playbook, SSH/UFW, Docker readiness, template, packaging, dan batas fixture.
Arsip Bash hanya diperiksa guard-nya; body lama tidak dijadikan installer produksi.
Tidak membaca/mengubah rahasia, workload, SSH, firewall, atau rules VPS aktif.

| Batas | Hasil review / bukti yang dipakai |
|---|---|
| Input bukan kode | JSON ber-allowlist; argumen subprocess berupa list; template bukan input executable pengguna. Plan tidak membaca config.env atau menulis bytecode. |
| Paket lengkap sebelum mutasi | **Diperbaiki:** digest kini mewajibkan entry point, tiga playbook, config Ansible, dan seluruh template runtime. Regresi menghapus file nyata dari salinan fixture. |
| Supply chain | uv binary/wheel dan dependency Python dikunci hash; repos APT resmi signed-by + signing-key checksum. Paket OS/upstream tetap bergerak, bukan image bit-identik. |
| State dan resume | State/source root-owned privat; manifest path terbatas, drift dan symlink ditolak; run ID baru dan receipt terikat source/instance/boot. Rerun selesai tidak melakukan perbaikan diam-diam. |
| Checkpoint privilege | Sudo biasa, tanpa exception/NOPASSWD; verifier path tetap, TTY/admin identity/whois/TTL/purpose divalidasi; receipt atomik single-use. Gate di driver, playbook, dan helper firewall. |
| Lockdown | Jalur Tailscale ditambahkan sebelum public ALLOW dihapus; tanpa reset/disable firewall atau fail-open rollback. Konfigurasi SSH divalidasi sebelum reload, rollback hanya file kelolaan. |
| Workload dan Docker | Tidak ada rewrite/recursive chown workspace. Compose mewajibkan IP Tailscale. Docker startup menunggu IP nyata di interface; grup Docker memang root-equivalent dan disetujui secara eksplisit. |
| Fixture | Dua kernel guest, control plane privat dengan kunci baru; tanpa Docker socket/host networking/published host port. Policy test hanya transisi deny→allow admin fixture, bukan arbitrary command bridge. |
| Artifact | Hanya source/docs/lockfile/manifest/checksum. Tidak ada data runtime, .env, private key, atau kredensial produksi. Checksum bukan autentikasi publisher. |

## Batas yang tetap penting

- Receipt melindungi alur normal, bukan melawan admin yang sudah memiliki sudo
  penuh dan sengaja memalsukan input `SSH_CONNECTION`. Lihat [threat model](CHECKPOINT.md).
- Policy Tailscale SSH terpisah dari OpenSSH. `PermitRootLogin no` tidak mengubah
  ACL root tailnet; installer tidak mengedit policy akun pemilik.
- Fresh-host gate sengaja konservatif. Resume tidak mengadopsi resource asing;
  setelah selesai ia bukan mekanisme update/repair atau audit seluruh host.
- Tes interupsi proses dilakukan pada batas fase yang aman, bukan membunuh dpkg
  saat menulis. Network disconnect/download failure dan seluruh matriks variasi
  provider/OS tidak boleh diklaim lulus dari satu skenario acceptance.
- Browser SaaS, MFA/device approval/ACL pemilik, image/routing/console Contabo,
  dan arm64 tetap di luar bukti otomatis. Ubuntu 22.04 standard support berakhir
  Mei 2027; keputusan ESM/upgrade tetap milik pemilik.
- Merge kandidat yang masih diberi guard eksperimental bukan izin wipe VPS,
  penerbitan rilis produksi, atau pernyataan seluruh matriks rilis sudah lulus.

## Keputusan merge

Merge hanya setelah CI head yang direview hijau, acceptance negatif terbaru
berhasil pada digest payload yang sama, bukti tersimpan permanen, kandidat dapat
dibangun ulang dengan checksum, dan tidak ada temuan keamanan yang belum ditangani
di lingkup ini. Panduan [RECOVERY](RECOVERY.md) tidak menggantikan latihan console
provider nyata. Jika gate gagal, hentikan merge dan laporkan sebabnya.
