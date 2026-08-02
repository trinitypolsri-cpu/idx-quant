"""Event study rilis BPS — apakah pasar bereaksi saat data diumumkan?

Inilah pengujian yang benar untuk mencari alpha dari data makro. Korelasi biasa
membandingkan angka bulan Mei dengan harga bulan Mei, padahal angkanya baru
diumumkan pertengahan Juni. Di sini yang diuji adalah reaksi pada HARI RILIS.

Tiga pertanyaan:
  1. Apakah return/volatilitas pada hari rilis berbeda dari hari biasa?
  2. Apakah arah reaksi bisa diprediksi dari KEJUTAN (angka aktual vs perkiraan)?
  3. Apakah reaksinya berlanjut (drift) atau langsung habis dalam sehari?
"""

from __future__ import annotations

import re
import warnings

import numpy as np
import pandas as pd

from idxquant import brs
from idxquant import data as dl
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)

ANGKA = re.compile(r"sebesar\s+([\d]+[,.]?\d*)\s*persen", re.I)


def nilai_dari_judul(judul: str) -> float | None:
    m = ANGKA.search(str(judul))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def jendela_return(px: pd.Series, tanggal: pd.Timestamp, h: int) -> float | None:
    """Return h hari bursa setelah tanggal rilis (h=0 berarti hari rilis itu sendiri)."""
    idx = px.index
    pos = idx.searchsorted(tanggal)
    if pos >= len(idx):
        return None
    if h == 0:
        if pos == 0:
            return None
        return float(px.iloc[pos] / px.iloc[pos - 1] - 1)
    if pos + h >= len(idx):
        return None
    return float(px.iloc[pos + h] / px.iloc[pos] - 1)


