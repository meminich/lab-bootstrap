#!/usr/bin/env bash
# =============================================================================
#  VPS LAB BOOTSTRAP
#  Ubuntu fresh  ->  lab siap pakai
#  (Tailscale + hardening + fondasi OS + Docker + struktur lab)
#
#  Cara pakai:
#    sudo bash bootstrap.sh                 # interaktif (disarankan)
#    sudo bash bootstrap.sh --dry-run       # lihat rencana saja, tidak mengubah
#    sudo bash bootstrap.sh --only 50       # jalankan 1 fase saja
#    sudo bash bootstrap.sh --from 40       # mulai dari fase tertentu
#    sudo bash bootstrap.sh --yes           # non-interaktif (pakai default)
#
#  Aman dijalankan ulang (idempotent).
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
#  NILAI DEFAULT — bisa diubah via config.env atau wizard.
#  (Kosong = pakai default ini.)
# ---------------------------------------------------------------------------
: "${HOSTNAME:=vpslab}"
: "${ADMIN_USER:=vpsadmin}"
: "${ADMIN_PASSWORD:=}"
: "${TIMEZONE:=Asia/Jakarta}"
: "${SWAP_SIZE:=4G}"
: "${TAILSCALE_AUTHKEY:=}"
: "${DEFAULT_PORT:=8080}"
: "${DEFAULT_IMAGE:=nginx:alpine}"
: "${DOCKER_LOG_MAX_SIZE:=10m}"
: "${INSTALL_TOOLS:=true}"
: "${PLAYGROUND_DIR:=}"

# ---------------------------------------------------------------------------
#  Argumen
# ---------------------------------------------------------------------------
DRY_RUN=false
ASSUME_YES=false
SKIP_VERIFY=false
FORCE=false
ONLY=""
FROM=""
CONFIG_FILE=""
TAILSCALE_IP=""
PUBLIC_IP=""
TAILNET=""
DNSNAME=""
SCRIPT_START=""

usage() {
  cat <<'EOF'
VPS LAB BOOTSTRAP — Ubuntu fresh -> lab siap pakai
(Tailscale + hardening + fondasi OS + Docker + struktur lab)

Cara pakai:
  sudo bash bootstrap.sh                 # interaktif (disarankan)
  sudo bash bootstrap.sh --dry-run       # lihat rencana saja, tidak mengubah
  sudo bash bootstrap.sh --only 50       # jalankan 1 fase saja
  sudo bash bootstrap.sh --from 40       # mulai dari fase tertentu
  sudo bash bootstrap.sh --yes           # non-interaktif (pakai default)

Opsi:
  --dry-run        Tampilkan rencana, tidak mengubah apa pun.
  --yes            Non-interaktif (pakai default / config.env).
  --skip-verify    Lewati konfirmasi verifikasi SSH (HATI-HATI).
  --force          Timpa file yang sudah ada (termasuk AGENTS.md).
  --only N         Jalankan hanya fase N (10,20,30,40,50).
  --from N         Jalankan mulai fase N sampai akhir.
  -h, --help       Bantuan ini.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)     DRY_RUN=true ;;
    --yes|-y)      ASSUME_YES=true ;;
    --skip-verify) SKIP_VERIFY=true ;;
    --force)       FORCE=true ;;
    --only)        ONLY="${2:-}"; shift ;;
    --from)        FROM="${2:-}"; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "Argumen tidak dikenal: $1"; usage; exit 1 ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
#  Warna & helper tampilan
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
  B=$'\033[1m'; DIM=$'\033[2m'; R=$'\033[0m'
  BL=$'\033[34m'; GR=$'\033[32m'; YE=$'\033[33m'; RD=$'\033[31m'
else
  B=""; DIM=""; R=""; BL=""; GR=""; YE=""; RD=""
fi

