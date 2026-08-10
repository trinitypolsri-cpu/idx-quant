"""Apakah statistical arbitrage bekerja di IDX?"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import setups as st
from idxquant import statarb as sa
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES, sector_of

warnings.filterwarnings("ignore")
pd.set_option("display.width", 210)

BIAYA = 0.0083          # sekali putar IDX


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    scan = st.scan(prep)
    likuid = list(scan[scan["likuid"]]["ticker"])

    harga = pd.DataFrame({t: prep[t]["close"] for t in likuid}).dropna(how="all")
    harga = harga.dropna(axis=1, thresh=int(len(harga) * 0.9)).ffill()
    sektor = {t: sector_of(t) for t in harga.columns}

    print("=" * 100)
    print(f"STATISTICAL ARBITRAGE — {len(harga.columns)} emiten likuid, "
          f"{len(harga)} hari")
    print("=" * 100)

    # --- pindai pasangan sesektor ---
    print("\nMemindai pasangan SESEKTOR (alasan ekonomi wajib ada) ...")
    ps = sa.cari_pasangan(harga, sektor=sektor, hanya_sesektor=True)
    n_kombinasi = sum(1 for i, a in enumerate(harga.columns)
                      for b in list(harga.columns)[i + 1:]
                      if sektor.get(a) == sektor.get(b))
    print(f"  {n_kombinasi} kombinasi sesektor diuji · "
          f"{len(ps)} lolos (ADF<-2,9 dan half-life 2-60 hari)")
    if len(ps):
        print()
        print(ps.head(12).to_string(index=False))
    else:
        print("  TIDAK ADA pasangan terkointegrasi.")
        return

    # Berapa yang diharapkan lolos murni kebetulan?
    harap = n_kombinasi * 0.05
    print(f"\n  Diperkirakan lolos KEBETULAN pada ambang 5%: ~{harap:.0f}")
    if len(ps) <= harap:
        print("  Jumlah yang lolos SETARA kebetulan — hati-hati.")
    else:
        print(f"  Lolos {len(ps)/harap:.1f}x lipat dari yang diharapkan kebetulan.")

    # --- backtest ---
    print("\n" + "=" * 100)
    print("BACKTEST — z-score bergulir 60 hari, masuk |z|>2, keluar |z|<0,5")
    print("=" * 100)
    rows = []
    for r in ps.head(20).itertuples():
        for mode, lo in (("Long-short", False), ("Long-only", True)):
            h = sa.backtest_pasangan(harga[r.a], harga[r.b], r.hedge_ratio,
                                     biaya=BIAYA, long_only=lo)
            if h.get("n_trade", 0) < 3:
                continue
            rows.append({"Pasangan": f"{r.a}-{r.b}", "Mode": mode,
                         "Trade": h["n_trade"],
                         "Kotor%": round(h["ret_kotor_rata"] * 100, 2),
                         "Net%": round(h["ret_net_rata"] * 100, 2),
                         "Menang%": round(h["menang_net"] * 100, 0),
                         "Total%": round(h["total_net"] * 100, 1),
                         "Hari": round(h["hari_rata"], 0)})
    bt = pd.DataFrame(rows)
    if bt.empty:
        print("Tidak ada pasangan dengan cukup transaksi.")
        return
    print()
    print(bt.sort_values("Net%", ascending=False).head(16).to_string(index=False))

    # --- verdict ---
    print("\n" + "=" * 100)
    print("VONIS")
    print("=" * 100)
    for mode in ("Long-short", "Long-only"):
        s = bt[bt["Mode"] == mode]
        if s.empty:
            continue
        untung = (s["Net%"] > 0).sum()
        print(f"\n  {mode}: {len(s)} pasangan · rata-rata net "
              f"{s['Net%'].mean():+.2f}%/trade · {untung}/{len(s)} menguntungkan")
        print(f"    kotor rata-rata {s['Kotor%'].mean():+.2f}%  vs  "
              f"biaya {BIAYA*100*(2 if mode=='Long-short' else 1):.2f}%")

    ls = bt[bt["Mode"] == "Long-short"]
    if len(ls) and ls["Kotor%"].mean() < BIAYA * 200:
        print("\n  Gerak spread rata-rata TIDAK menutup biaya dua kaki.")
    print("\n  CATATAN PENTING: short selling tidak tersedia untuk ritel IDX,")
    print("  jadi hasil Long-short di atas TIDAK BISA DIEKSEKUSI — hanya acuan")
    print("  seberapa besar edge teoretisnya sebelum kendala pasar.")

    ps.to_csv(OUT_DIR / "statarb_pasangan.csv", index=False)
    bt.to_csv(OUT_DIR / "statarb_backtest.csv", index=False)
    print(f"\nDisimpan: statarb_pasangan.csv, statarb_backtest.csv")


if __name__ == "__main__":
    main()
