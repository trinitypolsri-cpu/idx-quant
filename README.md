# idxquant — aplikasi screener & riset kuantitatif Bursa Efek Indonesia

Aplikasi screener untuk memindai ratusan saham IDX, plus mesin riset untuk memvalidasi
setup teknikal secara statistik dan mem-backtest strategi momentum dengan biaya khas IDX.

## Menjalankan aplikasi

Klik dua kali **`Jalankan Screener.bat`**, atau:

```bash
python -m app.server 8848
```

Lalu buka http://127.0.0.1:8848

**Fitur:**
- Kartu setup — jumlah emiten yang memicu tiap setup hari ini, lengkap dengan bukti
  historisnya (edge 21 hari, jumlah sinyal, t-stat). Setup yang tidak lolos uji keandalan
  ditandai merah. Klik untuk memfilter.
- Daftar sektor — median return 1/3 bulan, porsi anggota di atas MA200. Klik untuk memfilter.
- Tabel screener — 15 kolom, semua bisa diurutkan, filter turnover/skor/MA200/pencarian ticker.
- Panel detail — klik baris mana pun untuk grafik candlestick + MA20/50/200 dan volume,
  dengan pilihan interval harian 6 bulan, harian 2 tahun, 15 menit, dan 5 menit.
- Tombol **Refresh data** — menarik ulang seluruh universe dari sumber data.

**Soal "realtime":** data berasal dari endpoint chart publik Yahoo Finance dan umumnya
**delay 10–20 menit**, bukan realtime murni. Bar intraday 1m/5m/15m tersedia dan mencakup
sesi penuh IDX (09:00–16:10 WIB). Untuk realtime sejati diperlukan feed berbayar dari
vendor data IDX atau API broker.

## Mode Scalping

Tab **Scalping · intraday** memindai 40 emiten terlikuid pada bar 5 menit dan menghitung
metrik yang relevan untuk horizon menit-ke-jam: VWAP, breakout opening range, volume
relatif paruh kedua sesi, posisi dalam rentang harian, dan sisa ruang sebelum ARA.

### Gesekan fraksi harga — faktor yang paling sering diabaikan

Fraksi harga IDX bersifat **absolut** (Rp1/2/5/10/25), bukan persentase. Akibatnya saham
murah jauh lebih mahal untuk di-scalp:

| Harga | Tick | Tick % | Biaya sekali putar | Contoh nyata |
|---|---:|---:|---:|---|
| Rp140 | Rp1 | 0,714% | **1,11%** | BIPI |
| Rp555 | Rp5 | 0,901% | **1,30%** | BRMS |
| Rp4.950 | Rp10 | 0,202% | **0,60%** | ASII |
| Rp24.250 | Rp25 | 0,103% | **0,50%** | UNTR |

Biaya sekali putar = komisi beli 0,15% + jual 0,25% + sekali silang spread. Artinya
scalping BRMS butuh gerak **>1,3%** hanya untuk balik modal, sementara UNTR cukup 0,50% —
**2,6x lebih murah**. Kolom `Peluang` menunjukkan berapa kali rentang harian menutup biaya
itu; di bawah 2x, gesekan memakan sebagian besar gerak.

### Corong dua tahap (gratis, tanpa API key)

Endpoint `spark` Yahoo mengembalikan banyak ticker dalam satu request (maksimal
**20 simbol**, diverifikasi 30 Jul 2026), tetapi **hanya harga penutup** — tanpa
high/low/volume, sehingga tidak bisa dipakai sendirian untuk VWAP atau opening range.

Karena itu scanner memakai corong:

| Tahap | Endpoint | Cakupan | Waktu |
|---|---|---:|---:|
| 1 — saring | `spark` (close saja) | 87 emiten likuid | ~1,0 s |
| 2 — gali | `chart` (OHLCV penuh) | 20 teratas | ~2,3 s |

