# Aturan VPS lab pribadi

> Template untuk home admin. Belum menyatakan kondisi mesin sudah terverifikasi.
> Installer baru belum menginstal template ini. Aturan repo bukan aturan host.

## Prinsip kerja

- Pemilik non-engineer, paham IT. Gunakan Bahasa Indonesia santai dan jelaskan
  akibat/risiko, bukan sekadar perintah.
- Rapi, sederhana, perubahan kecil, bisa dibalik. Mesin bisa dibangun ulang dari
  resep dan backup, bukan kumpulan tindakan manual yang tak tercatat.
- Untuk migrasi akses: pasang jalur baru → tes dari client → baru putus jalur lama.
- Read-only dulu. Penemuan resource **bukan izin** untuk membaca data/mengubahnya.
- Kalau kepemilikan atau cakupan tugas meragukan, tanya; jangan hapus atau reset.

## Batas keamanan

1. Akses administrasi dan layanan hanya melalui Tailscale. Jalur awal publik
   hanya untuk bootstrap fresh, lalu ditutup setelah checkpoint akses berhasil.
2. Jangan publish port ke `0.0.0.0`, `::`, atau IP publik. Compose wajib menyebut
   IP Tailscale host secara eksplisit. Binding kosong/fallback tidak boleh.
   Contoh bentuk aman: `${TAILSCALE_IP:?wajib diisi}:${PORT:?wajib diisi}:80`.
   Periksa juga IPv6, host networking, dan mode privileged; jangan diasumsikan aman.
3. Docker published ports bisa melewati UFW. Firewall aktif bukan bukti layanan
   tidak terbuka ke publik. Periksa binding dan lakukan tes dari luar tailnet.
4. `tailscale funnel` dilarang. `tailscale serve` privat tetapi tetap perubahan
   routing/eksposur; perlu persetujuan, bukan izin otomatis.
5. Jangan ubah user, password, sudo, SSH, UFW, kebijakan tailnet, atau restart
   service akses tanpa konfirmasi. Jangan otomatis membuka publik saat gagal.
6. Grup `docker` setara root. Container bukan sandbox sempurna. Jangan mount
   docker.sock, root filesystem, atau data layanan lain tanpa persetujuan eksplisit.
7. Aplikasi lab melalui Docker, satu layanan satu folder di `~/playground`.
   Fondasi host (SSH, firewall, Tailscale, Docker, updater, tooling bootstrap)
   adalah pengecualian yang dikelola resep, bukan izin memasang app ke OS.

## Data dan rahasia

- Jangan membaca `.env`, token, private key, database runtime, unggahan, dokumen,
  backup, atau file user kecuali tugas mengizinkan **data dan tujuan tersebut**.
- README/AGENTS/registry boleh untuk discovery; tidak memberi akses ke data.
- Integrasi antar layanan lewat API/MCP terdokumentasi dengan kredensial sah.
  Tidak boleh mencari token di filesystem sebagai jalan pintas.
- Rahasia layanan di `.env` mode 600 atau mekanisme secret yang disetujui;
  jangan commit atau cetak nilainya. Tidak ada rahasia di registry atau rules.
- Jangan hapus data/volume, menjalankan prune, atau mereset Git tanpa izin
  spesifik. Backup harus berada di luar VPS dan pernah diuji restore.

## Satu sumber kebenaran

- `AGENTS.md`: instruksi kerja, bukan inventaris atau laporan status aktual.
- `README.md`: cara pakai dan batasan; jangan menyalin inventaris layanan.
- `CHANGELOG.md` home: perubahan host, dampak, dan cara balik.
- `CHANGELOG.md` layanan: riwayat proyek; `TODO.md`: pekerjaan tertunda.
- `~/playground/portal/labs.json`: registry layanan jika portal/registry sudah
  diinisialisasi. Jangan membuat registry paralel. Jika belum ada, laporkan;
  bootstrap sendiri tidak berarti portal sudah terpasang.
- IP host dan port bukan fakta permanen: cek runtime/registry, terutama setelah
  reinstall. Jangan menyalin IP dari mesin lama atau mengarang fallback.

## Layanan dan verifikasi

- Sebelum membuat layanan, cek registry dan README yang relevan. Satu layanan =
  folder, Compose, README, `.env` mode 600, dan data persisten bila diperlukan.
- Registry wajib valid sebelum dipasang. Siapkan rollback, validasi kandidat
  tanpa secret, lalu replace atomik di filesystem yang sama. Entri menunjuk
  layanan aktif, bukan rencana. Jangan menambah atau mengubah layanan lain diam-diam.
- Tentukan cara membuktikan perubahan sebelum mengerjakannya. Sesudah perubahan,
  periksa hanya container/listener/endpoint yang relevan dan laporkan hasil.
  Gunakan diagnostik host jika tersedia, tanpa mengasumsikan script sudah terpasang.
- Jangan menyebut sehat hanya karena container berjalan, atau aman hanya karena
  sintaks valid. Jelaskan mana yang diuji dan mana yang belum.
- Catat perubahan host di changelog home; jangan taruh riwayat kode di sana.
- Pembaruan tanpa auto-reboot **tidak** menjamin service tidak restart.
- Gangguan akses: gunakan console/VNC provider. Jangan minta agent mengakali
  izin atau memakai akses Docker sebagai jalur root alternatif tanpa persetujuan.

## Harness dan kepemilikan file

- File home ini adalah sumber aturan host kanonik; aturan workspace/layanan hanya
  menambahkan batas spesifik. Jika konflik, berhenti dan minta keputusan pemilik.
- Tidak semua harness memuat AGENTS.md otomatis. Verifikasi perilaku harness;
  jangan menjanjikan pemuatan otomatis secara universal.
- Integrasi harness opsional boleh menunjuk file kanonik via symlink, tetapi
  jangan menimpa file/symlink existing. Jangan membuat salinan rules kedua untuk root.
- Jangan menjalankan `chown -R` pada home/workspace atau memperbaiki izin secara
  massal. Tentukan path dan UID layanan yang benar sebelum mengubah kepemilikan.
