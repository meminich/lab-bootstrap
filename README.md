# VPS Lab Bootstrap

Resep membangun ulang VPS lab pribadi. Target desain: dari `ssh root@IP-VPS`
menjadi akses harian `ssh vpsadmin@vpslab`, lewat Tailscale.

> **BELUM SIAP UNTUK INSTALASI produksi.** Implementasi Ansible v2 tersedia sebagai
> kandidat **eksperimental**. [Acceptance dua VM terisolasi sudah lulus](docs/VERIFICATION.md),
> termasuk SSH/sudo nyata dan reboot; matriks rilis serta akun/provider pemilik belum teruji penuh.
> Script Bash lama tetap diblokir. Jangan bypass melalui versi historis.

## Install di VPS fresh — mulai di sini

Pilih **Ubuntu Server 22.04 LTS amd64** saat reinstall. Ini bukan installer untuk
VPS existing. Siapkan console/VNC provider dan laptop yang sudah terhubung Tailscale.
Bootstrap memasang fondasi host, Docker, dan workspace; **bukan** portal, OpenCode,
aplikasi, atau pemulihan data lama.

Login dari laptop:

```bash
ssh root@IP-VPS
```

Di terminal VPS tersebut, jalankan satu perintah:

```bash
curl -fSLo lab-setup.py https://raw.githubusercontent.com/meminich/lab-bootstrap/feat/guided-installer-launcher/setup.py && python3 -I -B lab-setup.py
```

URL launcher di atas masih **branch review**, belum rilis launcher bertag. Gunakan
hanya setelah meninjau branch tersebut. Launcher mengunduh payload **v0.1.0** yang
tetap dan memverifikasi SHA256 yang tertanam sebelum menjalankannya. Tidak perlu
mengunduh archive, mengekstrak, membuat config JSON, atau mengingat flag sendiri.
Download hanya dari repo yang dipercaya; checksum bukan tanda tangan publisher.

Selanjutnya ikuti terminal:

1. Isi nama admin, nama VPS, timezone, dan swap. **Enter** memakai default.
2. Installer memeriksa VPS fresh, lalu meminta konfirmasi sebelum mengubah sistem.
3. Buat password sudo ketika diminta dan buka URL login Tailscale yang muncul.
4. Buka **terminal kedua di laptop**, salin perintah SSH dan verifier yang ditampilkan.
   Ada tiga checkpoint; gunakan sesi SSH baru setiap kali diminta.
5. Kembali ke terminal installer sampai muncul hasil akhir dan alamat login harian.