Hasilnya **87 emiten dipindai dalam ~3,3 detik**, dibanding 40 emiten dalam 3,7 detik
dengan pendekatan lama — cakupan 2,2x lebih luas dan sedikit lebih cepat. Yang lebih
penting: corong ini memunculkan penggerak yang terlewat oleh pemeringkatan turnover
(MAPI RVol 3,01; ARTO RVol 2,52; BFIN +7,6%), karena emiten paling likuid belum tentu
emiten yang sedang bergerak.

### Soal feed realtime gratis — hasil pencarian

Sudah diprobe pada 30 Jul 2026, dan kesimpulannya tegas: **tidak ada feed realtime IDX
yang gratis.**

| Sumber | Hasil | Catatan |
|---|---|---|
| idx.co.id (5 endpoint resmi) | **HTTP 403** | Tantangan bot Cloudflare — tidak ditembus |
| Stooq | **404** | Tidak punya cakupan IDX sama sekali |
| Yahoo `v7/finance/quote` | **401** | Sudah butuh crumb/cookie |
| Yahoo `v7/finance/spark` | **200** | Jalan, close-only, maks 20 simbol |
| Yahoo `v8/finance/chart` | **200** | Jalan, OHLCV penuh, delay 10–20 menit |
| goapi.io | Daftar gratis | Paket ~Rp900rb/bulan |
| Invezgo | Berbayar | Tidak ada tier gratis di dokumentasi |

Realtime IDX adalah **produk berlisensi** — bursa menjualnya ke vendor, jadi tidak ada
yang membagikannya cuma-cuma. Yahoo adalah batas atas dari yang gratis.

Konsekuensi praktisnya: aplikasi ini layak untuk **riset pola dan seleksi kandidat**,
tidak untuk **eksekusi**. Untuk pencet beli-jual, gunakan aplikasi broker Anda yang
memang punya feed realtime berlisensi.

Jalankan sendiri probe-nya:

```bash
python probe_free_feeds.py
python probe_free2.py
```

### Menyambung feed berbayar (bila nanti berlangganan)

Aplikasi mendukung **sectors.app** dan **Invezgo** sebagai pengganti Yahoo. Keduanya butuh
API key berbayar yang harus Anda daftarkan sendiri:

```bash
setx SECTORS_API_KEY "kunci-anda"     # sectors.app (Supertype)
setx INVEZGO_API_KEY "kunci-anda"     # invezgo.com — realtime + broker summary + foreign flow
```

Verifikasi sambungan:

```bash
python -m idxquant.providers
```

Perintah ini mencoba beberapa kandidat path dan varian header auth terhadap API sungguhan,
lalu melaporkan mana yang hidup. **Ini perlu karena path endpoint kedua layanan tidak
terdokumentasi publik tanpa akun berbayar** — yang terkonfirmasi hanya base URL
(`https://api.sectors.app/v1`, `https://api.invezgo.com`) dan mekanisme autentikasinya.
Probe akan memberi tahu nilai `INVEZGO_AUTH_HEADER` dan `INVEZGO_AUTH_FORMAT` yang benar
untuk disimpan. Provider aktif dipilih otomatis: Invezgo → Sectors → Yahoo.

Untuk scalping, Invezgo lebih relevan karena menyediakan realtime, broker summary, dan
foreign flow — data bandarmology yang tidak ada di Yahoo maupun Sectors.

