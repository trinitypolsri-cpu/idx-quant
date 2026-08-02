"""Mean-variance optimisation + VaR untuk kandidat teratas IDX."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import portfolio as pf
from idxquant import setups as st
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)

MODAL = 1_000_000_000       # Rp1 miliar
TOP_N = 15


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    scan = st.scan(prep)
    liq = scan[scan["likuid"]]
    kandidat = list(liq.nlargest(TOP_N, "skor")["ticker"])

    px = pd.DataFrame({t: prep[t]["close"] for t in kandidat}).dropna()
    R = px.pct_change().dropna()
    harga = px.iloc[-1]

    print("=" * 92)
    print(f"OPTIMASI PORTOFOLIO — {len(kandidat)} kandidat skor tertinggi, "
          f"{len(R)} hari return")
    print("=" * 92)
    print(f"Modal: Rp{MODAL:,.0f}\n")

    hasil = {}
    for tuj, nama in (("sharpe", "Sharpe maksimum"),
                      ("min_var", "Varians minimum"),
                      ("risk_parity", "Risk parity")):
        r = pf.optimasi(R, tujuan=tuj, wmax=0.25)
        if not r:
            continue
        hasil[tuj] = r
        print(f"{nama:20} return {r['return_thn']*100:6.2f}%/thn  "
              f"vol {r['vol_thn']*100:5.2f}%  Sharpe {r['sharpe']:5.2f}  "
              f"n efektif {r['n_aset_efektif']:.1f}")

    # Pembanding: bobot sama rata
    w_eq = pd.Series(1 / len(kandidat), index=kandidat)
    S = pf.ledoit_wolf(R) * 244
    ret_eq = float(w_eq @ (R.mean().to_numpy() * 244))
    vol_eq = float(np.sqrt(w_eq @ S @ w_eq))
    from idxquant.config import RISK_FREE
    print(f"{'Sama rata (1/N)':20} return {ret_eq*100:6.2f}%/thn  "
          f"vol {vol_eq*100:5.2f}%  Sharpe {(ret_eq-RISK_FREE)/vol_eq:5.2f}  "
          f"n efektif {len(kandidat):.1f}")

    print("\nCatatan: 1/N sering mengalahkan mean-variance di luar sampel karena")
    print("optimasi sangat sensitif terhadap kesalahan estimasi return. Bandingkan")
    print("Sharpe-nya sebelum mempercayai bobot hasil optimasi.")

    # --- bobot ---
    best = hasil.get("sharpe")
    if best:
        print("\n--- Bobot Sharpe maksimum (batas 25% per emiten) ---")
        b = best["bobot"][best["bobot"] > 0.005]
        print((b * 100).round(2).to_string())

        print("\n--- Diterjemahkan ke lot IDX ---")
        lot = pf.ke_lot(b, harga, MODAL)
        print(lot.to_string(index=False))
        terpakai = lot["nilai"].sum() if len(lot) else 0
        print(f"\nTerpakai Rp{terpakai:,.0f} dari Rp{MODAL:,.0f} "
              f"({terpakai/MODAL*100:.1f}%) — sisanya kas karena pembulatan lot.")

    # --- VaR ---
    print("\n" + "=" * 92)
    print("PENGUKURAN RISIKO (VaR / CVaR harian)")
    print("=" * 92)
    if best:
        w = best["bobot"].reindex(R.columns).fillna(0)
        r_port = (R * w).sum(axis=1)
        tab = pf.ringkas_risiko(r_port, modal=MODAL)
        print(f"\nPortofolio Sharpe maksimum, modal Rp{MODAL:,.0f}:\n")
        print(tab.to_string(index=False))
        print(f"\n  Skewness {tab.attrs['skew']:+.2f}   "
              f"Kurtosis berlebih {tab.attrs['kurtosis']:+.2f}")
        if tab.attrs["kurtosis"] > 1:
            print("  Kurtosis tinggi = ekor gemuk. VaR normal MEREMEHKAN risiko;")
            print("  pakai angka Cornish-Fisher atau CVaR sebagai acuan.")

        # Bandingkan dengan IHSG
        rb = bench["close"].pct_change().reindex(r_port.index).dropna()
        print(f"\nPembanding IHSG:")
        print(f"  VaR 95% historis IHSG   : {pf.var_historis(rb)*100:.3f}%")
        print(f"  VaR 95% historis porto  : {pf.var_historis(r_port)*100:.3f}%")

    if best:
        best["bobot"].to_csv(OUT_DIR / "portfolio_bobot.csv")
        print(f"\nDisimpan: {OUT_DIR / 'portfolio_bobot.csv'}")


if __name__ == "__main__":
    main()
