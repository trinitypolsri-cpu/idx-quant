"""Demo PnL: kalau benar-benar membeli saham yang direkomendasikan, hasilnya berapa?

Plus analisis regresi: faktor apa yang benar-benar menjelaskan return trade?
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import demo
from idxquant import setups as st
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 210)

MODAL = 100_000_000     # Rp100 juta


def rp(v):
    return f"Rp{v:,.0f}".replace(",", ".")


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    scan = st.scan(prep)
    likuid = set(scan[scan["likuid"]]["ticker"])

    print("=" * 100)
    print(f"DEMO PORTOFOLIO — modal {rp(MODAL)}, maks 5 posisi, biaya IDX penuh")
    print("=" * 100)

    hasil, ringkas = {}, []
    for setup in ["BaseBreakout", "FVGBullish", "KumoNaik", "TrendTemplate",
                  "MACDMomentum", "apa_saja"]:
        r = demo.simulasi(prep, bench, setup=setup, modal=MODAL,
                          maks_posisi=5, likuid=likuid)
        if not r or not r.get("metrik"):
            continue
        hasil[setup] = r
        m = r["metrik"]
        ringkas.append({
            "Setup": setup,
            "Nilai akhir": m["nilai_akhir"],
            "Laba/Rugi": m["laba_rugi"],
            "Return%": round(m["total_return"] * 100, 1),
            "CAGR%": round(m["cagr"] * 100, 2),
            "MaxDD%": round(m["maxdd"] * 100, 1),
            "Trade": m["n_trade"],
            "Hit%": round(m.get("hit_rate", np.nan) * 100, 1),
            "PF": round(m.get("profit_factor", np.nan), 2),
            "Hari": round(m.get("hari_rata", np.nan), 0),
        })

    tab = pd.DataFrame(ringkas).sort_values("Return%", ascending=False)
    print()
    print(tab.to_string(index=False))

    # Pembanding wajib: beli IHSG dan diamkan
    bc = bench["close"]
    eq0 = next(iter(hasil.values()))["ekuitas"]
    bh = bc.reindex(eq0.index).ffill()
    bh_ret = float(bh.iloc[-1] / bh.iloc[0] - 1)
    print(f"\n  Pembanding — beli IHSG dan diamkan: {bh_ret*100:+.1f}% "
          f"({rp(MODAL * (1 + bh_ret))})")
    print(f"  Periode: {eq0.index[0].date()} s/d {eq0.index[-1].date()}")

    terbaik = tab.iloc[0]
    print(f"\n  Terbaik: {terbaik['Setup']} -> {rp(terbaik['Nilai akhir'])} "
          f"({terbaik['Return%']:+.1f}%)")
    if terbaik["Return%"] < bh_ret * 100:
        print("  CATATAN: tidak ada satu pun yang mengalahkan beli-dan-diamkan IHSG.")

    # ---------- regresi: apa yang menjelaskan return trade? ----------
    print("\n" + "=" * 100)
    print("REGRESI — faktor apa yang menjelaskan return tiap trade?")
    print("=" * 100)

    semua = []
    for setup, r in hasil.items():
        tr = r["trade"]
        if tr.empty:
            continue
        for x in tr.itertuples():
            d = prep.get(x.ticker)
            if d is None or x.masuk not in d.index:
                continue
            b = d.loc[x.masuk]
            semua.append({
                "ret": x.ret, "setup": setup, "hari": x.hari,
                "atr_pct": float(b.get("atr_pct", np.nan)),
                "rsi": float(b.get("rsi14", np.nan)),
                "adx": float(b.get("adx14", np.nan)),
                "roc63": float(b.get("roc63", np.nan)),
                "dari_hi": float(b.get("from_hi", np.nan)),
                "vol_ratio": float(b.get("vol_ratio", np.nan)),
                "harga": float(b.get("close", np.nan)),
            })
    R = pd.DataFrame(semua).replace([np.inf, -np.inf], np.nan).dropna()
    if len(R) < 60:
        print(f"  Hanya {len(R)} trade — terlalu sedikit untuk regresi.")
    else:
        from sklearn.linear_model import LinearRegression
        from sklearn.preprocessing import StandardScaler
        fitur = ["atr_pct", "rsi", "adx", "roc63", "dari_hi", "vol_ratio", "hari"]
        X = StandardScaler().fit_transform(R[fitur])
        y = R["ret"].to_numpy()
        lr = LinearRegression().fit(X, y)
        r2 = lr.score(X, y)

        # t-stat manual (sklearn tidak menyediakannya)
        n, k = X.shape
        resid = y - lr.predict(X)
        s2 = (resid ** 2).sum() / (n - k - 1)
        Xd = np.column_stack([np.ones(n), X])
        se = np.sqrt(np.diag(s2 * np.linalg.pinv(Xd.T @ Xd)))[1:]
        t = lr.coef_ / se
        from scipy.stats import t as tdist
        p = 2 * (1 - tdist.cdf(np.abs(t), n - k - 1))

        out = pd.DataFrame({
            "Faktor": fitur,
            "Koef (per 1 SD)": (lr.coef_ * 100).round(3),
            "t": t.round(2),
            "p": p.round(4),
        }).sort_values("t", key=abs, ascending=False)
        print(f"\n  N = {len(R)} trade · R-squared = {r2:.4f}\n")
        print(out.to_string(index=False))
        print(f"\n  R-squared {r2:.4f} artinya faktor-faktor ini menjelaskan hanya "
              f"{r2*100:.1f}% ragam return.")
        if r2 < 0.10:
            print("  Sisanya — lebih dari 90% — adalah hal yang tidak terukur di sini.")
            print("  Itu ciri khas pasar: hasil tiap trade sebagian besar acak.")
        sig = out[out["p"] < 0.05]
        print(f"\n  Faktor signifikan (p<0,05): "
              f"{', '.join(sig['Faktor']) if len(sig) else 'TIDAK ADA'}")

    for s, r in hasil.items():
        if not r["trade"].empty:
            r["trade"].to_csv(OUT_DIR / f"demo_{s}.csv", index=False)
    tab.to_csv(OUT_DIR / "demo_ringkasan.csv", index=False)
    print(f"\nDisimpan: demo_ringkasan.csv + rincian trade per setup")


if __name__ == "__main__":
    main()
