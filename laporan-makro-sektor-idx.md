# Analisis Makro & Rotasi Sektor — Pasar Saham Indonesia

**Tanggal laporan:** 30 Juli 2026
**Cakupan:** 281 emiten IDX diunduh, 87 lolos filter likuiditas, 11 sektor
**Jalur skill:** Macro → cross-sector + country

> **Catatan integritas data (baca dulu).** Tool Bigdata.com (`find_securities`,
> `bigdata_company_tearsheet`, `bigdata_search`, `bigdata_events_calendar`) **tidak tersedia**
> di sesi ini — server memerlukan OAuth yang tidak dapat dijalankan. Endpoint fundamental
> Yahoo (`quoteSummary`) mengembalikan 401. Akibatnya laporan ini **tidak memuat P/E,
> pertumbuhan EPS, estimasi konsensus, atau data sentimen analis** — kolom-kolom itu saya
> tandai kosong, bukan saya isi dengan tebakan. Yang ada di sini: data harga/volume harian
> 5 tahun yang saya hitung sendiri, plus konteks makro dari sumber publik bertanggal.

---

## Ringkasan eksekutif

IHSG di 6.186, **−32,6%** dari puncak 52 minggu (9.174) dan 95 hari bursa di bawah MA200.
Tetapi membaca ini sebagai "pasar beruang siklikal" adalah salah baca.

**Tesis utama:** koreksi ini bukan terutama cerita laba atau siklus ekonomi. Ini **cerita
struktur pasar dan kredibilitas** — tinjauan MSCI atas transparansi dan free float [1][2][6],
pelemahan rupiah melewati Rp17.900/USD [4][5], arus keluar asing ~US$3,65 miliar sepanjang
2026 [6], dan yang terbaru pengunduran diri mendadak Gubernur BI Perry Warjiyo pada
27 Juli 2026 [3][4][5].

Konsekuensinya berbeda dari pasar beruang biasa: pemulihan **tidak menunggu rebound laba**,
melainkan menunggu pemulihan kepercayaan asing dan tuntasnya reformasi free float.

**Variant perception saya vs pembacaan umum "IHSG ambruk":** ini **bukan** aksi jual tanpa
pandang bulu. Rata-rata korelasi pasangan 63 hari hanya **0,34** — moderat, bukan level panik —
sementara dispersi return 3 bulan mencapai **16,2%**. Pasar sedang membedakan dengan tajam.
Buktinya paling terang di dua ujung ekstrem: **GGRM hanya −1,0% dari puncak 52 minggunya dan
MAPI persis di puncaknya**, di saat indeks −32,6%. Yang hancur adalah kelompok tertentu, dan
kelompok itu bisa dinamai.

---

## Latar makro

| Faktor | Kondisi | Sumber |
|---|---|---|
| Suku bunga acuan BI | 5,75%, setelah +100 bps sejak Mei 2026 untuk menahan rupiah; ditahan Juli | [3][4] |
| Rupiah | ~Rp17.973/USD (24 Jul), melemah >7% sepanjang tahun; sempat 17.500–17.700 | [4][5] |
| Gubernur BI | Perry Warjiyo mundur 27 Jul 2026 (alasan kesehatan); Destry Damayanti pelaksana tugas | [3][4][5] |
| Klasifikasi MSCI | Indonesia **tetap** di Emerging Markets (putusan 24 Jun 2026), dengan catatan transparansi pemegang saham, free float, konsistensi reformasi | [1][2][6] |
| Konsentrasi pasar | 20 saham menguasai **85%** Indeks MSCI Indonesia | [6] |
| Reformasi free float | Batas minimum naik dari ~7,5% menuju **15%**; ditambah kerangka High Shareholding Concentration (HSC) dan keterbukaan pemegang saham >1% | [2][6] |
| Arus asing | Jual bersih ~US$3,65 miliar sepanjang 2026 | [6] |

Catatan: asumsi *risk-free* 5,75% yang saya pakai di backtest ternyata persis sama dengan
BI-Rate aktual — kebetulan yang menguntungkan, jadi perbandingan Sharpe di laporan backtest
sebelumnya tetap sahih.

