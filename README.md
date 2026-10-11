# VPS Lab Bootstrap

Ubah VPS **Ubuntu fresh** jadi **lab siap pakai** — sekali jalan, interaktif.
Hasilnya: akses cuma lewat Tailscale, port publik ditutup, Docker + struktur lab siap.

---

## Cara pakai (cukup copy-paste, terus ikuti di layar)

Di VPS baru, login sebagai **root**, lalu jalankan:

```bash
curl -fsSL https://raw.githubusercontent.com/meminich/lab-bootstrap/main/bootstrap.sh | sudo bash
```

> Atau download dulu: `curl -fsSL https://raw.githubusercontent.com/meminich/lab-bootstrap/main/bootstrap.sh -o bootstrap.sh`
> lalu `sudo bash bootstrap.sh`.

Terus **ikuti petunjuk di layar.** Biasanya cuma 2 aksi manual:

1. **Login Tailscale** — buka link yang muncul di browser, login, klik Connect.
2. **Tes akses** — di laptop jalankan `ssh vpsadmin@vpslab`. Bisa masuk? ketik `y`.

---

## Yang dihasilkan

- 🔒 Akses **hanya via Tailscale** (port publik ditutup, password SSH mati)
- 🧱 Fondasi OS rapi (auto-patch keamanan, timezone, swap, cloud-init mati)
- 🐳 **Docker** + struktur lab di `~/playground` (+ `_template`)
- 📄 `AGENTS.md` — aturan lab, kebaca otomatis sama agent & manusia

---

## Opsi

```bash
sudo bash bootstrap.sh --dry-run     # lihat rencana, tidak mengubah apa pun
sudo bash bootstrap.sh --only 50     # jalankan 1 fase saja
sudo bash bootstrap.sh --from 40     # mulai dari fase tertentu
sudo bash bootstrap.sh --yes         # non-interaktif (pakai default)
```

## Catatan

- **Data lab TIDAK ikut** di-restore — pulihkan dari **snapshot** kalau perlu.
- Mau ubah nama host/user/port default? Bikin `config.env` (lihat `config.env.example`) atau isi lewat wizard saat menjalankan.
- Detail lengkap aturan: lihat `AGENTS.md` di VPS setelah selesai.
