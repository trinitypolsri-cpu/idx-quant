"""Mesin backtest: event study per setup + rotasi portofolio dengan biaya IDX."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (FEE_BUY, FEE_SELL, LOT_SIZE, RISK_FREE, SLIPPAGE,
                     TRADING_DAYS)
from .setups import liquid_mask

RT_COST = FEE_BUY + FEE_SELL + 2 * SLIPPAGE   # biaya bolak-balik ~0.70%


# ---------------------------------------------------------------------------
# Metrik
# ---------------------------------------------------------------------------

def metrics(equity: pd.Series, exposure: pd.Series | None = None) -> dict:
    eq = equity.dropna()
    if len(eq) < 2:
        return {}
    ret = eq.pct_change().dropna()
    years = len(eq) / TRADING_DAYS
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1
    vol = ret.std(ddof=0) * np.sqrt(TRADING_DAYS)
    sharpe = (cagr - RISK_FREE) / vol if vol > 0 else np.nan
    dd = eq / eq.cummax() - 1
    maxdd = dd.min()
    downside = ret[ret < 0].std(ddof=0) * np.sqrt(TRADING_DAYS)
    out = {
        "CAGR": cagr,
        "Vol": vol,
        "Sharpe": sharpe,
        "Sortino": (cagr - RISK_FREE) / downside if downside > 0 else np.nan,
        "MaxDD": maxdd,
        "Calmar": cagr / abs(maxdd) if maxdd < 0 else np.nan,
        "TotalReturn": eq.iloc[-1] / eq.iloc[0] - 1,
        "Years": years,
    }
    if exposure is not None:
        out["Exposure"] = exposure.reindex(eq.index).fillna(0).mean()
    return out


# ---------------------------------------------------------------------------
# Event study — validasi tiap setup secara terpisah
# ---------------------------------------------------------------------------

def event_study(prepared: dict[str, pd.DataFrame], setup: str,
                horizons=(5, 10, 21), require_liquid: bool = True,
                cost: float = RT_COST) -> dict:
    """Return forward setelah sinyal. Entry di OPEN bar berikutnya (tanpa look-ahead)."""
    col = f"sig_{setup}"
    recs = []
    for t, d in prepared.items():
        if col not in d:
            continue
        sig = d[col].fillna(False)
        if require_liquid:
            sig = sig & liquid_mask(d).fillna(False)
        idx = np.flatnonzero(sig.to_numpy())
        if idx.size == 0:
            continue
        o = d["open"].to_numpy()
        c = d["close"].to_numpy()
        n = len(d)
        for i in idx:
            entry_i = i + 1
            if entry_i >= n:
                continue
            entry = o[entry_i]
            if not np.isfinite(entry) or entry <= 0:
                continue
            rec = {"ticker": t, "date": d.index[i]}
            for h in horizons:
                j = min(entry_i + h - 1, n - 1)
                rec[f"fwd{h}"] = c[j] / entry - 1 - cost
            recs.append(rec)

    if not recs:
        return {"setup": setup, "n": 0}

    df = pd.DataFrame(recs)
    res = {"setup": setup, "n": len(df), "n_ticker": df["ticker"].nunique()}
    for h in horizons:
        r = df[f"fwd{h}"].dropna()
        wins, losses = r[r > 0], r[r <= 0]
        res[f"avg{h}"] = r.mean()
        res[f"med{h}"] = r.median()
        res[f"win{h}"] = (r > 0).mean()
        res[f"pf{h}"] = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else np.inf
        # t-stat sederhana; sinyal saling tumpang tindih jadi ini batas atas keyakinan
        res[f"t{h}"] = r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 1 else np.nan
    res["_trades"] = df
    return res


# ---------------------------------------------------------------------------
# Backtest rotasi portofolio
# ---------------------------------------------------------------------------

def build_panels(prepared: dict[str, pd.DataFrame], fields: list[str]) -> dict[str, pd.DataFrame]:
    return {f: pd.DataFrame({t: d[f] for t, d in prepared.items()}).sort_index()
            for f in fields}


def run_rotation(prepared: dict[str, pd.DataFrame], bench: pd.DataFrame,
                 top_n: int = 10, rebalance_dow: int = 4, start: str | None = None,
                 regime_filter: bool = True, stop_atr: float = 2.5,
                 capital: float = 1_000_000_000, require_trend: bool = True,
                 bobot_atr: bool = False, verbose: bool = True) -> dict:
    """Long-only, rebalance mingguan, bobot sama, top-N skor momentum.

    - Keputusan pakai data bar t, eksekusi di OPEN bar t+1.
    - Stop loss trailing berbasis ATR dicek pada LOW harian.
    - Regime filter: IHSG di bawah MA200 -> tidak ada posisi baru.
    """
    fields = ["open", "high", "low", "close", "atr14", "ma200", "ma50",
              "roc21", "roc63", "roc126", "roc244", "atr_pct", "turnover_med20"]
    P = build_panels(prepared, fields)
    dates = P["close"].index
    if start:
        dates = dates[dates >= pd.Timestamp(start)]
    dates = dates[dates.isin(bench.index)]

    bench_c = bench["close"].reindex(dates).ffill()
    bench_ma200 = bench["close"].rolling(200, min_periods=200).mean().reindex(dates).ffill()

    # Skor cross-section harian (rank persentil, dihitung sekali secara vektor)
    ranks = {c: P[c].reindex(dates).rank(axis=1, pct=True) for c in
             ("roc21", "roc63", "roc126", "roc244")}
    vol_rank = P["atr_pct"].reindex(dates).rank(axis=1, pct=True)
    score = (0.15 * ranks["roc21"] + 0.30 * ranks["roc63"]
             + 0.35 * ranks["roc126"] + 0.20 * ranks["roc244"])
    score = 0.80 * score + 0.20 * (1 - vol_rank)

    eligible = (P["turnover_med20"].reindex(dates) >= 5e9) & (P["close"].reindex(dates) >= 100)
    if require_trend:
        eligible &= (P["close"].reindex(dates) > P["ma200"].reindex(dates))
        eligible &= (P["ma50"].reindex(dates) > P["ma200"].reindex(dates))

    o, h_, l_, c_ = (P["open"].reindex(dates), P["high"].reindex(dates),
                     P["low"].reindex(dates), P["close"].reindex(dates))
    atr_ = P["atr14"].reindex(dates)

    cash = capital
    pos: dict[str, dict] = {}          # ticker -> {shares, entry, stop, date}
    equity, expo, trades = [], [], []
    pending_buys: list[str] = []
    pending_sells: list[str] = []

    for i, dt in enumerate(dates):
        px_open = o.loc[dt]
        px_close = c_.loc[dt]

        # --- Eksekusi order yang diputuskan kemarin, di harga OPEN hari ini ---
        for t in pending_sells:
            if t in pos and np.isfinite(px_open.get(t, np.nan)):
                p = px_open[t] * (1 - SLIPPAGE)
                proceeds = pos[t]["shares"] * p * (1 - FEE_SELL)
                cost_basis = pos[t]["shares"] * pos[t]["entry"]
                trades.append({"ticker": t, "entry_date": pos[t]["date"], "exit_date": dt,
                               "entry": pos[t]["entry"], "exit": p,
                               "pnl": proceeds - cost_basis,
                               "ret": proceeds / cost_basis - 1,
                               "reason": pos[t].get("reason", "rebalance"),
                               "hari": (dt - pos[t]["date"]).days})
                cash += proceeds
                del pos[t]
        pending_sells = []

        if pending_buys:
            total_nilai = cash + sum(pos[t]["shares"] * px_open.get(t, pos[t]["entry"])
                                     for t in pos)
            if bobot_atr:
                # Penyamaan risiko: porsi berbanding terbalik dengan ATR%, sehingga
                # tiap posisi menyumbang risiko setara — bukan rupiah setara.
                from .risk import bobot_atr as _hitung_bobot
                ap = P["atr_pct"].loc[dt].reindex(pending_buys).dropna()
                w = _hitung_bobot(ap, wmaks=1.0 / max(top_n, 1) * 2.0)
                slot_map = {t: total_nilai * float(w.get(t, 1.0 / max(top_n, 1)))
                            for t in pending_buys}
            else:
                slot_map = {t: total_nilai / max(top_n, 1) for t in pending_buys}
            for t in pending_buys:
                slot_value = slot_map.get(t, total_nilai / max(top_n, 1))
                if t in pos or not np.isfinite(px_open.get(t, np.nan)):
                    continue
                p = px_open[t] * (1 + SLIPPAGE)
                lots = int(min(slot_value, cash * 0.98) // (p * LOT_SIZE * (1 + FEE_BUY)))
                if lots < 1:
                    continue
                shares = lots * LOT_SIZE
                outlay = shares * p * (1 + FEE_BUY)
                if outlay > cash:
                    continue
                cash -= outlay
                a = atr_.loc[dt].get(t, np.nan)
                pos[t] = {"shares": shares, "entry": p, "date": dt,
                          "stop": p - stop_atr * a if np.isfinite(a) else p * 0.85,
                          "reason": "rebalance"}
            pending_buys = []

        # --- Cek stop loss pada LOW hari ini; eksekusi jual besok ---
        lows = l_.loc[dt]
        for t, p_ in list(pos.items()):
            a = atr_.loc[dt].get(t, np.nan)
            if np.isfinite(a) and np.isfinite(px_close.get(t, np.nan)):
                p_["stop"] = max(p_["stop"], px_close[t] - stop_atr * a)   # trailing
            if np.isfinite(lows.get(t, np.nan)) and lows[t] <= p_["stop"]:
                p_["reason"] = "stop"
                pending_sells.append(t)

        # --- Mark-to-market ---
        mv = sum(p_["shares"] * px_close.get(t, p_["entry"]) for t, p_ in pos.items())
        total = cash + mv
        equity.append(total)
        expo.append(mv / total if total > 0 else 0)

        # --- Keputusan rebalance (bar tertutup) ---
        if dt.dayofweek == rebalance_dow and i < len(dates) - 1:
            risk_on = (not regime_filter) or (
                np.isfinite(bench_ma200.loc[dt]) and bench_c.loc[dt] > bench_ma200.loc[dt])
            s = score.loc[dt].where(eligible.loc[dt]).dropna()
            target = list(s.nlargest(top_n).index) if risk_on else []
            for t in list(pos):
                if t not in target and t not in pending_sells:
                    pos[t]["reason"] = "rebalance"
                    pending_sells.append(t)
            pending_buys = [t for t in target if t not in pos]

    eq = pd.Series(equity, index=dates, name="equity")
    ex = pd.Series(expo, index=dates, name="exposure")
    tr = pd.DataFrame(trades)

    m = metrics(eq, ex)
    if len(tr):
        wins, losses = tr[tr["ret"] > 0], tr[tr["ret"] <= 0]
        m.update({
            "Trades": len(tr),
            "HitRate": len(wins) / len(tr),
            "AvgWin": wins["ret"].mean() if len(wins) else np.nan,
            "AvgLoss": losses["ret"].mean() if len(losses) else np.nan,
            "ProfitFactor": (wins["pnl"].sum() / abs(losses["pnl"].sum()))
                            if len(losses) and losses["pnl"].sum() != 0 else np.inf,
            "AvgHoldDays": tr["hari"].mean(),
            "StopExits": (tr["reason"] == "stop").mean(),
        })
    return {"equity": eq, "exposure": ex, "trades": tr, "metrics": m,
            "bench": bench_c, "dates": dates}


def buy_hold(bench: pd.DataFrame, dates: pd.Index, capital: float = 1_000_000_000) -> pd.Series:
    c = bench["close"].reindex(dates).ffill()
    return (capital * c / c.iloc[0]).rename("bench_equity")
