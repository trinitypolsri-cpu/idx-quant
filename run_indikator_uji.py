"""Mana indikator & konsep SMC yang benar-benar punya edge di IDX?

Setiap sinyal diuji dengan cara yang sama seperti setup lain di proyek ini:
entry di OPEN bar berikutnya, biaya bolak-balik dipotong, dibandingkan dengan
base rate, lalu dikoreksi pengujian berganda (FDR).

Menguji ~25 sinyal sekaligus berarti ~1 akan lolos p<0,05 murni kebetulan.
Tanpa koreksi, daftar "indikator terbaik" hanyalah daftar keberuntungan.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import classic as cl
from idxquant import data as dl
from idxquant import setups as st
from idxquant import smc
from idxquant.altdata import fdr_bh
from idxquant.config import FEE_BUY, FEE_SELL, OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 215)

BIAYA = FEE_BUY + FEE_SELL + 2 * 0.0015     # ~0,70% bolak-balik
HORIZON = 21


def sinyal_bullish(d: pd.DataFrame) -> dict[str, pd.Series]:
    """Semua sinyal beli yang diuji. Semuanya dari bar tertutup."""
    c = d["close"]
    s = {}

    # --- klasik: momentum ---
    s["MACD cross naik"] = (d["macd_hist"] > 0) & (d["macd_hist"].shift(1) <= 0)
    s["MACD > 0 & naik"] = (d["macd"] > 0) & (d["macd"] > d["macd"].shift(1))
    s["Stoch keluar oversold"] = (d["stoch_k"] > 20) & (d["stoch_k"].shift(1) <= 20)
    s["Stoch K cross D"] = (d["stoch_k"] > d["stoch_d"]) & (d["stoch_k"].shift(1) <= d["stoch_d"].shift(1))
    s["CCI keluar -100"] = (d["cci"] > -100) & (d["cci"].shift(1) <= -100)
    s["CCI > 100"] = (d["cci"] > 100) & (d["cci"].shift(1) <= 100)
    s["RSI keluar 30"] = (d["rsi14"] > 30) & (d["rsi14"].shift(1) <= 30)

    # --- klasik: tren ---
    s["Supertrend balik naik"] = (d["st_arah"] > 0) & (d["st_arah"].shift(1) <= 0)
    s["PSAR balik naik"] = d["psar_naik"] & ~d["psar_naik"].shift(1).fillna(False)
    s["EMA10 cross EMA21"] = (d["ema10"] > d["ema21"]) & (d["ema10"].shift(1) <= d["ema21"].shift(1))
    s["Golden cross MA50/200"] = (d["ma50"] > d["ma200"]) & (d["ma50"].shift(1) <= d["ma200"].shift(1))
    s["ADX>25 & tren naik"] = (d["adx14"] > 25) & (c > d["ma50"]) & (d["adx14"].shift(1) <= 25)

    # --- Ichimoku ---
    s["Tembus atas kumo"] = d["di_atas_kumo"] & ~d["di_atas_kumo"].shift(1).fillna(False)
    s["Tenkan cross Kijun"] = (d["tenkan"] > d["kijun"]) & (d["tenkan"].shift(1) <= d["kijun"].shift(1))
    s["Kumo naik + harga atas"] = d["di_atas_kumo"] & (d["senkou_a"] > d["senkou_b"])

    # --- rentang ---
    s["ADR terpakai >150%"] = d["adr_terpakai"] > 150
    s["ADR terpakai <50%"] = d["adr_terpakai"] < 50

    # --- SMC / ICT ---
    s["FVG bullish"] = d["fvg_naik"]
    s["Order block bullish"] = d["ob_bullish"]
    s["BOS naik"] = d["bos_naik"]
    s["CHoCH naik"] = d["choch_naik"]
    s["Liquidity sweep bawah"] = d["sweep_bawah"]
    s["Sweep + discount"] = d["sweep_bawah"] & d["discount"]
    s["Setup ICT bullish"] = d["setup_ict_bullish"]
    s["Discount zone"] = d["discount"]

    return {k: v.fillna(False) for k, v in s.items()}


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    scan = st.scan(prep)
    likuid = set(scan[scan["likuid"]]["ticker"])

    print("Menghitung indikator klasik + SMC ...")
    hasil: dict[str, list] = {}
    n_emiten = 0
    base_semua = []

    for t, d in prep.items():
        if t not in likuid or d is None or len(d) < 320:
            continue
        x = cl.enrich(d)
        x = smc.enrich(x)
        for kol in ("rsi14", "ema10", "ema21", "ma50", "ma200", "adx14"):
            if kol not in x and kol in d:
                x[kol] = d[kol]
        sig = sinyal_bullish(x)

        o = x["open"].to_numpy()
        c = x["close"].to_numpy()
        n = len(x)
        # Return acuan seluruh bar (base rate)
        for i in range(n - HORIZON - 1):
            pass
        entry_all = o[1:]
        exit_all = c[min(HORIZON, n - 1):][:len(entry_all)]
        m = min(len(entry_all), len(exit_all))
        base_semua.append((exit_all[:m] / entry_all[:m] - 1) - BIAYA)

        for nama, v in sig.items():
            idx = np.flatnonzero(v.to_numpy())
            out = []
            for i in idx:
                e = i + 1
                if e >= n:
                    continue
                j = min(e + HORIZON - 1, n - 1)
                if not np.isfinite(o[e]) or o[e] <= 0:
                    continue
                out.append(c[j] / o[e] - 1 - BIAYA)
            if out:
                hasil.setdefault(nama, []).extend(out)
        n_emiten += 1

    base = np.concatenate(base_semua)
    base = base[np.isfinite(base)]
    mu_base = float(base.mean())

    print(f"\n{n_emiten} emiten likuid · base rate return {HORIZON} hari "
          f"(setelah biaya {BIAYA*100:.2f}%): {mu_base*100:+.3f}%\n")

    from scipy.stats import ttest_1samp
    rows = []
    for nama, v in hasil.items():
        a = np.array(v)
        a = a[np.isfinite(a)]
        if len(a) < 100:
            continue
        t_stat, p = ttest_1samp(a, mu_base)
        menang = float((a > 0).mean())
        kalah = a[a <= 0]
        menang_arr = a[a > 0]
        pf = (menang_arr.sum() / abs(kalah.sum())) if kalah.sum() != 0 else np.inf
        rows.append({
            "Sinyal": nama, "N": len(a),
            "Avg21h%": round(float(a.mean()) * 100, 3),
            "vs base": round((float(a.mean()) - mu_base) * 100, 3),
            "Menang%": round(menang * 100, 1),
            "PF": round(float(pf), 2),
            "t": round(float(t_stat), 2),
            "p": p,
        })

    df = pd.DataFrame(rows)
    df["lolos_fdr"] = fdr_bh(df["p"].to_numpy(), q=0.10)
    df["p"] = df["p"].map(lambda v: f"{v:.4f}")
    df = df.sort_values("vs base", ascending=False).reset_index(drop=True)

    print("=" * 110)
    print(f"HASIL — {len(df)} sinyal diuji, dibandingkan terhadap base rate")
    print("=" * 110)
    print()
    print(df.to_string(index=False))

    lolos = df[df["lolos_fdr"] & (df["vs base"] > 0)]
    print(f"\n  Unggul dari base rate DAN lolos koreksi FDR: {len(lolos)} dari {len(df)}")
    if len(lolos):
        print("\n--- YANG COCOK UNTUK IDX ---")
        print(lolos[["Sinyal", "N", "Avg21h%", "vs base", "Menang%", "PF", "t"]]
              .to_string(index=False))
    else:
        print("  TIDAK ADA yang lolos. Semua sinyal setara atau di bawah base rate.")

    buruk = df[df["lolos_fdr"] & (df["vs base"] < 0)]
    if len(buruk):
        print(f"\n--- JUSTRU MERUGIKAN (signifikan di bawah base rate): {len(buruk)} ---")
        print(buruk[["Sinyal", "N", "Avg21h%", "vs base", "t"]].to_string(index=False))

    df.to_csv(OUT_DIR / "indikator_uji.csv", index=False)
    print(f"\nDisimpan: {OUT_DIR / 'indikator_uji.csv'}")


if __name__ == "__main__":
    main()
