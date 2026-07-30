"""Kalibrasi skor ARA: skor sekian -> peluang ARA besok berapa persen?"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import ara as ar
from idxquant import data as dl
from idxquant import setups as st
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)


def skor_vektor(P: pd.DataFrame) -> pd.Series:
    """Versi vektor dari ara.skor() — sama persis, tapi cukup cepat untuk 300rb baris."""
    s = pd.Series(0.0, index=P.index)
    s += P["ara_kemarin"].fillna(False) * 30
    rv = P["rvol"].fillna(0)
    s += np.where(rv > 3.0, 20, np.where(rv > 2.0, 12, 0))
    s += (P["pos_close"].fillna(0) > 0.90) * 18
    s += P["dekat_ara"].fillna(False) * 20
    s += (P["dari_hi60"].fillna(-1) > -0.02) * 8
    s += (P["atr_pct"].fillna(0) > 0.07) * 4
    return s.clip(upper=100)


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    P = ar.kumpulkan(prep)
    P["skor"] = skor_vektor(P)
    base = float(P["ara_besok"].mean())

    print("=" * 88)
    print("KALIBRASI SKOR ARA — skor berapa, peluang berapa?")
    print("=" * 88)
    print(f"\nBase rate: {base*100:.3f}%  ({len(P):,} observasi)\n")

    bins = [0, 20, 30, 40, 50, 60, 70, 101]
    P["kelompok"] = pd.cut(P["skor"], bins=bins, right=False,
                           labels=[f"{a}-{b-1}" for a, b in zip(bins[:-1], bins[1:])])
    g = P.groupby("kelompok", observed=True).agg(
        N=("ara_besok", "size"), hit=("ara_besok", "sum"))
    g["P(ARA besok)%"] = (g["hit"] / g["N"] * 100).round(3)
    g["Lift"] = (g["hit"] / g["N"] / base).round(1)
    print(g.to_string())

    # Validasi luar sampel per kelompok skor
    P = P.sort_index()
    mid = P.index[len(P) // 2]
    tr, te = P[P.index <= mid], P[P.index > mid]
    b_te = float(te["ara_besok"].mean())
    print(f"\n--- Luar sampel (uji: {te.index[0].date()} - {te.index[-1].date()}) ---")
    gt = te.groupby("kelompok", observed=True).agg(
        N=("ara_besok", "size"), hit=("ara_besok", "sum"))
    gt["P%"] = (gt["hit"] / gt["N"] * 100).round(3)
    gt["Lift"] = (gt["hit"] / gt["N"] / b_te).round(1)
    print(gt.to_string())

    # Apa artinya secara praktis
    print("\n" + "=" * 88)
    print("ARTI PRAKTIS")
    print("=" * 88)
    tinggi = P[P["skor"] >= 50]
    if len(tinggi):
        p = float(tinggi["ara_besok"].mean())
        print(f"\nSkor >=50 : {len(tinggi):,} kejadian, {p*100:.2f}% diikuti ARA "
              f"({p/base:.0f}x base rate)")
        print(f"            Artinya {(1-p)*100:.0f}% TIDAK ARA — ini peningkatan peluang,")
        print(f"            bukan ramalan. Dari 10 sinyal, sekitar {p*10:.0f} yang kena.")
    sangat = P[P["skor"] >= 70]
    if len(sangat):
        p2 = float(sangat["ara_besok"].mean())
        print(f"\nSkor >=70 : {len(sangat):,} kejadian, {p2*100:.2f}% diikuti ARA "
              f"({p2/base:.0f}x base rate)")

    # Risiko sisi lain: berapa sering justru ARB?
    P["arb_besok"] = P.groupby("ticker")["ret"].shift(-1) <= -P["limit"] * 0.98
    for amb in (50, 70):
        sub = P[P["skor"] >= amb]
        if len(sub) > 50:
            pa = float(sub["ara_besok"].mean())
            pb = float(sub["arb_besok"].fillna(False).mean())
            print(f"\nSkor >={amb}: peluang ARA {pa*100:.2f}% vs ARB {pb*100:.2f}% "
                  f"(rasio {pa/pb:.1f}x)" if pb > 0 else
                  f"\nSkor >={amb}: peluang ARA {pa*100:.2f}%, ARB ~0%")

    P[["ticker", "skor", "ara_besok"]].to_csv(OUT_DIR / "ara_kalibrasi.csv")
    print(f"\nDisimpan: {OUT_DIR / 'ara_kalibrasi.csv'}")


if __name__ == "__main__":
    main()
