"""Uji apakah metode kuantitatif benar-benar memperkuat, bukan sekadar terdengar canggih.

Membandingkan tiga penilai untuk memprediksi ARA besok:
  1. Skor heuristik  — bobot yang saya tetapkan manual
  2. Regresi logistik — fitur harga/volume saja
  3. Regresi logistik + mikrostruktur (spread, Amihud, Kyle, OFI, CMF)

Kalau (3) tidak mengalahkan (1), maka menambah kerumitan itu sia-sia dan harus
dikatakan apa adanya.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import ara as ar
from idxquant import data as dl
from idxquant import microstructure as ms
from idxquant import probability as pr
from idxquant import setups as st
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 210)

DASAR = ["rvol", "rvol5", "pos_close", "ret", "ret5", "ret20",
         "dari_hi60", "atr_pct"]
MIKRO = ["spread_cs", "amihud", "kyle", "ofi", "cmf", "ad_slope", "akum_diam"]


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)

    print("Menghitung mikrostruktur untuk tiap emiten ...")
    baris = []
    for t, d in prep.items():
        if d is None or len(d) < 320:
            continue
        a = ar.tandai_ara(d)
        m = ms.enrich(d)
        x = a.join(m[MIKRO], how="left")
        x["ticker"] = t
        x["ara_kemarin_i"] = x["ara_kemarin"].astype(int)
        x["dekat_ara_i"] = x["dekat_ara"].astype(int)
        baris.append(x)
    P = pd.concat(baris).dropna(subset=["ara_besok"])
    P = P.replace([np.inf, -np.inf], np.nan)
    P["ara_besok"] = P["ara_besok"].astype(int)
    P = P.sort_index()

    print(f"\n{len(P):,} observasi · {P['ticker'].nunique()} emiten · "
          f"base rate {P['ara_besok'].mean()*100:.3f}%")

    F1 = DASAR + ["ara_kemarin_i", "dekat_ara_i"]
    F2 = F1 + MIKRO

    print("\n" + "=" * 92)
    print("MODEL 1 — regresi logistik, fitur harga & volume")
    print("=" * 92)
    r1 = pr.uji_temporal(P, F1, "ara_besok")
    if "error" in r1:
        print(r1["error"]); return
    print(f"  latih {r1['n_latih']:,}  uji {r1['n_uji']:,}  "
          f"base uji {r1['base_uji']*100:.3f}%")
    print(f"  AUC {r1['auc']:.4f}   Brier {r1['brier']:.6f}   "
          f"lift desil-1 {r1['lift_desil1']:.1f}x")

    print("\n" + "=" * 92)
    print("MODEL 2 — ditambah fitur mikrostruktur")
    print("=" * 92)
    r2 = pr.uji_temporal(P, F2, "ara_besok")
    print(f"  AUC {r2['auc']:.4f}   Brier {r2['brier']:.6f}   "
          f"lift desil-1 {r2['lift_desil1']:.1f}x")

    lo, hi = pr.bootstrap_ci(r2["y_uji"], r2["p_uji"])
    print(f"  Selang kepercayaan 95% AUC: [{lo:.4f}, {hi:.4f}]")

    # Skor heuristik pada potongan uji yang sama persis (posisional, bukan label)
    te = P.iloc[r2["split_uji"]:]
    assert len(te) == len(r2["y_uji"]), "potongan uji tidak sinkron"
    rv = te["rvol"].fillna(0)
    heur = (te["ara_kemarin"].fillna(False) * 30
            + np.where(rv > 3.0, 20, np.where(rv > 2.0, 12, 0))
            + (te["pos_close"].fillna(0) > 0.90) * 18
            + te["dekat_ara"].fillna(False) * 20
            + (te["dari_hi60"].fillna(-1) > -0.02) * 8
            + (te["atr_pct"].fillna(0) > 0.07) * 4).clip(upper=100).to_numpy()

    print("\n" + "=" * 92)
    print("PERBANDINGAN — pada data uji yang sama persis")
    print("=" * 92)
    tab = pr.bandingkan(r2["y_uji"], {
        "Heuristik (bobot manual)": heur,
        "Logistik (harga+volume)": r1["p_uji"],
        "Logistik + mikrostruktur": r2["p_uji"],
    })
    print()
    print(tab.to_string(index=False))

    menang = tab.iloc[0]["Penilai"]
    selisih = tab.iloc[0]["AUC"] - tab.iloc[-1]["AUC"]
    print(f"\nTerbaik: {menang}  (selisih AUC {selisih:+.4f} dari terburuk)")
    if selisih < 0.01:
        print("Selisihnya kecil — kerumitan tambahan tidak terbayar.")

    print("\n--- Kalibrasi SEBELUM koreksi (mentah dari class_weight='balanced') ---")
    print(r2["kalibrasi_mentah"].to_string())
    print(f"\n  Brier mentah {r2['brier_mentah']:.6f}")
    print("  Angka 'diramal%' jauh di atas 'terjadi%' — probabilitasnya tidak bermakna.")

    print("\n--- Kalibrasi SETELAH regresi isotonik ---")
    print(r2["kalibrasi"].to_string())
    print(f"\n  Brier terkalibrasi {r2['brier']:.6f} "
          f"(turun {(1 - r2['brier']/r2['brier_mentah'])*100:.1f}%)")
    print(f"  AUC tidak rusak: {r2['auc_mentah']:.4f} -> {r2['auc']:.4f}")
    print("  Kolom 'selisih' mendekati nol = probabilitas kini dapat dipercaya.")

    print("\n--- Fitur paling berpengaruh ---")
    print(r2["koefisien"].head(12).to_string(index=False))
    print("\nodds_ratio > 1 menaikkan peluang ARA, < 1 menurunkan.")

    r2["koefisien"].to_csv(OUT_DIR / "model_koefisien.csv", index=False)
    tab.to_csv(OUT_DIR / "model_perbandingan.csv", index=False)
    print(f"\nDisimpan: model_koefisien.csv, model_perbandingan.csv")


if __name__ == "__main__":
    main()