---

## Papan skor sektor

Median emiten likuid per sektor. Kolom valuasi sengaja dikosongkan — lihat catatan integritas data.

| Sektor | N | 3 bulan | 6 bulan | 12 bulan | Di atas MA200 | P/E | Pertumbuhan EPS |
|---|---:|---:|---:|---:|---:|:---:|:---:|
| Konsumer & Kesehatan | 14 | −1,6% | −16,8% | −22,4% | 29% | n/a | n/a |
| Agri & Pangan | 6 | −15,9% | −17,9% | +7,9% | 33% | n/a | n/a |
| Keuangan | 8 | −4,4% | −19,7% | −18,8% | 12% | n/a | n/a |
| Energi | 15 | −19,2% | −24,5% | +31,9% | 27% | n/a | n/a |
| Telko & Teknologi | 12 | −19,8% | −27,5% | −20,0% | **0%** | n/a | n/a |
| Properti & Konstruksi | 8 | −19,5% | −28,7% | −28,3% | 12% | n/a | n/a |
| Industri Dasar | 6 | −28,2% | −30,0% | −14,9% | **0%** | n/a | n/a |
| Logam & Mineral | 13 | −28,2% | −36,6% | +1,9% | 8% | n/a | n/a |
| Utilitas & Lainnya | 2 | −36,0% | −45,7% | +205,0% | **0%** | n/a | n/a |

Sektor dengan N ≤ 2 (Transport & Pariwisata, Otomotif) dikeluarkan dari tabel — median dari
satu-dua emiten bukan statistik sektor.

**Median sektor menyesatkan di sini, dan itu justru temuannya.** Logam & Mineral bermedian
12 bulan +1,9%, menyembunyikan rentang TINS **+244%** sampai CUAN **−60%**. Analisis sektor
konvensional akan melewatkan hal terpenting di pasar ini.

---

## Temuan inti: pembelahan free float

Ketika saya bongkar per emiten, pola yang muncul menempel persis pada apa yang dipermasalahkan
MSCI — konsentrasi kepemilikan dan free float rendah [1][2][6].

**Kelompok yang runtuh** — sempat melesat, lalu jatuh paling dalam:

| Emiten | 12 bulan | 3 bulan | Dari puncak 52mg |
|---|---:|---:|---:|
| ARKO | +404% | −57,7% | −64,3% |
| CUAN | −60,0% | −50,0% | **−77,5%** |
| BREN | −59,0% | −31,3% | −69,7% |
| PANI | −60,5% | −28,0% | −62,9% |
| AMMN | −52,3% | −23,5% | −56,3% |

**Kelompok yang bertahan** — defensif dengan free float lebih sehat dan arus kas nyata:

| Emiten | 12 bulan | 3 bulan | Dari puncak 52mg | Di atas MA200 |
|---|---:|---:|---:|:---:|
| GGRM | +106% | +20,5% | **−1,0%** | ya |
| MAPI | +39,3% | +20,9% | **0,0%** | ya |
| TINS | +244% | −1,9% | −24,6% | ya |
| HMSP | +21,7% | −5,8% | −27,0% | tidak |
| INDF | −16,3% | +1,5% | −21,2% | ya |

Ini bukan rotasi sektor. Ini **unwinding satu kelompok kepemilikan terkonsentrasi**, dan
kebetulan anggotanya tersebar di beberapa sektor — itulah sebabnya median sektor terlihat
seragam buruk padahal penyebabnya spesifik.

**Implikasi ke depan yang belum banyak dihargai:** menaikkan free float minimum dari ~7,5%
ke 15% [2][6] secara mekanis **menambah pasokan saham** pada nama-nama yang persis paling
terkonsentrasi. Reformasi yang menyehatkan pasar dalam jangka panjang adalah tekanan pasokan
dalam jangka menengah bagi kelompok di tabel pertama. Saya belum melihat ini terhitung di
narasi "sudah murah, saatnya masuk".

---

## Posisi dalam siklus

**Fase: bear market akhir / awal stabilisasi — dengan risiko kebijakan yang belum selesai.**

