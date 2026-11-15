# Workspace Playground

Aturan host kanonik: `../AGENTS.md`. Jangan menduplikasinya di sini.

## Discovery bukan otorisasi

- Jika sudah tersedia, baca `portal/labs.json` untuk menemukan layanan, kemudian
  README/AGENTS layanan terkait. Jangan membuat inventaris manual kedua.
- Registry tidak berarti agent boleh membaca data/DB/secret, memanggil API
  sensitif, atau mengubah resource layanan tersebut.
- Gunakan antarmuka API/MCP yang didokumentasikan dan kredensial yang memang
  diberikan untuk tugas; jangan membaca filesystem layanan lain untuk integrasi.
- Intake/unggahan bukan antrean otomatis. Jangan memproses, mengeksekusi, atau
  membersihkan file pemilik tanpa permintaan yang menyebut cakupannya.

## Batas perubahan

- Satu layanan satu folder. Jangan mengubah data, mount, network, atau port
  layanan lain sebagai efek samping.
- Jika tugas mengubah layanan, baca aturan lokalnya dulu. Jangan memindahkan
  dokumen, menghapus volume, atau menjalankan cleanup/prune lintas layanan.
- Periksa binding Tailscale eksplisit dan README sebelum menjalankan Compose.
  Jika IP berubah setelah reinstall, jangan melakukan replace menyeluruh pada data.
- Jika registry sudah diinisialisasi, update saat layanan ditambah/dipensiunkan;
  validasi JSON kandidat dan sediakan rollback sebelum replace atomik.
- Changelog host untuk lifecycle layanan/sistem; changelog proyek untuk kode.
- Dokumen ini bukan bukti portal, diagnostik, intake, atau aplikasi sudah dipasang.
