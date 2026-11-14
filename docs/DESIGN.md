# Desain v2 — Ubuntu Server 22.04 LTS

Status: **implementasi eksperimental tersedia, belum lolos tes VM/client/reboot**.
Default desain satu tempat (diselaraskan dengan `CONFIG_DEFAULTS` di kode):

| Pengaturan | Default |
|---|---|
| OS | Ubuntu Server 22.04 LTS amd64; arm64 ditolak, belum didukung |
| User | vpsadmin |
| Hostname | vpslab |
| Timezone | Asia/Jakarta |
| Swap | 4 GiB hanya jika belum ada swap dan kapasitas cukup |
| Workspace | /home/vpsadmin/playground |
| Login harian | ssh vpsadmin@vpslab |

Pemeliharaan keamanan standar 22.04 berakhir Mei 2027. Rencana ESM/upgrade harus
dibahas sebelum periode itu; installer tidak mengaktifkan layanan berbayar.

## Pengalaman pemilik

Login root ke IP publik mesin fresh, download file installer dari rilis tetap
dan verifikasi checksum, lalu jalankan. Bukan `curl | bash`; tidak perlu Ansible
di laptop. Prompt pakai bahasa Indonesia, input password tersembunyi, Tailscale
login via browser. Pertahankan terminal root sampai selesai.

Installer kecil menyiapkan Ansible pada virtualenv terpisah di path host yang
dimiliki installer, lalu menjalankan playbook dengan koneksi lokal dan interpreter
yang benar. Tooling provisioning adalah fondasi host, bukan aplikasi lab. Dependency
controller dikunci versi dengan checksum; versi awal memakai Ansible builtin saja,
tanpa collection Galaxy tambahan. Python controller terpisah karena Python 3.10
bawaan Jammy terlalu lama untuk Ansible yang masih didukung. Tidak perlu daemon,
panel, scheduler, atau controller laptop.

Konfigurasi baru berupa data dengan schema dan allowlist, tidak di-source atau
di-eval. Path absolut divalidasi; tidak menerima arbitrary executable lookup/Jinja
dari konfigurasi yang tidak dipercaya. Jangan memakai HOME/HOSTNAME bawaan shell
sebagai default identitas. Tidak otomatis membaca config dari current directory.

## Fase dan batas kegagalan

1. **Preflight tanpa mutasi:** root, versi OS, ruang disk, apt/cloud-init selesai,
   akses console, internet, layanan/data existing. Sediakan mode read-only sebelum
   dependency provisioning diinstal. Target fresh harus ditolak jika ada workload
   existing yang bukan milik installer. Resume hanya instalasi yang dapat dibuktikan
   milik installer ini; marker saja bukan alasan menyentuh data existing.
2. **Identitas:** buat admin + password sudo, hostname, persistensi hostname melalui
   drop-in cloud-init. Jangan menonaktifkan cloud-init atau menghapus provider agents.
3. **Tailscale:** install dari repo resmi Jammy, enable service dan SSH, login browser,
   temukan IP/name sebenarnya. Validasi MagicDNS, status, dan nama yang sesuai.
   Policy tailnet diperiksa/dijelaskan, bukan diubah otomatis. Konflik nama lama
   memerlukan keputusan pemilik, bukan otomatis menghapus/rename perangkat lain.
4. **Checkpoint eksternal:** tampilkan perintah untuk terminal client kedua.
   Pemeriksaan di sesi admin baru mengikat challenge sekali-pakai ke versi setup,
   user, sesi SSH, sumber/destinasi Tailscale, serta instance. Receipt disimpan
   root-owned dan terbatas waktu; user biasa tidak boleh menulis receipt langsung.
   Detail validator dan batas kepercayaan ada di `CHECKPOINT.md`; tidak ada
   generic sudo wrapper, arbitrary command/path, atau token di log. Bukti ini
   mencegah salah konfirmasi, bukan melindungi dari pemilik/root yang berniat bypass.
   Pemilik membuktikan sudo dari sesi itu juga. `--yes` tidak tersedia.
5. **Lockdown:** stage config SSH, backup path spesifik, validasi sintaks dan effective
   config sebelum apply/reload. Konvergensi firewall IPv4/IPv6 hanya setelah gate.
   Jangan mengklaim publik tertutup karena default deny saja. Cek socket activation
   Ubuntu, policy root/password, dan Tailscale rules sebelum perubahan. Kegagalan
   sebelum gate mempertahankan jalur awal. Sesudah lockdown, kegagalan tidak otomatis
   membuka publik. Rollback SSH terbatas pada file milik installer; console tetap
   jalur recovery jika tidak mungkin memulihkan lewat Tailscale.
6. **Fondasi:** updater keamanan tanpa auto-reboot, timezone, swap existing tidak
   ditimpa, Docker upstream + Compose v2 dengan deteksi instalasi existing. Konfigurasi
   existing tidak ditimpa diam-diam. Reload/restart hanya bila perlu dan disetujui;
   upgrade paket bisa memicu restart. Proses resumable pada koneksi yang putus,
   memakai tmux atau mekanisme bounded yang terdokumentasi, bukan daemon permanen.
7. **Workspace:** hanya file/path manifest milik installer. Rules home kanonik dan
   aturan workspace minimal memakai template repo. Tidak ada rules root duplikat
   atau integrasi OpenCode otomatis. File existing/symlink tidak ditimpa. Ownership
   hanya path baru yang dikenal, bukan recursive home/workspace. Template Compose
   tanpa container_name tetap, IP Tailscale wajib dan tidak ada fallback publik.
8. **Penutupan:** receipt hasil, pemeriksaan sudo, SSH client ulang, listener dan
   container contoh sementara yang diizinkan, tes publik dari luar tailnet, reboot
   terencana lalu tes ulang. Hapus hanya resource tes milik run itu. Tampilkan status
   parsial jika tes eksternal belum dilakukan; jangan selalu mencetak "selesai".

## SSOT dan scope

- Rules tidak mencatat status faktual "SSH aktif"/"cloud-init mati". Status
  diverifikasi runtime, hasil run terpisah; tidak menjadi inventaris kedua.
- Portal/registry belum dipasang oleh bootstrap. Saat tahap portal diinisialisasi,
  tetap gunakan `~/playground/portal/labs.json`; jangan membuat daftar paralel.
- Aplikasi lab, OpenCode, plugin, restore BA, data, dan rahasia bukan payload
  bootstrap. README hanya menautkan proses terpisah setelah proses itu tersedia.
- Tidak ada auto-prune, auto-reboot, mount data layanan lain, atau eksposur publik.
- Release dipin dan dapat dibangun ulang. Update tooling provisioning berbeda
  dari menjalankan ulang bootstrap. Implementasi awal menggunakan tiga playbook
  builtin (`prepare`, `lockdown`, `foundation`) dan driver lokal, bukan collection
  besar. `scripts/build_candidate.py` membuat paket review, bukan rilis produksi.