| Sinyal | Pembacaan |
|---|---|
| Breadth MA50 | 6,9% → **62,1%** dalam sebulan — thrust nyata |
| Breadth MA200 | 4,6% → 16,1% — struktur tren **belum** pulih |
| IHSG vs MA200 | −18,3%; MA200 di 7.571 masih 22% di atas harga |
| Jarak dari dasar 52mg | +16,3% |
| Preseden thrust serupa | 3 episode sejak 2021; 2 yang matang berlanjut +11,7% dan +23,9% dalam 6 bulan |

Preseden itu **N=2**. Saya sebutkan sebagai konteks, bukan bukti — dua observasi tidak
membentuk distribusi.

Pola sektoralnya konsisten dengan defensif memimpin: Konsumer & Kesehatan terbaik dalam
3 bulan (−1,6%) dengan porsi di atas MA200 tertinggi (29%), sementara Industri Dasar,
Telko & Teknologi, dan Utilitas berada di **0%**. Itu urutan khas fase akhir penurunan.

---

## Pandangan rotasi

**Overweight — Konsumer & Kesehatan.** Return 3 bulan terbaik, porsi di atas MA200 tertinggi,
dan memuat dua-satunya emiten yang berada di/dekat puncak 52 minggu (GGRM, MAPI). Permintaan
domestik memberi sedikit penyangga terhadap rupiah. *Perlu diuji ulang saat data fundamental
tersedia — saya tidak tahu apakah defensif ini sudah mahal.*

**Overweight selektif — Energi & Agri.** Satu-satunya sektor dengan return 12 bulan positif
(+31,9% dan +7,9%) dan penopang eksposur ekspor terhadap rupiah lemah. Tetapi 3 bulan terakhir
sudah −19,2% dan −15,9%: momentumnya patah, jadi ini bukan tren yang sedang berjalan.

**Underweight — Logam & Mineral, Utilitas & Lainnya, Properti & Konstruksi.** Bukan karena
lemah harganya, melainkan karena di sinilah kelompok free float rendah terkonsentrasi, dan
tekanan pasokan dari reformasi 15% belum terjadi. Properti & Konstruksi juga paling terekspos
suku bunga 5,75% yang sedang ditahan tinggi demi rupiah.

**Underweight — Telko & Teknologi, Industri Dasar.** Nol persen anggota di atas MA200. Tidak
ada satu pun emiten yang menunjukkan struktur tren utuh.

**Underweight — Keuangan.** Hanya 12% di atas MA200. Terjepit dua arah: BI menahan bunga
tinggi untuk rupiah, sementara ketidakpastian kepemimpinan BI menambah premi risiko.

---

## Kaitan dengan hasil pemindaian kuantitatif

Dari 87 emiten likuid, hanya **BFIN** yang memicu setup dengan bukti statistik terkuat
(BaseBreakout: avg +1,58% per 21 hari, profit factor 1,25, N=1.300) sekaligus dua setup lain.
GGRM, ADRO, dan MAPI lolos trend template.

Kelangkaan sinyal ini konsisten dengan makro: hanya 16,1% emiten likuid di atas MA200, dan
dua setup dalam screener saya mensyaratkan hal itu — keduanya kosong hari ini.

Satu nuansa dari backtest yang relevan untuk kondisi sekarang: breakout yang **benar-benar
terjadi** saat IHSG di bawah MA200 justru memberi return 21 hari lebih tinggi (+3,23% vs
+1,08%), kemungkinan efek seleksi. N=307 dan terkonsentrasi di beberapa fase rebound —
indikasi, bukan bukti.

---

## Apa yang akan mengubah pandangan ini

**Menjadi lebih positif bila:** penunjukan Gubernur BI definitif yang diterima pasar [3][5];
rupiah stabil di bawah Rp17.500; arus asing berbalik menjadi beli bersih; breadth MA200
menembus 30–35%; MSCI menyatakan reformasi tuntas.

**Menjadi lebih negatif bila:** rupiah menembus Rp18.500; MSCI membuka kembali wacana
penurunan status; penerapan free float 15% dipercepat tanpa masa transisi; breadth MA50
kembali di bawah 30% (menandai thrust gagal — inilah risiko terbesar saat ini, karena
pengunduran diri Warjiyo terjadi 27 Juli, hanya tiga hari sebelum data ini berakhir, sehingga
dampaknya **belum terbaca** di angka mana pun di laporan ini).

