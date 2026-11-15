# Checkpoint akses: implementasi dan batas kepercayaan

## Perintah client

Di terminal **baru** pada client Tailscale, login sebagai admin, kemudian:

```bash
sudo -k -- /usr/local/sbin/lab-verify-access --connection "$SSH_CONNECTION"
```

`sudo -k` mengabaikan cache credential untuk perintah ini; autentikasi mengikuti
policy sudo host. Installer tidak menambahkan aturan NOPASSWD dan tidak menerima
password melalui JSON, argumen CLI, environment, receipt, atau log.

Wrapper root-owned hanya menjalankan satu file Python tetap menggunakan `-I`.
Tidak menerima path, nama command, username target, atau lokasi receipt dari user.
Tidak ada sudoers exception untuk wrapper; admin memakai hak sudo normalnya.

## Pemeriksaan

- Effective UID root, terminal interaktif, `SUDO_USER` dan `SUDO_UID` cocok admin.
- State/challenge regular file, root-owned, mode 600, direktori mode 700 bukan symlink.
- Challenge berumur maksimal 15 menit, terikat run, digest source, instance,
  boot, admin, purpose, dan nonce acak. Resume membuat run ID baru; receipt lama
  tidak cocok. Receipt dibuat atomik create-if-absent, tidak ditimpa.
- Tuple koneksi adalah IP tailnet → IP tailnet host ini, port 22, bukan self-SSH.
- `tailscale whois --json <source>` harus memetakan IP source ke node dan identitas
  login nyata. Policy Tailscale SSH tetap pengambil keputusan otorisasi; whois
  sendiri bukan otorisasi. Client bertag tanpa UserProfile login ditolak oleh versi ini.
- Pada checkpoint akhir, root verifier menjalankan **hanya** `docker info` melalui
  `runuser` sebagai admin ke socket lokal yang eksplisit, tanpa konteks/credential
  Docker warisan, membaca data aplikasi, atau membuat container. Config CLI memakai
  direktori kosong sementara milik root di /run, dibersihkan setelah pemeriksaan.
- Gate sebelum lockdown diperiksa ulang oleh playbook dan helper firewall.
  Receipt yang sama boleh dibaca keduanya selama operasi/purpose yang sama;
  tidak boleh dipakai untuk purpose berikutnya atau run baru.

Ada tiga checkpoint: sebelum lockdown, sesudah lockdown (sebelum fondasi), dan
sesudah fondasi/upgrade. Pemilik membuka sesi SSH baru untuk masing-masing.
Tuple sesi yang sudah dipakai ditolak pada checkpoint berikutnya; sesi yang tetap
hidup tidak dianggap membuktikan koneksi baru. Keberhasilan setelah upgrade tidak
menggantikan tes setelah reboot.

## Threat model — jangan overclaim

Tailscale SSH mengisi `SSH_CONNECTION`, tetapi di sini tuple diteruskan sebagai
**input client** agar tidak bergantung pada sudo mempertahankan environment SSH.
Input tersebut bisa dipalsukan oleh admin yang memang sudah punya sudo penuh.
Receipt mencegah salah terminal/salah user/konfirmasi asal dalam alur normal,
**bukan** bukti kriptografis terhadap admin/root yang sengaja melewati prosedur.
Tidak ada klaim anti-malicious-root atau pembuktian socket dari `/proc`.

Tailscale SSH mengambil koneksi tailnet port 22; ia terpisah dari kebijakan
OpenSSH. `PermitRootLogin no` mengeraskan OpenSSH, tidak otomatis mengubah izin
root pada policy Tailscale SSH. Installer tidak mengubah policy tailnet diam-diam.
Mengaktifkan Tailscale SSH dapat mengganggu sesi tailnet existing; karena itu
installer berjalan di tmux dan meminta koneksi baru sebelum lockdown.

Review kode dan unit tests sudah mencakup validasi input/gate. **Uji autentikasi
PAM/sudo, Tailscale SSH nyata, dan semua efek firewall/reboot masih wajib pada VM
disposable dan perangkat client terpisah sebelum rilis.**

## Referensi primer

- https://tailscale.com/docs/features/tailscale-ssh
- https://tailscale.com/docs/reference/tailscale-cli
- https://github.com/tailscale/tailscale/blob/main/ssh/tailssh/incubator.go
- https://www.man7.org/linux/man-pages/man5/sudoers.5.html