hdr()   { printf '\n%s── %s ──%s\n' "${B}${BL}" "$*" "$R"; }
note()  { printf '   %s\n' "$*"; }
sub()   { printf '   %s%s%s\n' "$DIM" "$*" "$R"; }
ok()    { printf '   %s✔%s %s\n' "$GR" "$R" "$*"; }
warn()  { printf '   %s⚠%s %s\n' "$YE" "$R" "$*"; }
err()   { printf '   %s✘%s %s\n' "$RD" "$R" "$*" >&2; }
die()   { err "$*"; exit 1; }
pause() { $ASSUME_YES && return 0; read -r -p "   Tekan Enter untuk lanjut..." _ || true; }
ask_yn() {
  # ask_yn "pertanyaan" [default y|n]
  local prompt="$1" def="${2:-n}" ans
  $ASSUME_YES && { [[ "$def" == y ]]; return; }
  read -r -p "   ${prompt} [$def] " ans || true
  ans="${ans:-$def}"
  [[ "${ans,,}" == y* ]]
}
need_root() { [[ "$(id -u)" -eq 0 ]] || die "Jalankan sebagai root: sudo bash $0"; }
have()      { command -v "$1" >/dev/null 2>&1; }

# Deteksi nilai jaringan dari Tailscale (kalau belum terisi)
discover_net() {
  have tailscale || return 0
  [[ -n "$TAILSCALE_IP" ]] || TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  [[ -n "$DNSNAME" ]]      || DNSNAME="$(tailscale status --json 2>/dev/null | jq -r '.Self.DNSName // empty' || true)"
  [[ -n "$TAILNET" ]]      || TAILNET="$(printf '%s' "$DNSNAME" | sed 's/^[^.]*\.//; s/\.$//')"
  [[ -n "$PUBLIC_IP" ]]    || PUBLIC_IP="$(curl -4 -s --max-time 8 https://api.ipify.org 2>/dev/null || echo '?')"
}

# Jalankan perintah (atau cuma tampilkan saat dry-run)
xrun() {
  if $DRY_RUN; then printf '   %s[dry-run]%s %s\n' "$DIM" "$R" "$*"; return 0; fi
  "$@"
}

# ---------------------------------------------------------------------------
#  Lokasi & log
# ---------------------------------------------------------------------------
SELF="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" >/dev/null 2>&1 && pwd || pwd)"
LOG_FILE="/var/log/vpslab-bootstrap.log"

# ---------------------------------------------------------------------------
#  Muat config.env (kalau ada) + wizard
# ---------------------------------------------------------------------------
for c in "${PWD}/config.env" "${SCRIPT_DIR}/config.env" "/root/.lab-bootstrap/config.env"; do
  if [[ -f "$c" ]]; then
    CONFIG_FILE="$c"
    # shellcheck disable=SC1090
    source "$c"
    break
  fi
done

# terapkan default lagi untuk nilai yang kosong setelah load config
: "${HOSTNAME:=vpslab}"
: "${ADMIN_USER:=vpsadmin}"
: "${TIMEZONE:=Asia/Jakarta}"
: "${SWAP_SIZE:=4G}"
: "${DEFAULT_PORT:=8080}"
: "${DEFAULT_IMAGE:=nginx:alpine}"
: "${DOCKER_LOG_MAX_SIZE:=10m}"
: "${INSTALL_TOOLS:=true}"
: "${PLAYGROUND_DIR:=/home/${ADMIN_USER}/playground}"

