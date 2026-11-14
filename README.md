# VPS Lab Bootstrap

Resep membangun ulang VPS lab pribadi. Target desain: dari `ssh root@IP-VPS`
menjadi akses harian `ssh vpsadmin@vpslab`, lewat Tailscale.

> **BELUM SIAP UNTUK INSTALASI.** Installer Ansible belum diimplementasikan.
> Installer Bash lama diblokir karena temuan keselamatan. Jangan memakai versi
> historis untuk melewati blokir ini. Belum ada rilis baru yang lolos tes VM.

## Yang sudah tersedia

- [Audit kode lama dan batas pemeriksaan](docs/AUDIT.md).
- [Desain awal Ubuntu Server 22.04 LTS](docs/DESIGN.md).
- [Rencana verifikasi dan syarat rilis](docs/VERIFICATION.md).
- Template aturan host/workspace di `templates/`; **belum dipasang ke host**.
- Source lama di `legacy/bootstrap.sh`, untuk referensi saja dan tidak bisa dijalankan.

## Yang aman dijalankan sekarang

Dari checkout repo, tanpa root:

```bash
bash bootstrap.sh --dry-run
python3 -B -m unittest discover -s tests -v
```

`--dry-run` hanya mencetak **rencana desain**, bukan simulasi Ansible. Tidak
membaca `config.env`, menulis log/config, atau menjalankan perubahan host.
Perintah instalasi final akan dipublikasikan bersama rilis teruji, dengan versi
tetap dan checksum. Jangan mengandalkan URL `main` untuk rebuild yang konsisten.

## Cara pakai yang dituju (belum tersedia)

1. Fresh install Ubuntu Server **22.04 LTS** dari provider.
2. Login `ssh root@IP-VPS`, download installer rilis teruji, lalu jalankan file itu.
3. Konfirmasi pengaturan, buat password sudo, login Tailscale lewat browser.
4. Dari terminal kedua, tes `ssh vpsadmin@vpslab` dan jalankan checkpoint.
5. Baru tutup jalur publik; tes ulang, termasuk kemampuan sudo.

Laptop harus terhubung ke Tailscale, MagicDNS berfungsi, dan kebijakan tailnet
mengizinkan koneksi serta Tailscale SSH. Nama `vpslab` tidak boleh bertabrakan
dengan perangkat lama; installer tidak menghapus perangkat atau mengubah kebijakan
tailnet otomatis. Console Contabo harus tersedia sebelum mulai.

Ubuntu 22.04 mendapat pemeliharaan keamanan standar sampai **Mei 2027**;
setelah itu perlu ESM melalui Ubuntu Pro atau upgrade OS.

## Batas lingkup

Bootstrap hanya menyiapkan fondasi host dan workspace. Aplikasi, OpenCode/plugin,
portal, serta pemulihan data dipasang lewat tahap terpisah. Bootstrap bukan backup;
fresh clone repo ini tidak memulihkan data layanan.
