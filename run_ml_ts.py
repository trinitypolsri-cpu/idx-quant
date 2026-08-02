"""Random Forest vs logistik, plus deteksi lompatan & memori pasar."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import ara as ar
from idxquant import data as dl
from idxquant import microstructure as ms
from idxquant import probability as pr
from idxquant import setups as st
from idxquant import timeseries as ts
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 210)

DASAR = ["rvol", "rvol5", "pos_close", "ret", "ret5", "ret20", "dari_hi60", "atr_pct"]
MIKRO = ["spread_cs", "amihud", "kyle", "ofi", "cmf", "ad_slope", "akum_diam"]


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)

    print("Menyiapkan fitur ...")
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
    P = pd.concat(baris).dropna(subset=["ara_besok"]).replace([np.inf, -np.inf], np.nan)
    P["ara_besok"] = P["ara_besok"].astype(int)
    P = P.sort_index()
    F = DASAR + ["ara_kemarin_i", "dekat_ara_i"] + MIKRO

    # ---------------- Random Forest ----------------
    print("\n" + "=" * 92)
    print("RANDOM FOREST vs REGRESI LOGISTIK")
    print("=" * 92)

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.isotonic import IsotonicRegression

    n = int(len(P) * 0.5); nk = n + int(len(P) * 0.2)
    tr, ka, te = P.iloc[:n], P.iloc[n:nk], P.iloc[nk:]
    Xtr = tr[F].fillna(tr[F].median()); ytr = tr["ara_besok"].to_numpy()
    Xka = ka[F].fillna(tr[F].median()); yka = ka["ara_besok"].to_numpy()
    Xte = te[F].fillna(tr[F].median()); yte = te["ara_besok"].to_numpy()

    rf = RandomForestClassifier(
        n_estimators=300, max_depth=8, min_samples_leaf=50,
        class_weight="balanced_subsample", n_jobs=-1, random_state=7)
    rf.fit(Xtr, ytr)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
    iso.fit(rf.predict_proba(Xka)[:, 1], yka)
    p_rf = iso.predict(rf.predict_proba(Xte)[:, 1])

    r_log = pr.uji_temporal(P, F, "ara_besok")
    p_log = r_log["p_uji"]

    base = float(yte.mean())
    tab = pr.bandingkan(yte, {"Random Forest": p_rf, "Logistik": p_log})
    print(f"\nbase rate uji {base*100:.3f}%   n uji {len(yte):,}\n")
    print(tab.to_string(index=False))
    lo, hi = pr.bootstrap_ci(yte, p_rf)
    print(f"\nAUC Random Forest 95% CI: [{lo:.4f}, {hi:.4f}]")
    print(f"Brier RF {pr.brier(yte, p_rf):.6f}  vs  logistik {r_log['brier']:.6f}")

    imp = (pd.DataFrame({"fitur": F, "penting": rf.feature_importances_})
           .sort_values("penting", ascending=False).head(10))
    print("\n--- Fitur terpenting menurut Random Forest ---")
    print(imp.to_string(index=False))

    # ---------------- Lompatan & memori ----------------
    print("\n" + "=" * 92)
    print("LOMPATAN HARGA & MEMORI PASAR (Lee-Mykland, Hurst, Ljung-Box)")
    print("=" * 92)

    scan = st.scan(prep)
    liq = list(scan[scan["likuid"]]["ticker"])
    rows = [ts.ringkas(t, prep[t]) for t in liq if prep.get(t) is not None]
    T = pd.DataFrame([r for r in rows if r])

    print(f"\n{len(T)} emiten likuid:\n")
    show = T.nlargest(10, "lompatan_per_thn")[
        ["ticker", "vol_ewma%", "n_lompatan", "lompatan_per_thn",
         "lompatan_naik", "lompatan_turun", "porsi_var_lompatan%", "hurst", "ljung_p"]]
    print(show.to_string(index=False))

    print(f"\nRata-rata lompatan per tahun : {T['lompatan_per_thn'].mean():.1f}")
    print(f"Lompatan naik vs turun       : {T['lompatan_naik'].sum():,} vs "
          f"{T['lompatan_turun'].sum():,}")
    print(f"Median Hurst                 : {T['hurst'].median():.3f}")
    h = T["hurst"].median()
    if h < 0.45:
        print("  -> di bawah 0,5: harga cenderung BALIK ARAH (mean reverting)")
    elif h > 0.55:
        print("  -> di atas 0,5: tren cenderung BERLANJUT (persisten)")
    else:
        print("  -> mendekati 0,5: mendekati jalan acak, memori lemah")

    sig = int((T["ljung_p"] < 0.05).sum())
    print(f"Autokorelasi signifikan      : {sig}/{len(T)} emiten (Ljung-Box p<0,05)")
    print("  Ljung-Box signifikan berarti ADA struktur yang bisa dieksploitasi;")
    print("  tidak signifikan berarti return-nya mendekati tak terprediksi.")

    # IHSG sendiri
    print("\n--- IHSG ---")
    ih = ts.ringkas("IHSG", bench)
    for k, v in ih.items():
        print(f"  {k:24} {v}")

    T.to_csv(OUT_DIR / "timeseries.csv", index=False)
    tab.to_csv(OUT_DIR / "ml_perbandingan.csv", index=False)
    print(f"\nDisimpan: timeseries.csv, ml_perbandingan.csv")


if __name__ == "__main__":
    main()
