"""Seasonal IHSG — pola musiman bulanan dari histori terpanjang yang tersedia."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant.config import OUT_DIR

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
         "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def main():
    d = dl.fetch_one("^JKSE", rng="max", interval="1mo")
    if d is None or d.empty:
        print("Gagal mengambil histori IHSG.")
        return
    d = d[d["close"] > 0].copy()
    d["ret"] = d["close"].pct_change()
    d = d.dropna(subset=["ret"])

    print("=" * 94)
    print(f"SEASONAL IHSG — {d.index[0]:%b %Y} s/d {d.index[-1]:%b %Y} "
          f"({len(d)} bulan, {len(d)/12:.0f} tahun)")
    print("=" * 94)

    d["bulan"] = d.index.month
    d["tahun"] = d.index.year

    baris = []
    for m in range(1, 13):
        r = d[d["bulan"] == m]["ret"]
        if len(r) < 5:
            continue
        pos = float((r > 0).mean()) * 100
        # t-stat: apakah rata-rata bulan ini beda dari nol?
        t = float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))) if r.std(ddof=1) else np.nan
        baris.append({
            "Bulan": BULAN[m - 1], "N tahun": len(r),
            "Rata2%": round(float(r.mean()) * 100, 2),
            "Median%": round(float(r.median()) * 100, 2),
            "Menang%": round(pos, 0),
            "Terbaik%": round(float(r.max()) * 100, 1),
            "Terburuk%": round(float(r.min()) * 100, 1),
            "SD%": round(float(r.std(ddof=1)) * 100, 1),
            "t": round(t, 2),
        })
    tab = pd.DataFrame(baris)
    print()
    print(tab.to_string(index=False))

    # Signifikansi dengan koreksi banyak-uji
    print("\n--- Uji signifikansi ---")
    sig = tab[tab["t"].abs() > 2.0]
    print(f"Bulan dengan |t| > 2,0 : "
          f"{', '.join(sig['Bulan']) if len(sig) else 'tidak ada'}")
    print("Catatan: menguji 12 bulan sekaligus berarti ~1 bulan diperkirakan lolos")
    print("ambang 5% MURNI KARENA KEBETULAN. Ambang Bonferroni untuk 12 uji setara")
    print("|t| > 2,9 — gunakan itu sebelum mempercayai pola apa pun.")
    kuat = tab[tab["t"].abs() > 2.9]
    print(f"Lolos ambang Bonferroni: "
          f"{', '.join(kuat['Bulan']) if len(kuat) else 'TIDAK ADA SATU PUN'}")

    # Ranking
    print("\n--- Peringkat bulan (rata-rata) ---")
    urut = tab.sort_values("Rata2%", ascending=False)
    print("Terbaik  : " + ", ".join(
        f"{r.Bulan} ({r._3:+.2f}%)" for r in urut.head(3).itertuples()))
    print("Terburuk : " + ", ".join(
        f"{r.Bulan} ({r._3:+.2f}%)" for r in urut.tail(3).itertuples()))

    # Stabilitas: paruh awal vs paruh akhir sejarah
    print("\n--- Uji stabilitas: separuh awal vs separuh akhir sejarah ---")
    mid = d["tahun"].median()
    a = d[d["tahun"] <= mid].groupby("bulan")["ret"].mean()
    b = d[d["tahun"] > mid].groupby("bulan")["ret"].mean()
    ok = a.index.intersection(b.index)
    rho = float(a[ok].rank().corr(b[ok].rank()))
    print(f"Korelasi peringkat bulan antar era : {rho:+.3f}")
    print(f"  (sebelum {mid:.0f} vs sesudah)")
    if abs(rho) < 0.3:
        print("  -> Pola musiman TIDAK stabil antar era. Peringkat bulan pada satu")
        print("     periode tidak memprediksi periode berikutnya. Ini derau, bukan pola.")
    else:
        print("  -> Ada kemiripan peringkat antar era.")

    # Sell in May?
    mei_okt = d[d["bulan"].isin([5, 6, 7, 8, 9, 10])]["ret"]
    nov_apr = d[d["bulan"].isin([11, 12, 1, 2, 3, 4])]["ret"]
    print("\n--- 'Sell in May' di IHSG ---")
    print(f"  Mei-Okt : {mei_okt.mean()*100:+.2f}%/bulan  "
          f"(menang {(mei_okt>0).mean()*100:.0f}%, N={len(mei_okt)})")
    print(f"  Nov-Apr : {nov_apr.mean()*100:+.2f}%/bulan  "
          f"(menang {(nov_apr>0).mean()*100:.0f}%, N={len(nov_apr)})")
    beda = nov_apr.mean() - mei_okt.mean()
    se = np.sqrt(nov_apr.var(ddof=1)/len(nov_apr) + mei_okt.var(ddof=1)/len(mei_okt))
    print(f"  Selisih : {beda*100:+.2f}%/bulan  (t = {beda/se:.2f})")

    tab.to_csv(OUT_DIR / "seasonal_ihsg.csv", index=False)
    print(f"\nDisimpan: {OUT_DIR / 'seasonal_ihsg.csv'}")


if __name__ == "__main__":
    main()
