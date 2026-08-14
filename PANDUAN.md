# Panduan Menjalankan Sendiri — Tanpa Claude Code

Proyek ini **murni Python**. Claude Code hanya dipakai untuk membangunnya; untuk
menjalankannya Anda tidak memerlukannya sama sekali.

---

## A. Cara tercepat (sehari-hari)

Buka folder `idx-quant`, lalu **klik dua kali**:

```
jalankan.bat
```

Skrip itu akan: memeriksa Python → memasang paket yang kurang → menyalakan server →
**menunggu sampai data selesai dimuat** → baru membuka browser.

Butuh 30–60 detik. Jangan tutup jendela hitamnya.

Alamatnya: **http://127.0.0.1:8848**

Untuk berhenti: tutup jendela bernama *IDX Screener Server*.

---

## B. Kalau komputer baru / Python belum ada

**1. Pasang Python**

Unduh dari [python.org/downloads](https://www.python.org/downloads/) versi 3.10 atau
lebih baru.

> **PENTING:** saat memasang, centang **"Add Python to PATH"** di layar pertama.
> Kalau terlewat, semua perintah di bawah akan gagal dengan pesan
> `'python' is not recognized`.

**2. Ambil proyeknya**

Kalau folder `idx-quant` sudah ada di komputer, lewati langkah ini.

Kalau belum, unduh dari GitHub:

```bash
git clone https://github.com/trinitypolsri-cpu/idx-quant.git
```

Atau buka repo di browser → tombol hijau **Code** → **Download ZIP** → ekstrak.

**3. Pasang paket**

Buka Command Prompt di dalam folder `idx-quant`, lalu:

```bash
python -m pip install -r requirements.txt
```

**4. Jalankan**

```bash
python -m app.server 8848
```

Tunggu sampai muncul tulisan server siap, lalu buka **http://127.0.0.1:8848**
di browser.

---

## C. Perintah lain yang berguna

Semua dijalankan dari dalam folder `idx-quant`.

| Perintah | Fungsi |
|---|---|
| `python -m app.server 8848` | Nyalakan screener web |
| `python build_static.py` | Perbarui data dashboard HP |
| `python build_static.py --alert` | Perbarui + kirim notifikasi Telegram |
| `python -m idxquant.journal --status` | Lihat jurnal prediksi |
| `python -m idxquant.journal --nilai` | **Hitung hasil prediksi yang sudah matang** |
| `python run_demo.py` | Simulasi PnL beli saham rekomendasi |
| `python run_indikator_uji.py` | Uji ulang indikator mana yang punya edge |
| `python uji_tanpa_paket.py` | Cek build tidak rusak sebelum push |

---

## D. Dashboard HP tetap jalan sendiri

**https://trinitypolsri-cpu.github.io/idx-quant/**

Ini **tidak bergantung pada komputer Anda maupun Claude Code**. GitHub Actions
menjalankan pemindaian tiap 30 menit pada jam bursa (Senin–Jumat 09:00–16:00 WIB),
lalu menerbitkan hasilnya. Selama repo GitHub-nya ada, dashboard ini hidup terus.

Notifikasi Telegram juga dikirim dari sana, bukan dari komputer Anda.

---

## E. Kalau bermasalah

**`'python' is not recognized`**
Python belum masuk PATH. Pasang ulang dan centang "Add Python to PATH".

**Browser menampilkan "tidak bisa dijangkau"**
Servernya belum siap atau sudah mati. Cek jendela *IDX Screener Server*, atau
buka `server.log` di folder proyek.

**Port 8848 sudah dipakai**
Jalankan dengan port lain:

```bash
python -m app.server 8899
```

Lalu buka `http://127.0.0.1:8899`.

**Tampilan laptop beda dengan HP**
Server lokal memuat kode ke memori saat dinyalakan dan tidak membacanya ulang.
Kalau kodenya berubah, **restart servernya**. HP selalu mengikuti versi terbaru.

**Data tidak berubah-ubah**
Wajar di luar jam bursa. Data hanya bergerak Senin–Jumat 09:00–16:00 WIB.

---

## F. Yang perlu diingat soal isinya

Baca ringkasan temuan di bagian atas [README.md](README.md) sebelum mengambil
keputusan dari angka mana pun. Ringkasnya:

- Belum ada satu pun prediksi yang matang — **sistem ini belum terbukti**
- Universe punya survivorship bias, jadi semua angka backtest optimistis
- Edge-nya tipis: profit factor 1,0–1,2, drawdown 43–73%
- Rapor pertama yang bisa dipercaya keluar dari `journal --nilai` setelah
  21 hari bursa sejak prediksi pertama (31 Juli 2026)

Ini alat riset, bukan rekomendasi investasi.
