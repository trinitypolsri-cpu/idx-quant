"""Pipeline utama: unduh data IDX -> screening -> event study -> backtest rotasi."""

from __future__ import annotations

import sys
import warnings

import pandas as pd

from idxquant import backtest as bt
from idxquant import data as dl
from idxquant import setups as st
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

RANGE = "5y"
REFRESH = "--refresh" in sys.argv


def pct(x, d=1):
    return "n/a" if pd.isna(x) else f"{x*100:.{d}f}%"


def main():
    print("=" * 78)
    print("IDX QUANT PIPELINE — Bursa Efek Indonesia")
    print("=" * 78)

    print(f"\n[1/5] Mengunduh data ({len(CANDIDATES)} kandidat + IHSG, range={RANGE}) ...")
    bench = dl.load(BENCHMARK, rng=RANGE, use_cache=not REFRESH)
    if bench is None:
        raise SystemExit("Gagal mengambil data IHSG.")
    print(f"  IHSG: {len(bench)} bar, {bench.index[0].date()} -> {bench.index[-1].date()}")

    data = dl.load_many(CANDIDATES, rng=RANGE, use_cache=not REFRESH)

    print(f"\n[2/5] Menghitung indikator & sinyal untuk {len(data)} saham ...")
    prep = st.prepare(data, bench)

    print("\n[3/5] Screening cross-section (bar terakhir) ...")
    scan = st.scan(prep)
    scan.to_csv(OUT_DIR / "screening.csv", index=False)
    liq = scan[scan["likuid"]]
    print(f"  {len(scan)} saham dipindai, {len(liq)} lolos filter likuiditas "
          f"(harga>=Rp100 & median turnover>=Rp5 M/hari)")
    print(f"  Di atas MA200: {liq['di_atas_ma200'].mean()*100:.1f}% dari saham likuid")

    print("\n  --- TOP 15 SKOR MOMENTUM (likuid) ---")
    cols = ["ticker", "sektor", "close", "skor", "ret_3m", "ret_6m", "ret_12m",
            "from_hi", "adx14", "rsi14", "n_sinyal"]
    top = liq.head(15)[cols].copy()
    for c in ("ret_3m", "ret_6m", "ret_12m", "from_hi"):
        top[c] = top[c].map(lambda v: pct(v, 1))
    for c in ("close", "adx14", "rsi14"):
        top[c] = top[c].round(1)
    print(top.to_string(index=False))

    print("\n  --- SINYAL AKTIF HARI INI ---")
    sig_cols = [c for c in scan.columns if c.startswith("sig_")]
    for c in sig_cols:
        hits = liq[liq[c]].sort_values("skor", ascending=False)
        name = c.replace("sig_", "")
        if len(hits):
            names = ", ".join(f"{r.ticker}({r.skor:.0f})" for r in hits.head(12).itertuples())
            print(f"  {name:<16} {len(hits):>3} : {names}")
        else:
            print(f"  {name:<16} {0:>3} : -")

    print("\n[4/5] Event study tiap setup (5 tahun, entry di open bar berikutnya, "
          "biaya bolak-balik 0,70%) ...")
    rows = []
    for name in list(st.SETUPS) + ["RSLeader"]:
        r = bt.event_study(prep, name)
        if r.get("n", 0) == 0:
            continue
        rows.append({
            "Setup": name, "N": r["n"], "Saham": r["n_ticker"],
            "Avg5d": pct(r["avg5"], 2), "Win5d": pct(r["win5"], 0),
            "Avg10d": pct(r["avg10"], 2), "Win10d": pct(r["win10"], 0),
            "Avg21d": pct(r["avg21"], 2), "Win21d": pct(r["win21"], 0),
            "PF21d": round(r["pf21"], 2), "t21": round(r["t21"], 2),
        })
    ev = pd.DataFrame(rows)
    ev.to_csv(OUT_DIR / "event_study.csv", index=False)
    print(ev.to_string(index=False))

    print("\n[5/5] Backtest rotasi portofolio (top-10, rebalance mingguan) ...")
    variants = {
        "Momentum + regime filter": dict(regime_filter=True, require_trend=True),
        "Momentum tanpa regime filter": dict(regime_filter=False, require_trend=True),
        "Momentum longgar (tanpa syarat MA200)": dict(regime_filter=True, require_trend=False),
    }
    results = {}
    summary = []
    for label, kw in variants.items():
        res = bt.run_rotation(prep, bench, top_n=10, **kw)
        results[label] = res
        m = res["metrics"]
        summary.append({
            "Strategi": label, "CAGR": pct(m["CAGR"]), "Vol": pct(m["Vol"]),
            "Sharpe": round(m["Sharpe"], 2), "MaxDD": pct(m["MaxDD"]),
            "Calmar": round(m["Calmar"], 2) if pd.notna(m["Calmar"]) else "n/a",
            "Exposure": pct(m["Exposure"], 0), "Trade": m.get("Trades", 0),
            "HitRate": pct(m.get("HitRate", float("nan")), 0),
            "PF": round(m.get("ProfitFactor", float("nan")), 2),
            "Hold(hr)": round(m.get("AvgHoldDays", float("nan")), 0),
        })

    base = results["Momentum + regime filter"]
    bh = bt.buy_hold(bench, base["dates"])
    mb = bt.metrics(bh)
    summary.append({
        "Strategi": "IHSG Buy & Hold", "CAGR": pct(mb["CAGR"]), "Vol": pct(mb["Vol"]),
        "Sharpe": round(mb["Sharpe"], 2), "MaxDD": pct(mb["MaxDD"]),
        "Calmar": round(mb["Calmar"], 2) if pd.notna(mb["Calmar"]) else "n/a",
        "Exposure": "100%", "Trade": 1, "HitRate": "-", "PF": "-", "Hold(hr)": "-",
    })
    sm = pd.DataFrame(summary)
    sm.to_csv(OUT_DIR / "backtest_summary.csv", index=False)
    print(sm.to_string(index=False))

    # Split in-sample / out-of-sample (uji kestabilan, bukan tuning)
    dates = base["dates"]
    split = dates[len(dates) // 2]
    print(f"\n  --- Uji kestabilan: paruh-1 vs paruh-2 (split {split.date()}) ---")
    oos = []
    for label in ("Momentum + regime filter",):
        eq = results[label]["equity"]
        for part, seg in (("Paruh-1", eq[eq.index <= split]), ("Paruh-2", eq[eq.index > split])):
            m = bt.metrics(seg)
            bseg = bh[seg.index]
            mb2 = bt.metrics(bseg)
            oos.append({"Periode": part,
                        "Mulai": seg.index[0].date(), "Selesai": seg.index[-1].date(),
                        "Strategi CAGR": pct(m["CAGR"]), "Strategi MaxDD": pct(m["MaxDD"]),
                        "Strategi Sharpe": round(m["Sharpe"], 2),
                        "IHSG CAGR": pct(mb2["CAGR"]), "IHSG MaxDD": pct(mb2["MaxDD"])})
    print(pd.DataFrame(oos).to_string(index=False))

    # Simpan kurva ekuitas
    curve = pd.DataFrame({"strategi": base["equity"], "ihsg": bh,
                          "exposure": base["exposure"]})
    curve.to_csv(OUT_DIR / "equity_curve.csv")
    base["trades"].to_csv(OUT_DIR / "trades.csv", index=False)

    print(f"\nOutput tersimpan di: {OUT_DIR}")
    print("  screening.csv, event_study.csv, backtest_summary.csv, equity_curve.csv, trades.csv")


if __name__ == "__main__":
    main()