**Jangan tutup terminal awal sebelum selesai.** Proses panjang berjalan dalam tmux.
Jika SSH terputus atau proses berhenti, lihat [cara menyambung/resume](#jika-koneksi-putus).
Jangan menjalankan download ulang untuk mengambil alih instalasi yang terhenti.

Paket tetap eksperimental. Login Tailscale akun pemilik, image/routing Contabo,
dan console recovery belum diuji penuh. Tiga checkpoint akses tetap wajib; installer
tidak otomatis reboot atau mengklaim tes eksternal yang belum dilakukan sudah lulus.

## Informasi teknis dan pengembangan

### Yang sudah tersedia

- [Audit kode lama dan batas pemeriksaan](docs/AUDIT.md).
- [Desain dan implementasi Ubuntu Server 22.04 LTS amd64](docs/DESIGN.md).
- [Rencana verifikasi dan syarat rilis](docs/VERIFICATION.md).
- Installer `install.sh`, driver Python, dan tiga playbook Ansible lokal.
- Template aturan host/workspace di `templates/`; **tidak dipasang ke VPS aktif
  saat pengembangan**. Installer hanya memasangnya ke target fresh yang disetujui.
- Source lama di `legacy/bootstrap.sh`, untuk referensi saja dan tidak bisa dijalankan.

### Pemeriksaan aman dari source

Dari checkout repo, tanpa root:

```bash
bash bootstrap.sh --dry-run
bash install.sh --dry-run
python3 -B -m unittest discover -s tests -v
```

`--dry-run` hanya mencetak **rencana**, bukan simulasi Ansible. Tidak
membaca `config.env`, menulis log/config, atau menjalankan perubahan host.
Launcher di atas mengambil payload rilis tetap dan memeriksa checksum. Untuk
rebuild konsisten, catat pula versi/commit launcher yang ditinjau; branch dapat berubah.

### Penggunaan manual / pengujian kandidat (bukan pada VPS aktif)

Gunakan **seluruh checkout/paket kandidat** pada VPS/VM Ubuntu 22.04 amd64 fresh
yang memang boleh diubah. Jangan hanya mengunduh install.sh: file itu membutuhkan
driver, playbook, template, serta lockfile di paket yang sama.

```bash
# Read-only. Root diperlukan untuk cek metadata host, bukan untuk menulis.
bash install.sh --preflight
# HANYA target fresh disposable yang diizinkan, bukan VPS lab aktif:
bash install.sh --apply --experimental
```

Config opsional berupa JSON eksplisit (`--config /root/lab-config.json`), dengan
field `admin_user`, `hostname`, `timezone`, `swap_gib`. Tanpa config, default dari
desain digunakan. Password tidak dimasukkan ke JSON. Tidak ada `--yes`,
`--skip-verify`, auto-prune, atau auto-reboot.

## Jika koneksi putus

Jika koneksi putus sebelum Tailscale siap, login root seperti awal lalu
`tmux attach -t lab-bootstrap`. Sesudah Tailscale siap, login
`ssh vpsadmin@vpslab` lalu `sudo tmux attach -t lab-bootstrap`.

Jika proses benar-benar berhenti (bukan hanya koneksi SSH), lanjutkan payload
versi sama yang sudah dipasang, dari sesi admin:

```bash
sudo /usr/bin/python3 -I -B /opt/lab-bootstrap/source/labbootstrap/installer.py --apply --experimental --resume
```

Resume menolak config/source yang berbeda, drift file kelolaan, dan container
existing selama setup belum selesai. Setelah selesai, resume tidak mengubah apa pun;
ini bukan mekanisme update host atau alat memperbaiki instalasi orang lain.

Langkah aman saat koneksi/proses gagal: [RECOVERY](docs/RECOVERY.md).
Hasil review dan batas trust: [SECURITY-REVIEW](docs/SECURITY-REVIEW.md).
CI menyediakan artifact **kandidat + SHA256**, bukan rilis produksi; nama artifact
memuat commit source. Tetap unduh seluruh paket dan verifikasi checksum.

## Alur installer

1. Fresh install Ubuntu Server **22.04 LTS** dari provider.
2. Login `ssh root@IP-VPS`, download installer rilis teruji, lalu jalankan file itu.
3. Konfirmasi pengaturan, buat password sudo, login Tailscale lewat browser.
4. Dari terminal kedua, tes `ssh vpsadmin@vpslab` dan jalankan perintah verifier
   yang ditampilkan. `sudo -k` meminta autentikasi sesuai policy sudo, bukan
   mengirim password ke installer.
5. Baru tutup jalur publik; buka sesi SSH baru dan verifikasi ulang.
6. Pasang fondasi/Docker/workspace, kemudian checkpoint akhir (termasuk Docker
   sebagai admin). Tampilkan tes publik/reboot yang **masih tertunda**, bukan
   mengklaim semua tes rilis sukses.

Laptop harus terhubung ke Tailscale, MagicDNS berfungsi, dan kebijakan tailnet
mengizinkan koneksi serta Tailscale SSH. Nama `vpslab` tidak boleh bertabrakan
dengan perangkat lama; installer tidak menghapus perangkat atau mengubah kebijakan
tailnet otomatis. Console Contabo harus tersedia sebelum mulai.

Jika client memperingatkan host key berubah sesudah reinstall, jangan mematikan
host-key checking secara global. Cocokkan identitas mesin baru melalui console/
Tailscale terlebih dahulu; setelah benar, perbarui hanya entri host terkait pada
client. Installer di server tidak mengubah known_hosts laptop diam-diam.

Ubuntu 22.04 mendapat pemeliharaan keamanan standar sampai **Mei 2027**;
setelah itu perlu ESM melalui Ubuntu Pro atau upgrade OS.

## Batas lingkup dan pengujian

Bootstrap hanya menyiapkan fondasi host dan workspace. Aplikasi, OpenCode/plugin,
portal, serta pemulihan data dipasang lewat tahap terpisah. Bootstrap bukan backup;
fresh clone repo ini tidak memulihkan data layanan.

Runtime controller menggunakan Python terpisah (bukan mengganti Python Ubuntu),
uv dan dependency Ansible dipin dengan hash. Paket OS/Docker/Tailscale mengikuti
repository bertanda tangan agar mendapat patch; versi terpasang dapat berubah
antarwaktu. Ini resep rebuild, **bukan jaminan image OS bit-for-bit identik**.

Daftar bukti yang sudah/belum ada: [VERIFICATION](docs/VERIFICATION.md).

Tes VM tanpa kredensial produksi memakai [jaringan fixture terisolasi](docs/VM-ACCEPTANCE.md)
di runner GitHub sementara. Hasilnya tidak boleh disamakan dengan login browser
Tailscale milik pemilik atau pengujian routing/provider Contabo.
