"""Apakah penyamaan risiko berbasis ATR mengalahkan bobot sama rata?"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import backtest as bt
from idxquant import data as dl
from idxquant import setups as st
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)

    print("=" * 96)
    print("BOBOT SAMA RATA vs PENYAMAAN RISIKO ATR")
    print("=" * 96)

    hasil, ringkas = {}, []
    for label, kw in (("Sama rata", dict(bobot_atr=False)),
                      ("Penyamaan risiko ATR", dict(bobot_atr=True))):
        r = bt.run_rotation(prep, bench, top_n=10, regime_filter=True, **kw)
        hasil[label] = r
        m = r["metrics"]
        tr = r["trades"]
        # Kerapuhan: seberapa besar PnL bergantung pada segelintir posisi
        konsentrasi = np.nan
        if len(tr):
            top10 = tr.nlargest(10, "pnl")["pnl"].sum()
            konsentrasi = top10 / tr["pnl"].sum() * 100 if tr["pnl"].sum() else np.nan
        ringkas.append({
            "Bobot": label,
            "CAGR%": round(m["CAGR"] * 100, 2),
            "Vol%": round(m["Vol"] * 100, 2),
            "MaxDD%": round(m["MaxDD"] * 100, 2),
            "Sharpe": round(m["Sharpe"], 3),
            "Calmar": round(m["Calmar"], 2) if pd.notna(m["Calmar"]) else None,
            "Trade": m.get("Trades", 0),
            "HitRate%": round(m.get("HitRate", np.nan) * 100, 1),
            "PF": round(m.get("ProfitFactor", np.nan), 2),
            "Top10/PnL%": round(konsentrasi, 0) if pd.notna(konsentrasi) else None,
        })

    tab = pd.DataFrame(ringkas)
    print()
    print(tab.to_string(index=False))

    a, b = hasil["Sama rata"]["metrics"], hasil["Penyamaan risiko ATR"]["metrics"]
    print("\n--- Perbandingan langsung ---")
    for k, nama in (("CAGR", "CAGR"), ("Vol", "Volatilitas"),
                    ("MaxDD", "Drawdown maks"), ("Sharpe", "Sharpe")):
        d = b[k] - a[k]
        arah = "lebih baik" if (
            (k in ("CAGR", "Sharpe") and d > 0) or
            (k in ("Vol",) and d < 0) or
            (k == "MaxDD" and d > 0)) else "lebih buruk"
        satuan = "" if k == "Sharpe" else "pp"
        print(f"  {nama:16} {d*100 if k!='Sharpe' else d:+7.2f}{satuan}  ({arah})")

    # Rasio konsentrasi HANYA bermakna bila total PnL positif. Bila totalnya
    # negatif, rasionya berbalik tanda dan angka "turun" justru berarti sistem
    # merugi — bukan lebih tersebar. Jangan dibandingkan lintas kondisi itu.
    ka, kb = tab.iloc[0]["Top10/PnL%"], tab.iloc[1]["Top10/PnL%"]
    pnl_pos = [hasil[l]["trades"]["pnl"].sum() > 0 for l in
               ("Sama rata", "Penyamaan risiko ATR")]
    print(f"\n  Konsentrasi PnL pada 10 trade terbaik: {ka:.0f}% vs {kb:.0f}%")
    if not all(pnl_pos):
        print("  TIDAK DAPAT DIBANDINGKAN: salah satu strategi total PnL-nya negatif,")
        print("  sehingga rasio ini berbalik tanda dan kehilangan arti.")
    elif kb < ka:
        print("  Turun = laba lebih tersebar.")
    else:
        print("  Naik = justru lebih terkonsentrasi.")

    tab.to_csv(OUT_DIR / "risk_uji.csv", index=False)
    print(f"\nDisimpan: {OUT_DIR / 'risk_uji.csv'}")


if __name__ == "__main__":
    main()
