# Deploy — pantau dari HP tanpa PC nyala

Arsitekturnya tanpa server berbayar sama sekali:

```
GitHub Actions (cron)  ->  pindai pasar  ->  tulis docs/data/*.json
                                          ->  kirim Telegram / ntfy
                                                    |
                                          GitHub Pages menyajikan docs/
                                                    |
                                              buka dari HP
```

**Gratis, tanpa kartu kredit, tanpa VPS.** Yang harus Anda lakukan sendiri: membuat
akun GitHub dan repo — saya tidak bisa mendaftarkan akun atas nama Anda.

---

## 1. Buat repo dan unggah

Di [github.com/new](https://github.com/new), buat repo baru — misal `idx-quant`.

> **Publik atau privat?**
> **Privat** — data tidak terlihat siapa pun, tapi kuota Actions 2.000 menit/bulan.
> Jadwal `*/30` memakai ~990 menit/bulan, masih aman.
> **Publik** — menit Actions tak terbatas (bisa `*/15`), tapi seluruh isi repo
> termasuk data harga terlihat publik. Token tetap aman karena disimpan di Secrets,
> bukan di repo — asalkan `.gitignore` tidak diubah.

Dari folder proyek:

```bash
git init
git add .
git commit -m "IDX quant screener"
git branch -M main
git remote add origin https://github.com/USERNAME/idx-quant.git
git push -u origin main
```

Periksa dulu bahwa `data/alert_config.json` **tidak** ikut ter-commit:

```bash
git ls-files | grep alert_config
```

Kalau muncul hasil, hentikan — file itu berisi token Telegram Anda.

---

## 2. Simpan token sebagai Secret

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

| Nama | Isi | Wajib? |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | token dari @BotFather | untuk Telegram |
| `TELEGRAM_CHAT_ID` | hasil `--telegram` di lokal | untuk Telegram |
| `NTFY_TOPIC` | nama topik ntfy Anda | untuk ntfy |

Cukup salah satu saluran. Ambil nilainya dari `data/alert_config.json` di komputer Anda.

**Jangan pernah menaruh token di dalam file yang di-commit.** Secrets tidak terlihat
di log, bahkan pada repo publik.

---

## 3. Nyalakan GitHub Pages

Repo → **Settings** → **Pages**:

- Source: **Deploy from a branch**
- Branch: **main**, folder: **/docs**
- Save

Setelah 1–2 menit, dashboard tersedia di:

```
https://USERNAME.github.io/idx-quant/
```

Buka di HP, lalu **Add to Home Screen** — tampil seperti aplikasi.

---

## 4. Jalankan pertama kali

Repo → tab **Actions** → **IDX Monitor** → **Run workflow**.

Sekitar 2–3 menit. Setelah selesai, muat ulang halaman Pages — data sudah muncul.

Setelah itu berjalan otomatis tiap 30 menit pada jam bursa, Senin–Jumat.

---

## Batas yang perlu dipahami

**Keterlambatan bertumpuk.** Cron GitHub Actions bersifat *best-effort* dan bisa
tertunda 5–15 menit, terutama pada menit bulat yang ramai. Ditambah delay data Yahoo
10–20 menit, total bisa **15–35 menit**. Ini alat pemantau — untuk melihat apa yang
sedang bergerak, bukan untuk entry presisi. Eksekusi tetap lewat aplikasi broker Anda.

**Kuota Actions.** Repo privat dapat 2.000 menit/bulan gratis. Satu run ~3 menit,
jadwal `*/30` pada jam bursa = ~15 run/hari × 22 hari ≈ **990 menit/bulan**. Aman.
Kalau diubah ke `*/15`, jadi ~1.980 menit — mepet; pakai repo publik untuk itu.

**Data publik bila repo publik.** Isi `docs/data/*.json` adalah harga IDX yang memang
publik, jadi risikonya kecil. Tapi topik ntfy Anda **tidak boleh** publik — pakai
Secrets, dan bila khawatir gunakan Telegram yang tertutup.

**Riwayat alert.** Disimpan lewat cache Actions agar notifikasi yang sama tidak
berulang antar-run. Cache bisa dihapus GitHub setelah 7 hari tanpa akses; efeknya
paling buruk hanya satu notifikasi terkirim ulang.

---

## Menjalankan lebih sering

Ubah baris cron di `.github/workflows/idx-monitor.yml`:

```yaml
- cron: "*/15 2-9 * * 1-5"   # tiap 15 menit (repo publik)
- cron: "*/30 2-9 * * 1-5"   # tiap 30 menit (default, aman untuk privat)
- cron: "0 2-9 * * 1-5"      # tiap jam (paling hemat)
```

Ingat jadwal ditulis dalam **UTC**; `2-9` UTC = 09:00–16:00 WIB.