validate_config() {
  [[ "$ADMIN_USER" =~ ^[a-z][a-z0-9_]{0,31}$ ]] || die "ADMIN_USER '$ADMIN_USER' tidak valid (huruf kecil/angka/_ , tanpa strip/spasi)."
  [[ "$HOSTNAME" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] || die "HOSTNAME '$HOSTNAME' tidak valid (huruf kecil/angka/- , tanpa spasi)."
  [[ "$SWAP_SIZE" =~ ^[0-9]+[GM]$ ]] || die "SWAP_SIZE '$SWAP_SIZE' tidak valid (contoh: 4G, 2G)."
}

wizard() {
  $ASSUME_YES && return 0
  [[ -n "$CONFIG_FILE" ]] && { sub "Config ditemukan: $CONFIG_FILE"; return 0; }
  [[ -t 0 ]] || return 0

  hdr "KONFIGURASI"
  note "Tekan Enter untuk pakai default (di dalam tanda kurung)."
  local a
  read -r -p "   Nama host        [$HOSTNAME] : " a || true;       HOSTNAME="${a:-$HOSTNAME}"
  read -r -p "   User admin       [$ADMIN_USER] : " a || true;     ADMIN_USER="${a:-$ADMIN_USER}"
  read -r -p "   Timezone         [$TIMEZONE] : " a || true;       TIMEZONE="${a:-$TIMEZONE}"
  read -r -p "   Ukuran swap      [$SWAP_SIZE] : " a || true;     SWAP_SIZE="${a:-$SWAP_SIZE}"
  read -r -p "   Port default     [$DEFAULT_PORT] : " a || true; DEFAULT_PORT="${a:-$DEFAULT_PORT}"
  read -r -p "   Auth key (kosong=link) : " a || true;           TAILSCALE_AUTHKEY="${a:-$TAILSCALE_AUTHKEY}"
  PLAYGROUND_DIR="/home/${ADMIN_USER}/playground"
  validate_config

  local save="${PWD}/config.env"
  if ask_yn "Simpan ke $save biar lain kali tidak ditanya lagi?" y; then
    cat > "$save" <<EOF
# Config VPS Lab Bootstrap — JANGAN di-commit (berisi rahasia).
HOSTNAME=$HOSTNAME
ADMIN_USER=$ADMIN_USER
# ADMIN_PASSWORD=isi_jika_mau       # kosong = tanya saat setup
TIMEZONE=$TIMEZONE
SWAP_SIZE=$SWAP_SIZE
DEFAULT_PORT=$DEFAULT_PORT
DEFAULT_IMAGE=$DEFAULT_IMAGE
# TAILSCALE_AUTHKEY=tskey-auth-xxx   # kosong = login pakai link
INSTALL_TOOLS=$INSTALL_TOOLS
EOF
    chmod 600 "$save"
    ok "Disimpan: $save"
  fi
}

# ---------------------------------------------------------------------------
#  FASE
# ---------------------------------------------------------------------------
summary_vars() {
  sub "Host=$HOSTNAME  User=$ADMIN_USER  TZ=$TIMEZONE  Swap=$SWAP_SIZE  Playground=$PLAYGROUND_DIR"
}

# ---------------- Fase 10: Preflight ----------------
phase_10() {
  hdr "FASE 10 · Preflight"
  note "APA    : Cek prasyarat + pasang alat dasar."
  note "KENAPA : Pastikan mesin siap sebelum diubah."
  if $DRY_RUN; then sub "cek root, OS Ubuntu, internet, apt install curl/ca-certificates/gnupg/git/jq"; return 0; fi

  need_root
  local id=""
  [[ -r /etc/os-release ]] && id="$(. /etc/os-release; echo "$ID")"
  [[ "$id" == "ubuntu" ]] || warn "Bukan Ubuntu (terdeteksi: ${id:-?}). Script ini diuji di Ubuntu 24.04."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq curl ca-certificates gnupg git jq >/dev/null
  ok "Prasyarat & alat dasar siap."
}

# ---------------- Fase 20: Identity ----------------
phase_20() {
  hdr "FASE 20 · User admin & hostname"
  note "APA    : Bikin user admin (non-root) + set hostname."
  note "KENAPA : Login sehari-hari lewat user ini (lebih aman), dan hostname = nama Tailscale."
  if $DRY_RUN; then sub "adduser $ADMIN_USER + sudo; set password; hostname=$HOSTNAME; preserve_hostname"; return 0; fi
  need_root

  # user admin
  if id "$ADMIN_USER" >/dev/null 2>&1; then
    ok "User '$ADMIN_USER' sudah ada."
  else
    adduser --disabled-password --gecos "" "$ADMIN_USER" >/dev/null
    ok "User '$ADMIN_USER' dibuat."
  fi
  usermod -aG sudo "$ADMIN_USER"

  # password (buat sudo)
  local st; st="$(passwd -S "$ADMIN_USER" 2>/dev/null | awk '{print $2}')"
  if [[ "$st" != "P" ]]; then
    if [[ -n "$ADMIN_PASSWORD" ]]; then
      echo "$ADMIN_USER:$ADMIN_PASSWORD" | chpasswd; ok "Password di-set dari config."
    elif $ASSUME_YES; then
      warn "Password kosong (mode --yes). sudo belum bisa dipakai user ini."
    else
      note "Set password buat sudo user '$ADMIN_USER':"
      passwd "$ADMIN_USER" || warn "Gagal set password."
    fi
  else
    ok "Password '$ADMIN_USER' sudah ada."
  fi

  # hostname + /etc/hosts + preserve_hostname
  xrun hostnamectl set-hostname "$HOSTNAME"
  if grep -q '^127\.0\.1\.1' /etc/hosts; then
    sed -i "s/^127\.0\.1\.1.*/127.0.1.1 ${HOSTNAME}/" /etc/hosts
  else
    echo "127.0.1.1 ${HOSTNAME}" >> /etc/hosts
  fi
  if [[ -f /etc/cloud/cloud.cfg ]]; then
    if grep -q '^preserve_hostname: false' /etc/cloud/cloud.cfg; then
      sed -i 's/^preserve_hostname: false/preserve_hostname: true/' /etc/cloud/cloud.cfg
    elif ! grep -q '^preserve_hostname: true' /etc/cloud/cloud.cfg; then
      echo 'preserve_hostname: true' >> /etc/cloud/cloud.cfg
    fi
  fi
  ok "Hostname = $HOSTNAME."
}

# ---------------- Fase 30: Access ----------------
phase_30() {
  hdr "FASE 30 · Tailscale & amankan akses"
  note "APA    : Pasang Tailscale, verifikasi, baru tutup port publik + hardening SSH."
  note "KENAPA : Akses cuma lewat Tailscale; port publik ditutup total."
  if $DRY_RUN; then sub "install tailscale; login; CHECKPOINT verifikasi; ufw deny incoming + allow tailscale0; hardening sshd"; return 0; fi
  need_root

  # install tailscale
  if have tailscale; then
    ok "Tailscale sudah terpasang."
  else
    note "Memasang Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh >/dev/null 2>&1 || die "Gagal memasang Tailscale."
    ok "Tailscale terpasang."
  fi

  # login
  if tailscale status >/dev/null 2>&1 && tailscale ip -4 >/dev/null 2>&1; then
    ok "Sudah login Tailscale."
  else
    hdr "Login Tailscale"
    if [[ -n "$TAILSCALE_AUTHKEY" ]]; then
      note "Login otomatis pakai auth key."
      tailscale up --ssh --authkey "$TAILSCALE_AUTHKEY"
    else
      note "⚠ PERLU AKSI LU:"
      note "   Sebentar lagi muncul LINK di layar ini (https://login.tailscale.com/...)."
      note "   Buka link itu di browser laptop/HP, login akun Tailscale, klik Connect."
      note "   Script menunggu sampai selesai."
      tailscale up --ssh
    fi
  fi

  tailscale set --hostname "$HOSTNAME" >/dev/null 2>&1 || true
  discover_net
  [[ -n "$TAILSCALE_IP" ]] || die "Tidak dapat IP Tailscale. Login gagal?"
  ok "Tailscale IP = $TAILSCALE_IP  (nama: ${DNSNAME%.*})"

  # checkpoint
  if ! $SKIP_VERIFY; then
    hdr "VERIFIKASI (JANGAN DILEWAT)"
    note "Buka terminal BARU di laptop/HP (Tailscale nyala), jalankan:"
    note "    ssh ${ADMIN_USER}@${DNSNAME%.*}"
    note "Harus bisa masuk TANPA password."
    if ! ask_yn "Berhasil masuk tanpa password?" n; then
      err "Dihentikan. Belum ada yang dikunci. Cek ACL Tailscale lalu jalankan lagi."
      exit 1
    fi
  else
    warn "Verifikasi dilewati (--skip-verify)."
  fi

  # firewall
  have ufw || apt-get install -y -qq ufw >/dev/null
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw allow in on tailscale0 >/dev/null
  ufw --force enable >/dev/null
  ok "Firewall aktif (blok publik, izinkan Tailscale)."

  # hardening sshd
  mkdir -p /etc/ssh/sshd_config.d
  cat > /etc/ssh/sshd_config.d/00-hardening.conf <<'EOF'
# Dibuat oleh vpslab bootstrap. Prefix "00-" penting:
# OpenSSH memakai nilai PERTAMA yang ditemukan.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
  if sshd -t; then
    systemctl restart ssh
    ok "SSH di-hardening (password dimatikan)."
  else
    warn "Config SSH tidak valid, tidak di-restart."
  fi
  sshd -T 2>/dev/null | grep -q '^passwordauthentication no' && ok "Terverifikasi: PasswordAuthentication=no."
}

# ---------------- Fase 40: OS ----------------
phase_40() {
  hdr "FASE 40 · Fondasi OS"
  note "APA    : Update, auto-patch keamanan, timezone, swap, cloud-init."
  note "KENAPA : Sistem aman & terawat, dan siap buat beban AI."
  if $DRY_RUN; then sub "apt full-upgrade; unattended-upgrades (tanpa auto-reboot); timezone; swap $SWAP_SIZE; disable cloud-init; tools"; return 0; fi
  need_root
  export DEBIAN_FRONTEND=noninteractive

  apt-get update -qq
  apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" full-upgrade >/dev/null
  ok "Paket di-update."

  apt-get install -y -qq unattended-upgrades apt-listchanges >/dev/null
  cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
  cat > /etc/apt/apt.conf.d/52-vpslab-noreboot <<'EOF'
Unattended-Upgrade::Automatic-Reboot "false";
EOF
  systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
  ok "Auto-patch keamanan aktif (tanpa auto-restart)."

  timedatectl set-timezone "$TIMEZONE" 2>/dev/null && ok "Timezone = $TIMEZONE."

  if ! swapon --show 2>/dev/null | grep -q '/swapfile'; then
    fallocate -l "$SWAP_SIZE" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    ok "Swap $SWAP_SIZE dibuat."
  else
    ok "Swap sudah ada."
  fi
  printf 'vm.swappiness=10\nvm.vfs_cache_pressure=50\n' > /etc/sysctl.d/99-swappiness.conf
  sysctl --system >/dev/null 2>&1 || true

  touch /etc/cloud/cloud-init.disabled
  systemctl disable cloud-init cloud-init-local cloud-config cloud-final >/dev/null 2>&1 || true
  ok "cloud-init dimatikan."

  if [[ "$INSTALL_TOOLS" == "true" ]]; then
    apt-get install -y -qq git tmux htop jq unzip rsync ncdu >/dev/null
    ok "Tools dasar terpasang."
  fi
}

# ---------------- Fase 50: Docker + struktur ----------------
render() { # render file: ganti placeholder
  sed -i \
    -e "s|__HOSTNAME__|${HOSTNAME}|g" \
    -e "s|__ADMIN_USER__|${ADMIN_USER}|g" \
    -e "s|__TS_IP__|${TAILSCALE_IP:-100.64.0.1}|g" \
    -e "s|__PUBLIC_IP__|${PUBLIC_IP:-?}|g" \
    -e "s|__TAILNET__|${TAILNET:-ts.net}|g" \
    -e "s|__TZ__|${TIMEZONE}|g" \
    -e "s|__PLAYGROUND_DIR__|${PLAYGROUND_DIR}|g" \
    -e "s|__DEFAULT_PORT__|${DEFAULT_PORT}|g" \
    -e "s|__DEFAULT_IMAGE__|${DEFAULT_IMAGE}|g" \
    "$1"
}

write_agents() { # $1 = path tujuan
  cat > "$1" <<'AGENTSEOF'
# AGENTS.md — VPS Lab (`__HOSTNAME__`)

> Dibaca otomatis oleh OpenCode (dan tool lain yang mendukung `AGENTS.md`).
> Berlaku untuk SEMUA folder di bawah home user admin.
> Sumber kebenaran tunggal; `~/.config/opencode/AGENTS.md` = symlink ke file ini.

---

## 0. TL;DR
- VPS **lab pribadi**. Akses **HANYA via Tailscale SSH**; port publik tertutup.
- Login: **`ssh __ADMIN_USER__@__HOSTNAME__`**.
- Semua eksperimen = **container Docker** di **`__PLAYGROUND_DIR__/<nama-lab>/`**.
- **JANGAN bind port ke `0.0.0.0`.** Bind ke IP Tailscale **`__TS_IP__`**. Akses: **`__HOSTNAME__:<PORT>`**.
- **Jangan install aplikasi lab langsung ke OS.**
- Break-glass kalau terkunci: **console/VNC panel provider**.

## 1. Konteks & prinsip
- Pemilik: non-engineer tapi paham IT. Komunikasi: Bahasa Indonesia santai.
- Prinsip: **"cattle, not pet"** — bisa dibangun ulang dari resep (script + snapshot).
- **Urutan aman:** pasang jalur baru → TES → baru putus jalur lama.

## 2. Identitas
| Item | Nilai |
|---|---|
| Hostname | `__HOSTNAME__` |
| Tailscale | `__HOSTNAME__` (`__TS_IP__`) |
| Tailnet | `__TAILNET__` |
| Public IP | `__PUBLIC_IP__` (tidak dipakai untuk akses) |
| User | `root`, `__ADMIN_USER__` (grup: `sudo`, `docker`) |
| Timezone | `__TZ__` |

## 3. Keamanan
- ufw: deny incoming, allow outgoing, allow in on `tailscale0`.
- sshd: `PasswordAuthentication no`, `PermitRootLogin prohibit-password`.
- Tailscale SSH aktif (login tanpa password).
- unattended-upgrades aktif (tanpa auto-restart).
- cloud-init dimatikan. Swap aktif.
- ⚠️ Grup `docker` = setara root (akses mesin sudah dibatasi Tailscale).

## 4. Struktur folder
```
__PLAYGROUND_DIR__/
├── README.md
├── _template/          # cetakan lab baru
└── <nama-lab>/         # docker-compose.yml + .env + data/ + README.md
```

## 5. ATURAN ISOLASI & AKSES (WAJIB)
1. **Jangan** publish port ke `0.0.0.0`.
   - ❌ `ports: ["8080:80"]` (bocor ke internet — Docker nembus ufw)
   - ✅ `ports: ["__TS_IP__:8080:80"]` → akses `http://__HOSTNAME__:8080`
2. Akses dari client hanya lewat Tailscale (format `__HOSTNAME__:<PORT>`).
3. **Dilarang `tailscale funnel`** (publik). Kalau perlu, pakai `tailscale serve` (privat).
4. **Jangan install app lab ke OS** — lewat container.
5. Rahasia di `.env` (jangan di-commit).
6. Tiap lab wajib punya `README.md`.
7. Setiap perubahan dicatat di changelog.

## 6. Cara bikin lab baru
```bash
cd __PLAYGROUND_DIR__
cp -r _template nama-lab && cd nama-lab
cp .env.example .env      # atur PORT
docker compose up -d
# akses: http://__HOSTNAME__:<PORT>
```

## 7. Gotchas
- **Bind-mount folder harus ada dulu.** Kalau `data/` belum ada saat `up`, Docker membuatnya milik `root` → error izin + 403. Templat sudah menyertakan `data/`. Fix: `sudo chown -R $USER:$USER data`.
- Gunakan `docker compose` (v2), bukan `docker-compose`.

## 8. Changelog
- Dibuat otomatis oleh `bootstrap.sh`.
AGENTSEOF
  render "$1"
}

write_playground() {
  mkdir -p "$PLAYGROUND_DIR/_template/data"

  cat > "$PLAYGROUND_DIR/README.md" <<'EOF'
# Playground — Lab Docker

Satu lab = satu folder. Bikin lab baru dari `_template`.

```bash
cd ~/playground
cp -r _template nama-lab && cd nama-lab
cp .env.example .env      # atur PORT
docker compose up -d
```
Akses dari PC/HP (Tailscale nyala): **http://<host>:<PORT>**

Aturan: lihat `../AGENTS.md`. **Jangan** bind ke `0.0.0.0`.
EOF

  cat > "$PLAYGROUND_DIR/_template/README.md" <<'EOF'
# Lab: <nama-lab>

Deskripsi: <apa ini>

- **Akses:** http://<host>:<PORT>
- **Port:** lihat `.env`
- **Data:** folder `data/`

```bash
docker compose up -d
docker compose logs -f
docker compose down
```

> Penting: folder `data/` harus ada sebelum `up` (templat sudah menyertakannya).
EOF

  cat > "$PLAYGROUND_DIR/_template/docker-compose.yml" <<'EOF'
# Cetakan lab. Cara pakai:
#   cp -r _template <nama-lab> && cd <nama-lab>
#   cp .env.example .env   # atur PORT
#   docker compose up -d
services:
  app:
    image: __DEFAULT_IMAGE__          # <-- ganti sesuai aplikasi
    container_name: lab-app           # <-- beri nama unik per lab
    ports:
      # Bind ke IP TAILSCALE -> akses via <host>:PORT, TIDAK bocor ke publik.
      # JANGAN ganti jadi "8080:80" (itu 0.0.0.0 = bocor).
      - "__TS_IP__:${PORT:-__DEFAULT_PORT__}:80"
    volumes:
      - ./data:/usr/share/nginx/html
    environment:
      - TZ=__TZ__
    restart: unless-stopped
EOF

  cat > "$PLAYGROUND_DIR/_template/.env.example" <<'EOF'
# Salin jadi .env lalu atur PORT. JANGAN commit .env.
PORT=__DEFAULT_PORT__
TZ=__TZ__
EOF

  cat > "$PLAYGROUND_DIR/_template/.gitignore" <<'EOF'
.env
data/
*.log
EOF

  cat > "$PLAYGROUND_DIR/_template/data/index.html" <<'EOF'
<!doctype html>
<html lang="id"><head><meta charset="utf-8"><title>Lab</title></head>
<body style="font-family:system-ui;text-align:center;padding:3rem">
<h1>🚀 Lab jalan!</h1>
<p>Ganti file <code>data/index.html</code> dengan konten lab lu.</p>
</body></html>
EOF

  # render placeholder di semua file yang butuh
  local f
  while IFS= read -r -d '' f; do render "$f"; done < <(find "$PLAYGROUND_DIR" -type f -print0)
}

phase_50() {
  hdr "FASE 50 · Docker & struktur lab"
  note "APA    : Pasang Docker, bikin struktur folder lab + aturan (AGENTS.md)."
  note "KENAPA : Tiap eksperimen jalan di container terisolasi; mesin tetap bersih."
  if $DRY_RUN; then sub "install Docker CE + Compose; grup docker; daemon.json; bikin $PLAYGROUND_DIR + _template + AGENTS.md"; return 0; fi
  need_root
  export DEBIAN_FRONTEND=noninteractive
  discover_net

  # install docker
  if have docker; then
    ok "Docker sudah terpasang."
  else
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
    ok "Docker terpasang."
  fi
  usermod -aG docker "$ADMIN_USER"
  systemctl enable --now docker >/dev/null 2>&1 || true

  mkdir -p /etc/docker
  cat > /etc/docker/daemon.json <<EOF
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "${DOCKER_LOG_MAX_SIZE}", "max-file": "3" },
  "live-restore": true
}
EOF
  systemctl restart docker
  ok "Config Docker (log rotation) diterapkan."

  # struktur lab
  local HOME_DIR; HOME_DIR="$(getent passwd "$ADMIN_USER" | cut -d: -f6)"
  PLAYGROUND_DIR="${PLAYGROUND_DIR:-$HOME_DIR/playground}"
  mkdir -p "$PLAYGROUND_DIR"
  write_playground

  # AGENTS.md: untuk admin & root (+ symlink). Tidak menimpa kalau sudah ada.
  maybe_write_agents() {
    local p="$1" label="$2"
    if [[ -f "$p" && "$FORCE" != true ]]; then
      sub "AGENTS.md ($label) sudah ada - dibiarkan (pakai --force untuk menimpa)."
    else
      write_agents "$p"; ok "AGENTS.md ($label) dibuat."
    fi
  }
  maybe_write_agents "$HOME_DIR/AGENTS.md" "admin"
  mkdir -p "$HOME_DIR/.config/opencode"
  ln -sf "$HOME_DIR/AGENTS.md" "$HOME_DIR/.config/opencode/AGENTS.md"

  maybe_write_agents /root/AGENTS.md "root"
  mkdir -p /root/.config/opencode
  ln -sf /root/AGENTS.md /root/.config/opencode/AGENTS.md
  ok "Symlink AGENTS.md siap (admin + root)."

  # ownership
  chown -R "$ADMIN_USER:$ADMIN_USER" "$HOME_DIR/AGENTS.md" "$HOME_DIR/.config" "$PLAYGROUND_DIR"
  ok "Kepemilikan file diserahkan ke '$ADMIN_USER'."

  # verifikasi
  if su - "$ADMIN_USER" -c "docker run --rm hello-world" >/dev/null 2>&1; then
    ok "Verifikasi: Docker jalan sebagai '$ADMIN_USER'."
  else
    warn "Docker belum jalan untuk '$ADMIN_USER' (mungkin perlu re-login)."
  fi
}

