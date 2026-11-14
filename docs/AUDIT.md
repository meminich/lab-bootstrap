# Audit lab-bootstrap — 14 November 2026

## Lingkup dan bukti

Source lama pada commit `20ae16e3f1b17ac868ac45ad3065ace289e8c3ba`:
`bootstrap.sh`, README, config example, dan ignore rules. Pemeriksaan source,
bukan instalasi atau pengujian VM. Tidak mengubah VPS aktif atau aturan host.
Nomor baris berikut mengacu commit tersebut, bukan file arsip yang diberi guard.

## Temuan

| Prioritas | Lokasi lama | Masalah dan dampak |
|---|---|---|
| Kritis | 577–579 | `find` + `sed -i` seluruh Playground dapat menulis ulang DB/dokumen dan mengganti inode file bind-mount. |
| Tinggi | 679–688, 167–200 | Dry-run tetap menulis log dan wizard dapat menyimpan config. |
| Tinggi | 606–614, 642 | Docker config ditimpa dan daemon direstart; ownership seluruh workspace/.config diubah rekursif. |
| Tinggi | 316–327 | Checkpoint hanya jawaban manusia dan dapat dilewati, bukan bukti SSH dari client. |
| Tinggi | 329–352 | UFW mempertahankan izin publik existing. Validasi sshd gagal hanya memberi warning; file tidak dipulihkan. |
| Tinggi | 141–145 | Config shell di-source sebagai root; file config merupakan kode executable, bukan data. |
| Sedang | 294–312 | Node sudah login tidak selalu mengaktifkan SSH; kegagalan set hostname diabaikan. |
| Sedang | 410 | Fallback IP `100.64.0.1` bisa menghasilkan binding salah. |
| Sedang | README 13; 170 | Piped Bash bertentangan dengan wizard stdin terminal. |
| Sedang | 378, 395–397 | Klaim tanpa auto-restart keliru; cloud-init dimatikan tanpa kebutuhan provider yang dibuktikan. |
| Sedang | 382–387 | Hanya mengecek swap bernama /swapfile; file existing yang tidak aktif berpotensi ditimpa. |
| Sedang | 22, 151 | `HOSTNAME` lazim sudah diisi shell; default vpslab belum tentu dipakai. |
| Sedang | 420–495, 623–638 | Rules bercampur klaim runtime, dua salinan root/admin, pemuatan harness digeneralisasi, symlink existing ditimpa. |
| Sedang | 544 | `container_name: lab-app` menyebabkan konflik antarlayanan hasil copy template. |

## Tindakan dalam perubahan ini

- Eksekusi lama **dibatasi**, bukan dinyatakan telah diperbaiki: root entry point
  hanya help/rencana; arsip lama berhenti sebelum membaca config atau mengubah host.
- Instruksi install berbahaya dan klaim idempotent/siap pakai dicabut dari README.
- Template rules baru memisahkan instruksi dari status/inventaris dan memperjelas
  otorisasi data, Docker setara root, rollback, scope perubahan, dan harness opsional.
- Ubuntu 22.04 menjadi target desain. Konfigurasi legacy tidak aktif; belum ada
  installer/renderer baru yang memasang template rules ini.
- Tes regresi mengunci guard, mode rencana, dan kontrak dokumentasi/template.

Ini **bukan** patch yang membuat body legacy aman. Jangan menghapus guard atau
memakai commit lama untuk melewati blokir. Implementasi baru dan bukti VM adalah
pekerjaan terpisah, mengikuti DESIGN dan VERIFICATION.

## Belum terjawab / belum diuji

- Bootstrap Ubuntu fresh, reboot, firewall IPv4/IPv6, Docker, dan SSH Tailscale
  dari laptop belum diuji oleh perubahan repo ini.
- Rules di `templates/` belum di-render/dipasang. Rules host aktif tidak berubah.
- Branch protection, wajib review, dan konfigurasi keamanan akun GitHub tidak
  diubah; audit ini bukan audit seluruh akun GitHub atau repository lain.

## Referensi primer

- [Docker dan firewall/UFW](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
- [Prasyarat Tailscale SSH](https://tailscale.com/docs/features/tailscale-ssh).
- [Siklus dukungan Ubuntu](https://ubuntu.com/about/release-cycle).
- [Ansible local playbooks](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_delegation.html#local-playbooks).
