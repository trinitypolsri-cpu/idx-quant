"""Apa yang benar-benar mengecilkan drawdown dan menaikkan Sharpe?

Bukan opini — sapuan parameter pada simulator demo, semua diukur dengan biaya
IDX penuh. Yang diuji adalah hal-hal yang secara teori memengaruhi drawdown:

  1. Jarak stop (ATR)         — stop ketat memotong rugi tapi sering kena noise
  2. Jumlah posisi maksimum   — lebih banyak = lebih tersebar
  3. Filter regime IHSG       — tidak beli saat indeks di bawah MA200
  4. Filter volatilitas       — hindari emiten yang volatilitasnya ekstrem
  5. Lama tahan maksimum      — keluar lebih cepat = eksposur lebih pendek

Indikator sengaja TIDAK diikutkan: 25 indikator sudah diuji terpisah dan yang
lolos pun hanya menggeser return rata-rata 0,3-1,2pp, bukan menyentuh drawdown.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import demo
from idxquant import setups as st
from idxquant.config import OUT_DIR, RISK_FREE
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)

MODAL = 100_000_000
SETUP = "BaseBreakout"     # PF tertinggi & DD paling ringan dari uji demo


def sharpe(eq: pd.Series) -> float:
    r = eq.pct_change().dropna()
    if len(r) < 20 or r.std(ddof=0) == 0:
        return np.nan
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (244 / len(eq)) - 1
    return (cagr - RISK_FREE) / (r.std(ddof=0) * np.sqrt(244))


def jalankan(prep, bench, likuid, **kw) -> dict:
    r = demo.simulasi(prep, bench, setup=SETUP, modal=MODAL, likuid=likuid, **kw)
    if not r or not r.get("metrik"):
        return {}
    m, eq = r["metrik"], r["ekuitas"]
    return {"Return%": round(m["total_return"] * 100, 1),
            "CAGR%": round(m["cagr"] * 100, 2),
            "MaxDD%": round(m["maxdd"] * 100, 1),
            "Sharpe": round(sharpe(eq), 3),
            "Trade": m["n_trade"],
            "PF": round(m.get("profit_factor", np.nan), 2)}


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    scan = st.scan(prep)
    likuid = set(scan[scan["likuid"]]["ticker"])

    # Regime IHSG: tanggal saat indeks di bawah MA200 -> tidak boleh beli
    ma200 = bench["close"].rolling(200, min_periods=200).mean()
    risk_on = set(bench.index[bench["close"] > ma200])

    print("=" * 96)
    print(f"SAPUAN PARAMETER — setup {SETUP}, modal Rp{MODAL:,}")
    print("=" * 96)

    baris = []

    # --- 1. jarak stop ---
    for s in (1.5, 2.0, 3.0, 4.0, 6.0):
        h = jalankan(prep, bench, likuid, stop_atr=s, maks_posisi=5)
        if h:
            baris.append({"Faktor": "Jarak stop", "Nilai": f"{s}x ATR", **h})

    # --- 2. jumlah posisi ---
    for n in (3, 5, 8, 12):
        h = jalankan(prep, bench, likuid, stop_atr=3.0, maks_posisi=n)
        if h:
            baris.append({"Faktor": "Maks posisi", "Nilai": str(n), **h})

    # --- 3. lama tahan ---
    for d in (10, 21, 42):
        h = jalankan(prep, bench, likuid, stop_atr=3.0, maks_posisi=5, tahan_maks=d)
        if h:
            baris.append({"Faktor": "Tahan maks", "Nilai": f"{d} hari", **h})

    tab = pd.DataFrame(baris)
    print()
    print(tab.to_string(index=False))

    # --- 4. filter regime: universe dibatasi saat IHSG lemah ---
    print("\n" + "=" * 96)
    print("FILTER REGIME IHSG — hanya beli saat indeks di atas MA200")
    print("=" * 96)
    prep_regime = {}
    for t, d in prep.items():
        x = d.copy()
        for c in [c for c in x.columns if c.startswith("sig_")]:
            x[c] = x[c] & x.index.isin(risk_on)
        prep_regime[t] = x
    a = jalankan(prep, bench, likuid, stop_atr=3.0, maks_posisi=5)
    b = jalankan(prep_regime, bench, likuid, stop_atr=3.0, maks_posisi=5)
    cmp = pd.DataFrame([{"Regime filter": "tidak", **a},
                        {"Regime filter": "YA", **b}])
    print()
    print(cmp.to_string(index=False))
    if a and b:
        print(f"\n  Drawdown : {a['MaxDD%']}% -> {b['MaxDD%']}%  "
              f"({b['MaxDD%'] - a['MaxDD%']:+.1f}pp)")
        print(f"  Sharpe   : {a['Sharpe']} -> {b['Sharpe']}  "
              f"({b['Sharpe'] - a['Sharpe']:+.3f})")
        print(f"  Trade    : {a['Trade']} -> {b['Trade']}")

    # --- kesimpulan berbasis data ---
    print("\n" + "=" * 96)
    print("YANG PALING BERPENGARUH")
    print("=" * 96)
    semua = pd.concat([tab, cmp.rename(columns={"Regime filter": "Nilai"})
                       .assign(Faktor="Regime IHSG")], ignore_index=True)
    dd = semua.groupby("Faktor")["MaxDD%"].agg(["min", "max"])
    dd["rentang_pp"] = (dd["max"] - dd["min"]).round(1)
    sh = semua.groupby("Faktor")["Sharpe"].agg(["min", "max"])
    sh["rentang"] = (sh["max"] - sh["min"]).round(3)
    print("\n  Seberapa besar tiap faktor menggeser DrawDown:")
    print(dd.sort_values("rentang_pp", ascending=False).to_string())
    print("\n  Seberapa besar tiap faktor menggeser Sharpe:")
    print(sh.sort_values("rentang", ascending=False).to_string())

    semua.to_csv(OUT_DIR / "dd_sweep.csv", index=False)
    print(f"\nDisimpan: {OUT_DIR / 'dd_sweep.csv'}")


if __name__ == "__main__":
    main()