# ---------------------------------------------------------------------------
#  MAIN
# ---------------------------------------------------------------------------
banner() {
  cat <<EOF
${B}========================================================${R}
  ${B}VPS LAB BOOTSTRAP${R}  ·  Ubuntu fresh -> lab siap pakai
${B}========================================================${R}
Fase:
  10) Preflight (cek + alat dasar)
  20) User admin & hostname
  30) Tailscale & amankan akses   <- ada 1 aksi manual (login)
  40) Fondasi OS (update, swap, timezone)
  50) Docker & struktur lab
${DIM}Aman dijalankan ulang. Ctrl+C kapan saja.${R}
EOF
  summary_vars
}

phase_enabled() {
  local n="$1"
  [[ -n "$ONLY" && "$ONLY" != "$n" ]] && return 1
  [[ -n "$FROM" && "$n" -lt "$FROM" ]] && return 1
  return 0
}

main() {
  need_root
  touch "$LOG_FILE" 2>/dev/null || true
  SCRIPT_START="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "=== bootstrap start $SCRIPT_START ===" >>"$LOG_FILE" 2>/dev/null || true

  banner
  $DRY_RUN && warn "Mode DRY-RUN: tidak ada yang diubah."
  wizard
  validate_config
  summary_vars
  if ! $ASSUME_YES && ! $DRY_RUN; then
    ask_yn "Mulai sekarang?" y || { note "Dibatalkan."; exit 0; }
  fi

  phase_enabled 10 && phase_10
  phase_enabled 20 && phase_20
  phase_enabled 30 && phase_30
  phase_enabled 40 && phase_40
  phase_enabled 50 && phase_50

  hdr "SELESAI"
  ok "Bootstrap selesai."
  note "Login: ssh ${ADMIN_USER}@${HOSTNAME}"
  note "Akses lab: http://${HOSTNAME}:<PORT>"
  note ""
  warn "SEKARANG: bikin SNAPSHOT di panel provider (nama: baseline)."
  note "Itu 'titik balik' lu. Detail: /root/AGENTS.md dan $PLAYGROUND_DIR/../AGENTS.md"
}

main