---

## Batasan laporan ini

1. **Tidak ada data fundamental sama sekali.** Tanpa P/E, EV/EBITDA, ROIC, atau estimasi laba,
   saya tidak bisa menyatakan sektor mana yang *murah* — hanya mana yang *kuat secara harga*.
   Itu perbedaan besar, dan pandangan rotasi di atas harus dibaca dengan batasan tersebut.
2. **Survivorship bias.** Universe disusun dari nama yang dikenal hari ini; emiten yang
   delisting selama periode uji tidak terhitung.
3. **Harga dari Yahoo Finance**, bukan feed resmi IDX.
4. **Klasifikasi sektor buatan sendiri**, bukan IDX-IC resmi.
5. **Data berakhir 30 Juli 2026**, tiga hari setelah pengunduran diri Gubernur BI.

---

## Sumber

| # | Sumber | Tanggal | URL |
|---|---|---|---|
| 1 | The Diplomat — MSCI Raises New Transparency Concerns About Indonesia | Jun 2026 | https://thediplomat.com/2026/06/msci-raises-new-transparency-concerns-about-indonesia-as-emerging-markets-verdict-looms/ |
| 2 | Jakarta Globe — Indonesia to Raise Minimum Free Float Requirement to 15% After MSCI Review | 2026 | https://jakartaglobe.id/business/indonesia-to-raise-minimum-free-float-requirement-to-15-after-msci-review |
| 3 | CNBC — Indonesia central bank governor Perry Warjiyo steps down in surprise move | 27 Jul 2026 | https://www.cnbc.com/2026/07/27/indonesia-central-bank-governor-perry-warjiyo-steps-down.html |
| 4 | The Asian Banker — Perry Warjiyo's surprise resignation follows Bank Indonesia's 5.75% rate hold | Jul 2026 | https://www.theasianbanker.com/updates-and-articles/perry-warjiyo-s-surprise-resignation-follows-bank-indonesia-s-5-75-rate-hold |
| 5 | France24 — Indonesia bank chief quits, adding uncertainty to struggling economy | 27 Jul 2026 | https://www.france24.com/en/live-news/20260727-indonesia-central-bank-chief-steps-down-early-govt |
| 6 | Glass Lewis — Free Float, Ownership Transparency and Governance Quality | 2026 | https://www.glasslewis.com/article/free-float-ownership-transparency-governance-quality-what-indonesia-market-stress-revealed |
| 7 | Databoks — BI JISDOR Rupiah Weakens Following Perry Warjiyo's Resignation | 27 Jul 2026 | https://databoks.katadata.co.id/en/market/statistics/6a672e8a5f35e/bi-jisdor-rupiah-weakens-following-perry-warjiyos-resignation-announcement-monday-july-27-2026 |
| 8 | Jakarta Globe — MSCI Keeps Indonesia Stocks on Hold as Reform Review Continues | 2026 | https://jakartaglobe.id/business/msci-keeps-indonesia-stocks-on-hold-as-reform-review-continues |
| 9 | Data harga & volume: endpoint chart publik Yahoo Finance (`^JKSE`, `*.JK`), diolah sendiri | 30 Jul 2026 | — |

---

**Powered by Bigdata.com** - https://bigdata.com

> **Klarifikasi atribusi:** baris di atas adalah footer standar yang diwajibkan template skill.
> Untuk menghindari salah paham — **tidak ada data Bigdata.com dalam laporan ini.** Tool-nya
> tidak tersedia di sesi ini. Seluruh angka berasal dari sumber [1]–[9] di atas.

## Disclaimer

This output is for informational and research-assistance purposes only. It does **not** constitute investment, legal, tax, accounting, or other professional advice, and it is **not** a recommendation to buy, sell, or hold any security or instrument or to pursue any strategy. Information may be incomplete, estimated, delayed, or inaccurate. Past performance does not guarantee future results. Verify material facts independently and consult qualified advisors before making decisions.