def main():
    df = pd.read_pickle(OUT_DIR / "brs.pkl") if (OUT_DIR / "brs.pkl").exists() \
        else brs.kelompokkan(brs.ambil_brs())
    # Range panjang membuat Yahoo menurunkan resolusi ke bulanan tanpa memberi
    # tahu. Ambil range terpanjang yang MASIH harian, diverifikasi, bukan diasumsikan.
    bench = px = None
    for rng in ("10y", "5y", "2y"):
        b = dl.fetch_one(BENCHMARK, rng=rng, interval="1d")
        cek = dl.periksa_resolusi(b, "1d")
        print(f"  {BENCHMARK} range={rng}: {cek.get('n_bar','?')} bar, "
              f"jarak median {cek.get('median_hari','?')} hari -> "
              f"{'harian' if cek['ok'] else 'BUKAN harian, dilewati'}")
        if cek["ok"]:
            bench, px = b, b["close"].dropna()
            break
    if px is None:
        print("Tidak ada range yang memberi data harian.")
        return
    ret_harian = px.pct_change().dropna()

    print("=" * 96)
    print(f"EVENT STUDY RILIS BPS — IHSG {px.index[0].date()} s/d {px.index[-1].date()}")
    print("=" * 96)

    hasil = []
    for tema in ("Inflasi", "Ekspor-Impor", "Pertumbuhan Ekonomi", "Ketenagakerjaan"):
        tgl = brs.kalender(df, tema)
        tgl = tgl[(tgl >= px.index[0]) & (tgl <= px.index[-1])]
        if len(tgl) < 20:
            continue
        r0 = [jendela_return(px, t, 0) for t in tgl]
        r0 = np.array([x for x in r0 if x is not None])
        if len(r0) < 20:
            continue

        # Pembanding: seluruh hari bursa
        mu_semua = float(ret_harian.mean())
        sd_semua = float(ret_harian.std(ddof=1))
        t_stat = (r0.mean() - mu_semua) / (r0.std(ddof=1) / np.sqrt(len(r0)))
        # Uji volatilitas: apakah |return| lebih besar di hari rilis?
        from scipy.stats import mannwhitneyu
        u, p_vol = mannwhitneyu(np.abs(r0), ret_harian.abs(), alternative="greater")

        hasil.append({
            "Tema": tema, "N rilis": len(r0),
            "Ret hari rilis%": round(float(r0.mean()) * 100, 4),
            "Ret hari biasa%": round(mu_semua * 100, 4),
            "t": round(float(t_stat), 2),
            "|Ret| rilis%": round(float(np.abs(r0).mean()) * 100, 3),
            "|Ret| biasa%": round(float(ret_harian.abs().mean()) * 100, 3),
            "p volatilitas": round(float(p_vol), 4),
        })

    tab = pd.DataFrame(hasil)
    print("\n--- Reaksi IHSG pada hari rilis ---")
    print(tab.to_string(index=False))
    print("\nt = apakah return rata-rata hari rilis beda dari hari biasa.")
    print("p volatilitas = apakah pergerakan (tanpa arah) lebih besar di hari rilis.")

    # ---------- kejutan inflasi ----------
    print("\n" + "=" * 96)
    print("KEJUTAN INFLASI — apakah ARAH reaksi bisa diprediksi?")
    print("=" * 96)
    inf = df[(df["tema"] == "Inflasi")].copy()
    inf["nilai"] = inf["title"].map(nilai_dari_judul)
    inf = inf.dropna(subset=["nilai", "rl_date"]).sort_values("rl_date")
    # Ambil satu rilis per bulan (yang y-on-y), buang duplikat
    inf = inf[inf["title"].str.contains("y-on-y", case=False, na=False)]
    inf = inf.drop_duplicates(subset=[inf["rl_date"].dt.to_period("M").name]
                              if False else "rl_date", keep="first")
    inf = inf[(inf["rl_date"] >= px.index[0]) & (inf["rl_date"] <= px.index[-1])]

    if len(inf) < 24:
        print(f"\nHanya {len(inf)} rilis dengan angka terbaca — terlalu sedikit.")
    else:
        # Perkiraan naif: nilai rilis sebelumnya. Kejutan = aktual - perkiraan.
        inf["perkiraan"] = inf["nilai"].shift(1)
        inf["kejutan"] = inf["nilai"] - inf["perkiraan"]
        inf = inf.dropna(subset=["kejutan"])
        for h in (0, 1, 5):
            inf[f"ret{h}"] = [jendela_return(px, t, h) for t in inf["rl_date"]]
        inf = inf.dropna(subset=["ret0"])

        print(f"\n{len(inf)} rilis inflasi y-on-y dengan angka terbaca "
              f"({inf['rl_date'].min().date()} .. {inf['rl_date'].max().date()})")
        naik = inf[inf["kejutan"] > 0]
        turun = inf[inf["kejutan"] < 0]
        print(f"\n  Kejutan inflasi NAIK  (n={len(naik):3}): "
              f"ret hari rilis {naik['ret0'].mean()*100:+.3f}%  "
              f"H+1 {naik['ret1'].mean()*100:+.3f}%  H+5 {naik['ret5'].mean()*100:+.3f}%")
        print(f"  Kejutan inflasi TURUN (n={len(turun):3}): "
              f"ret hari rilis {turun['ret0'].mean()*100:+.3f}%  "
              f"H+1 {turun['ret1'].mean()*100:+.3f}%  H+5 {turun['ret5'].mean()*100:+.3f}%")

        from scipy.stats import pearsonr, ttest_ind
        for h in (0, 1, 5):
            a, b = naik[f"ret{h}"].dropna(), turun[f"ret{h}"].dropna()
            if len(a) > 5 and len(b) > 5:
                t, p = ttest_ind(a, b, equal_var=False)
                r, pr_ = pearsonr(inf["kejutan"], inf[f"ret{h}"].fillna(0))
                print(f"\n  H+{h}: selisih naik-turun t={t:+.2f} p={p:.3f} | "
                      f"korelasi kejutan-return r={r:+.3f} p={pr_:.3f}")

        print("\n  Tafsir: kalau p besar (>0,05), arah reaksi TIDAK dapat diprediksi")
        print("  dari kejutan inflasi — pasar sudah memperhitungkannya lebih dulu.")

    tab.to_csv(OUT_DIR / "brs_event.csv", index=False)
    print(f"\nDisimpan: {OUT_DIR / 'brs_event.csv'}")


if __name__ == "__main__":
    main()
