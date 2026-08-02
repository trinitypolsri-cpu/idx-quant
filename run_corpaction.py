"""Adakah jejak sebelum pergerakan besar di IDX? Uji historis + kandidat hari ini."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import corpaction as ca
from idxquant import data as dl
from idxquant import probability as pr
from idxquant import setups as st
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 215)

AMBANG = 0.20      # lonjakan >= 20%
JENDELA = 5        # dalam 5 hari bursa


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)

    P = ca.kumpulkan(prep, ambang=AMBANG, jendela=JENDELA)
    if P.empty:
        print("Data tidak cukup."); return

    n_lonjak = int(P["lonjakan_awal"].sum())
    base = float(P["lonjakan_awal"].mean())
    print("=" * 100)
    print(f"JEJAK SEBELUM PERGERAKAN BESAR — lonjakan >= {AMBANG:.0%} dalam "
          f"{JENDELA} hari bursa")
    print("=" * 100)
    print(f"\n  {len(P):,} observasi · {P['ticker'].nunique()} emiten")
    print(f"  Episode lonjakan  : {n_lonjak:,}")
    print(f"  Base rate         : {base*100:.3f}%  (1 dari {1/base:.0f} hari-emiten)")

    print("\n--- Apakah ciri hari-H berbeda? (Mann-Whitney, dikoreksi FDR) ---")
    tab = ca.bandingkan_ciri(P)
    print(tab.to_string(index=False))

    lolos = tab[tab["lolos_fdr"]] if "lolos_fdr" in tab else tab.iloc[:0]
    print(f"\n  Ciri yang berbeda bermakna: {len(lolos)} dari {len(tab)}")

    # --- model prediktif ---
    print("\n" + "=" * 100)
    print("MODEL PREDIKTIF — latih pada masa lalu, uji pada masa depan")
    print("=" * 100)
    P2 = P.copy()
    P2["target"] = P2["lonjakan_awal"].astype(int)
    P2 = P2.sort_index()
    r = pr.uji_temporal(P2, ca.CIRI, "target")
    if "error" in r:
        print(r["error"]); return
    print(f"\n  latih {r['n_latih']:,} · kalibrasi {r['n_kalib']:,} · uji {r['n_uji']:,}")
    print(f"  base rate uji   : {r['base_uji']*100:.3f}%")
    print(f"  AUC             : {r['auc']:.4f}")
    lo, hi = pr.bootstrap_ci(r["y_uji"], r["p_uji"])
    print(f"  AUC 95% CI      : [{lo:.4f}, {hi:.4f}]")
    print(f"  Desil-1 peluang : {r['p_desil1']*100:.3f}%  "
          f"(lift {r['lift_desil1']:.1f}x)")

    if hi < 0.55:
        print("\n  AUC nyaris tidak beda dari 0,5 — jejak sebelum lonjakan praktis")
        print("  tidak terdeteksi dari harga dan volume saja.")
    elif r["lift_desil1"] > 2:
        print("\n  Ada jejak yang terukur. Desil teratas jauh di atas base rate.")

    print("\n--- Fitur paling berpengaruh ---")
    print(r["koefisien"].head(8).to_string(index=False))

    # --- kandidat hari ini ---
    print("\n" + "=" * 100)
    print("KANDIDAT HARI INI")
    print("=" * 100)
    scan = st.scan(prep)
    liq = set(scan[scan["likuid"]]["ticker"])
    hari = P[P.index == P.index.max()].copy()
    hari = hari[hari["ticker"].isin(liq)]
    if hari.empty:
        print("Tidak ada emiten likuid pada tanggal terakhir."); return
    hari["peluang"] = r["kalibrator"].predict(
        r["model"].peluang(hari)) if r.get("kalibrator") else np.nan
    top = hari.nlargest(12, "peluang")[
        ["ticker", "close", "peluang", "rvol10", "akum_diam", "rng_ratio",
         "hari_kuat", "ret20", "dari_hi60"]].copy()
    top["peluang%"] = (top["peluang"] * 100).round(3)
    top = top.drop(columns=["peluang"])
    for c in ("rvol10", "akum_diam", "rng_ratio"):
        top[c] = top[c].round(2)
    for c in ("ret20", "dari_hi60"):
        top[c] = (top[c] * 100).round(1)
    print(f"\nPer {P.index.max().date()} (base rate {r['base_uji']*100:.3f}%):\n")
    print(top.to_string(index=False))

    hari.to_csv(OUT_DIR / "corpaction_kandidat.csv")
    tab.to_csv(OUT_DIR / "corpaction_ciri.csv", index=False)
    print(f"\nDisimpan: corpaction_kandidat.csv, corpaction_ciri.csv")


if __name__ == "__main__":
    main()