Invezgo juga punya **MCP server resmi** ([Invezgo/invezgo-mcp](https://github.com/Invezgo/invezgo-mcp)),
jadi bila nanti berlangganan, datanya bisa dipakai langsung dari Claude tanpa lewat
aplikasi ini. Konfigurasinya tetap memerlukan `INVEZGO_API_KEY` yang sama.

## API

Server juga mengekspos REST API (dokumentasi otomatis di `/api/docs`):

| Endpoint | Fungsi |
|---|---|
| `GET /api/status` | Level IHSG, regime, breadth, kesiapan data |
| `GET /api/screen` | Hasil screener; parameter `setup`, `sector`, `min_skor`, `min_turnover`, `only_above_ma200` |
| `GET /api/sectors` | Agregat per sektor |
| `GET /api/setups` | Jumlah sinyal per setup + bukti historisnya |
| `GET /api/chart/{ticker}` | OHLCV + indikator; parameter `rng`, `interval` |
| `POST /api/refresh?full=true` | Tarik ulang data |

## Pantau dari HP tanpa PC nyala

Lihat **[DEPLOY.md](DEPLOY.md)** — GitHub Actions menjalankan pindaian sesuai jadwal,
GitHub Pages menyajikan dashboard mobile. Gratis, tanpa kartu kredit, tanpa VPS.

```bash
python build_static.py --alert    # yang dijalankan Actions tiap 30 menit
```

## Notifikasi momentum ke HP

```bash
python run_alerts.py --setup     # cara pasang di HP
python run_alerts.py --tes       # kirim notifikasi uji
python run_alerts.py --pantau    # loop sepanjang jam bursa
python run_alerts.py --riwayat   # alert yang pernah dikirim
```

Tiga saluran: **ntfy.sh** (gratis, tanpa daftar akun, push ke HP), **Telegram**
(opsional, perlu bot token), dan **toast Windows**. Alert tetap tercatat di
`data/alerts.db` walau tidak ada saluran yang aktif.

> **Topik ntfy.sh bersifat PUBLIK.** Siapa pun yang tahu nama topiknya bisa membaca
> alert Anda. Nama topik dibuat acak 20 karakter dan disimpan di
> `data/alert_config.json` — jangan dibagikan. Untuk kerahasiaan penuh, pakai Telegram.

### Telegram (lebih privat daripada ntfy)

```bash
python run_alerts.py --telegram                      # panduan
python run_alerts.py --telegram --token "TOKEN_ANDA" # pasang + uji
```

Bot dibuat sendiri lewat **@BotFather** di Telegram (`/newbot`), lalu tekan START di
bot Anda. Perintah di atas memvalidasi token dan **menemukan `chat_id` otomatis** dari
`getUpdates`, jadi tidak perlu mencarinya manual. Tersimpan di `data/alert_config.json`.

### Level TP / R1-R3 / Support

```bash
python run_alerts.py --level BBCA --modal 100000000
```

Tersedia juga di panel detail aplikasi dan lewat `GET /api/levels/{ticker}`.

Yang dihitung: **pivot klasik** (PP, R1-R3, S1-S3) dari H/L/C hari sebelumnya,
**swing S/R fraktal** (level yang benar-benar diuji pasar), dan **rencana trade**
berbasis ATR dengan TP pada RR 1/2/3.

Tiga hal yang membedakannya dari kalkulator pivot biasa:

1. **Semua level dibulatkan ke fraksi harga IDX.** Order pada harga non-tick ditolak
   sistem bursa, jadi level yang tidak dibulatkan tidak bisa dipakai memasang order.
2. **TP dipotong batas ARA.** Target di atas ARA hari itu tidak mungkin tercapai —
   ditandai eksplisit, bukan disembunyikan.
3. **Pivot yang sudah dilewati harga ditandai.** Kalau harga di atas R3, level itu
   bukan resistance lagi melainkan support; menampilkannya sebagai target ke atas
   adalah pembacaan terbalik.

**Aturan stop loss.** SL memakai jarak ATR sebagai dasar. Support hanya dipakai bila
berada di antara 0,5x–1,5x jarak stop ATR, dan risiko dibatasi maksimum 8%. Versi
pertama mengambil `min(ATR, support)` — yang justru menjamin stop terlebar: pada BFIN
menghasilkan SL −18,5% karena support teruji terdekat jauh di bawah setelah lonjakan
harga. Setelah diperbaiki, SL-nya −5,98%.

### Aturan alert

| Aturan | Prioritas | Syarat |
|---|:---:|---|
| BaseBreakout | 5 | setup dengan bukti terkuat (t=2,49) |
| SqueezeBreakout | 4 | t=1,95 |
| MomentumIntraday | 4 | skor ≥85, di atas VWAP, RVol ≥1,5, sisa ARA ≥3%, peluang ≥2x |
| Wyckoff SOS/Spring | 4 | bias akumulasi, ≥3 bullish, ≤1 bearish, penerimaan VWAP ≥80% |
| TrendTemplate | 3 | t=3,48 tapi edge tipis |

**RSLeader dan PullbackUptrend sengaja tidak memicu alert** — t-stat 0,89 dan 0,44,
tidak signifikan. Memberi notifikasi untuk keduanya hanya melatih Anda mengabaikan
notifikasi.

### Pembatas banjir notifikasi

Uji pertama menghasilkan **27 notifikasi sekaligus** — itu spam, dan hasilnya orang
berhenti membaca. Dua perbaikan:

1. Syarat Wyckoff diperketat (SOS awalnya muncul di 13 dari 25 emiten — terlalu sering
   untuk disebut sinyal).
2. Hanya **5 alert prioritas tertinggi** dikirim satu per satu; sisanya digabung jadi
   **satu** notifikasi ringkasan.

Hasilnya: 20 sinyal → **6 notifikasi**. Ditambah cooldown per aturan (12 jam untuk
setup harian, 90 menit untuk momentum intraday) agar sinyal yang sama tidak berulang.

## Perekam data sendiri

Protokol resmi IDX — **FIX 5.0, OUCH, ITCH** — dijalankan lewat IDXSTI dan diakses
melalui langganan IDX Data Services berlisensi (Anggota Bursa / vendor data, koneksi
khusus). ITCH adalah feed multicast di jaringan bursa, bukan endpoint internet.

Yang bisa dilakukan tanpa lisensi: **merekam data yang lewat hari ini.** History
intraday IDX praktis tidak tersedia gratis, tapi kalau direkam setiap hari bursa,
dalam 3–6 bulan Anda punya dataset yang tidak dijual murah oleh siapa pun.

```bash
python -m idxquant.recorder --sekali    # satu putaran
python -m idxquant.recorder --sesi      # loop sepanjang jam bursa
python -m idxquant.recorder --status    # lihat isi database
```

Dua jalur, disimpan di SQLite (`data/intraday.db`):

| Jalur | Endpoint | Isi | Frekuensi |
|---|---|---|---|
| Tape | `spark` | harga penutup, seluruh universe likuid | ~60 detik |
| Bar | `chart` | OHLCV penuh, emiten terpantau | ~5 menit |

PRIMARY KEY komposit `(ticker, ts, interval)` membuatnya **idempoten** — poll berulang
menimpa, tidak menggandakan. Terverifikasi: rekam dua kali menghasilkan jumlah baris
identik. Satu hari ≈ **1,8 MB** (15.515 baris tape + 1.672 bar untuk 87 emiten),
jadi setahun ≈ 440 MB.

## Wyckoff & VWAP intraday

```bash
python run_risk_wyckoff.py
```

Membaca hubungan **usaha (volume) vs hasil (rentang harga)** pada bar 5 menit dari
database rekaman. Peristiwa yang dideteksi: Selling/Buying Climax, Spring, Upthrust,
Sign of Strength/Weakness, Absorption — plus VWAP sesi dengan pita deviasi berbobot
volume dan persentase penerimaan harga di atas VWAP.

## Monte Carlo risiko

Menjawab: hasil backtest itu keahlian sistem atau kebetulan urutan trade yang beruntung?
Bootstrap 10.000 jalur dari 498 trade nyata.

**Penting — `bobot` harus mencerminkan ukuran posisi sebenarnya.** Strategi memegang
10 posisi paralel, jadi tiap trade menggerakkan ~10% ekuitas (`bobot=0.10`). Menggandakan
return per-trade pada bobot penuh menghasilkan MaxDD −99% yang tidak berarti apa-apa dan
tidak cocok dengan kurva ekuitas backtest. Dengan bobot benar, simulasi menghasilkan
1,224x / MaxDD −28,9% — sepadan dengan backtest sesungguhnya 1,134x / −31,8%.

## DCF & fundamental — belum bisa

DCF dan valuasi fundamental **tidak tersedia** di pipeline ini: endpoint fundamental
Yahoo (`quoteSummary`) mengembalikan HTTP 401 dan tidak ada sumber gratis pengganti,
sehingga tidak ada revenue, margin, FCF, atau estimasi konsensus untuk dimodelkan.
Skill `creating-financial-models` punya mesin DCF dan Monte Carlo-nya, tapi tetap
memerlukan input fundamental yang harus Anda sediakan sendiri.

## Mesin riset (CLI)

Bagian di bawah ini adalah pipeline riset yang menghasilkan angka-angka yang dipakai aplikasi.

## Kenapa tidak pakai MCP

Tidak ada MCP server pasar saham Indonesia di registry (pencarian
`stock market / trading / IDX / market data` mengembalikan nol hasil). Server finance yang
tersedia di sesi ini (bigdata.com, S&P Global) butuh OAuth dan cakupannya global, bukan IDX.
Karena itu layer data dibangun langsung terhadap endpoint chart publik Yahoo Finance
(`^JKSE` untuk IHSG, `*.JK` untuk saham). Tanpa API key, tanpa autentikasi.

## Struktur

```
app/
  server.py       FastAPI: REST API + penyaji UI
  engine.py       state screener, refresh latar belakang, query terfilter
  static/
    index.html    aplikasi satu halaman (tabel, filter, grafik canvas)
idxquant/
  config.py       biaya transaksi, ARA/ARB, fraksi harga, filter likuiditas
  universe.py     290 kandidat ticker IDX + peta sektor
  data.py         downloader paralel + cache CSV
  indicators.py   indikator vektorisasi (Wilder smoothing agar cocok dgn Pine)
  setups.py       6 setup + screener cross-section
  backtest.py     event study + rotasi portofolio + metrik
pine/
  idx_momentum_strategy.pine   strategy TradingView, cermin run_rotation()
  idx_screener.pine            indikator 6 setup + alert + kolom Pine Screener
run_pipeline.py         unduh -> screening -> event study -> backtest
run_market_analysis.py  teknikal IHSG, breadth, rotasi sektor, uji thrust
check_metrics.py        pemisahan periode warm-up dari periode aktif
verify_dashboard.js     validasi JS/struktur dashboard.html
```

## Menjalankan

```bash
pip install pandas numpy requests
python run_pipeline.py            # tambahkan --refresh untuk abaikan cache
python run_market_analysis.py
```

Output ke `output/`: `screening.csv`, `event_study.csv`, `backtest_summary.csv`,
`equity_curve.csv`, `trades.csv`, `breadth.csv`, `sector_rotation.csv`.

## Asumsi backtest

| Parameter | Nilai |
|---|---|
| Komisi beli / jual | 0,15% / 0,25% (termasuk PPh final 0,1%) |
| Slippage | 0,15% per sisi |
| Ukuran lot | 100 lembar, dibulatkan ke bawah |
| Eksekusi | keputusan di bar tertutup, order di OPEN bar berikutnya |
| Stop | trailing 2,5 × ATR(14), dicek pada LOW harian |
| Rebalance | mingguan (Jumat), top-10 skor, bobot sama |
| Regime filter | IHSG harus di atas MA200-nya |
| Acuan bebas risiko | 5,75% (proxy BI-Rate) |

## Batasan yang diketahui

- **Survivorship bias.** Daftar ticker disusun dari nama yang dikenal saat ini, jadi saham
  yang delisting atau menjadi tidak likuid selama periode uji tidak ikut terhitung.
  Hasil sesungguhnya lebih buruk dari yang dilaporkan.
- **t-stat pada event study adalah batas atas.** Sinyal saling tumpang tindih antar waktu
  dan antar saham, sehingga observasi tidak independen dan standard error sebenarnya lebih besar.
- **200 hari pertama adalah warm-up MA200**, bukan keputusan strategi. Gunakan
  `check_metrics.py` untuk angka periode aktif.
- **Harga dari Yahoo Finance**, bukan feed resmi IDX; penyesuaian corporate action bisa berbeda.
- Backtest tidak memodelkan ARA/ARB, antrean order, atau suspensi saham — hanya tersedia
  sebagai helper di `config.py`.

Ini riset kuantitatif, bukan rekomendasi investasi.
