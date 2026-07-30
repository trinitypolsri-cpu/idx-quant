"""Scanner momentum intraday untuk scalping di IDX.

Berbeda dari screener harian: horizon di sini menit-ke-jam, jadi yang menentukan
untung-rugi bukan tren 6 bulan melainkan VWAP, volume relatif, ruang gerak sebelum
kena ARA, dan — yang paling sering diabaikan — GESEKAN FRAKSI HARGA.

Fraksi harga IDX bersifat absolut (Rp1 / 2 / 5 / 10 / 25), bukan persentase.
Akibatnya saham murah jauh lebih mahal untuk di-scalp:

    Harga Rp150   -> 1 tick = Rp1  = 0,67% per tick
    Harga Rp1.000 -> 1 tick = Rp5  = 0,50% per tick
    Harga Rp19.000-> 1 tick = Rp25 = 0,13% per tick

Dengan biaya beli+jual 0,40%, scalping saham Rp150 butuh gerak >1% hanya untuk
balik modal, sementara saham Rp19.000 cukup ~0,53%. Kolom `biaya_putaran` dan
`tick_untuk_bep` di bawah menghitung ini per emiten.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from .config import FEE_BUY, FEE_SELL, ar_limit, tick_size
from .providers import get_provider

SESSION_START = "09:00"


def vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    pv = (tp * df["volume"]).cumsum()
    vv = df["volume"].cumsum().replace(0, np.nan)
    return pv / vv


def analyse_intraday(ticker: str, bars: pd.DataFrame, prev_close: float | None,
                     opening_bars: int = 6) -> dict | None:
    """Hitung metrik scalping dari bar intraday satu sesi."""
    if bars is None or len(bars) < opening_bars + 2:
        return None

    b = bars.dropna(subset=["close"]).copy()
    if b.empty:
        return None

    price = float(b["close"].iloc[-1])
    if price <= 0:
        return None

    b["vwap"] = vwap(b)
    vw = float(b["vwap"].iloc[-1])

    o = float(b["open"].iloc[0])
    hi = float(b["high"].max())
    lo = float(b["low"].min())

    # Opening range (default 6 bar x 5 menit = 30 menit pertama)
    orh = float(b["high"].iloc[:opening_bars].max())
    orl = float(b["low"].iloc[:opening_bars].min())
    after = b.iloc[opening_bars:]
    orb_up = bool(len(after) and after["close"].max() > orh)
    orb_dn = bool(len(after) and after["close"].min() < orl)

    # Volume relatif: separuh sesi terakhir vs separuh awal
    half = max(1, len(b) // 2)
    v_early = float(b["volume"].iloc[:half].mean())
    v_late = float(b["volume"].iloc[half:].mean())
    rvol = (v_late / v_early) if v_early > 0 else np.nan

    # Rentang gerak intraday (proxy ATR pada bar intraday)
    tr = pd.concat([b["high"] - b["low"],
                    (b["high"] - b["close"].shift()).abs(),
                    (b["low"] - b["close"].shift()).abs()], axis=1).max(axis=1)
    atr_bar = float(tr.tail(14).mean())
    range_pct = (hi - lo) / price * 100

    # Momentum
    ret_sesi = (price / o - 1) * 100
    ret_30m = ((price / float(b["close"].iloc[-min(6, len(b))]) - 1) * 100
               if len(b) >= 6 else np.nan)
    vs_vwap = (price / vw - 1) * 100 if vw and not math.isnan(vw) else np.nan
    posisi_range = ((price - lo) / (hi - lo) * 100) if hi > lo else 50.0

    # --- Gesekan fraksi harga & biaya putaran ---
    tick = tick_size(price)
    tick_pct = tick / price * 100
    biaya_putaran = (FEE_BUY + FEE_SELL) * 100 + tick_pct      # % , sekali silang spread
    tick_bep = math.ceil(biaya_putaran / tick_pct) if tick_pct > 0 else None
    # Berapa kali biaya putaran tertutup oleh rentang harian yang khas?
    peluang = (range_pct / biaya_putaran) if biaya_putaran > 0 else 0

    # --- Ruang sebelum ARA / ARB ---
    ara_head = arb_head = None
    if prev_close and prev_close > 0:
        lim = ar_limit(prev_close) * 100
        move = (price / prev_close - 1) * 100
        ara_head = lim - move          # sisa ruang ke atas (%)
        arb_head = lim + move          # jarak ke batas bawah (%)

    return {
        "ticker": ticker,
        "harga": price,
        "ret_sesi": round(ret_sesi, 2),
        "ret_30m": None if pd.isna(ret_30m) else round(ret_30m, 2),
        "vs_vwap": None if pd.isna(vs_vwap) else round(vs_vwap, 2),
        "vwap": round(vw, 2) if vw and not math.isnan(vw) else None,
        "posisi_range": round(posisi_range, 0),
        "range_pct": round(range_pct, 2),
        "rvol": None if pd.isna(rvol) else round(rvol, 2),
        "orb_up": orb_up, "orb_dn": orb_dn,
        "or_high": round(orh, 2), "or_low": round(orl, 2),
        "atr_bar": round(atr_bar, 2),
        "tick": tick,
        "tick_pct": round(tick_pct, 3),
        "biaya_putaran": round(biaya_putaran, 2),
        "tick_untuk_bep": tick_bep,
        "peluang": round(peluang, 1),
        "ara_head": None if ara_head is None else round(ara_head, 1),
        "arb_head": None if arb_head is None else round(arb_head, 1),
        "n_bar": len(b),
    }


def skor_scalping(r: dict) -> float:
    """Skor 0-100. Menghargai momentum + volume + ruang gerak, menghukum gesekan."""
    if r is None:
        return 0.0
    s = 0.0
    # Momentum searah dan di atas VWAP
    s += min(max(r["ret_sesi"], -6), 6) * 3.2                       # -19..+19
    if r["vs_vwap"] is not None:
        s += min(max(r["vs_vwap"], -3), 3) * 3.0                    # -9..+9
    # Volume menguat di paruh kedua
    if r["rvol"]:
        s += min(r["rvol"], 3.0) * 6.0                              # 0..18
    # Breakout opening range
    if r["orb_up"]:
        s += 12
    if r["orb_dn"]:
        s -= 8
    # Dekat puncak rentang harian
    s += (r["posisi_range"] / 100) * 10                             # 0..10
    # Peluang: rentang harian relatif terhadap biaya
    s += min(r["peluang"], 6) * 3.5                                 # 0..21
    # Hukuman gesekan fraksi harga
    s -= r["tick_pct"] * 8                                          # murah = mahal
    # Hukuman bila ruang ke ARA menipis (tidak ada tempat untuk lari)
    if r["ara_head"] is not None and r["ara_head"] < 5:
        s -= (5 - max(r["ara_head"], 0)) * 3
    return round(max(0.0, min(100.0, s + 30)), 1)


def scan_scalping(tickers: list[str], prev_closes: dict[str, float] | None = None,
                  interval: str = "5m", rng: str = "1d", workers: int = 8,
                  provider=None) -> pd.DataFrame:
    """Ambil bar intraday untuk daftar ticker dan hitung metrik scalping."""
    prov = provider or get_provider()
    prev_closes = prev_closes or {}
    rows = []

    def job(t):
        try:
            bars = prov.intraday(t, interval=interval, rng=rng)
            if bars is None:
                return None
            return analyse_intraday(t, bars, prev_closes.get(t))
        except Exception:                                          # noqa: BLE001
            return None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in as_completed([ex.submit(job, t) for t in tickers]):
            r = fut.result()
            if r:
                r["skor"] = skor_scalping(r)
                rows.append(r)

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("skor", ascending=False).reset_index(drop=True)

    # Label keputusan yang bisa langsung dibaca
    def label(r):
        if r["ara_head"] is not None and r["ara_head"] < 3:
            return "MENTOK ARA"
        if r["biaya_putaran"] > 1.2:
            return "GESEKAN TINGGI"
        if r["orb_up"] and r["vs_vwap"] and r["vs_vwap"] > 0 and (r["rvol"] or 0) > 1.2:
            return "MOMENTUM KUAT"
        if r["vs_vwap"] is not None and r["vs_vwap"] > 0 and r["posisi_range"] > 70:
            return "DI ATAS VWAP"
        if r["vs_vwap"] is not None and r["vs_vwap"] < -1:
            return "DI BAWAH VWAP"
        return "NETRAL"

    df["label"] = df.apply(label, axis=1)
    return df


def scan_funnel(tickers: list[str], prev_closes: dict[str, float] | None = None,
                interval: str = "5m", top_deep: int = 20, workers: int = 8,
                provider=None) -> tuple[pd.DataFrame, dict]:
    """Corong dua tahap — memindai universe LEBIH LUAS dengan waktu lebih singkat.

    Tahap 1 (murah)  : endpoint spark, 20 ticker per request, hanya harga penutup.
                       Dipakai untuk memeringkat momentum intraday seluruh kandidat.
    Tahap 2 (mahal)  : endpoint chart OHLCV penuh, hanya untuk `top_deep` teratas,
                       supaya VWAP / opening range / RVol bisa dihitung.

    Alasan: spark tidak mengembalikan high/low/volume, jadi tidak bisa dipakai
    sendirian; tapi ia 20x lebih murah untuk menyaring.
    """
    import time as _t

    prov = provider or get_provider()
    prev_closes = prev_closes or {}
    stats = {"tahap1_ticker": len(tickers), "tahap2_ticker": 0,
             "detik_tahap1": 0.0, "detik_tahap2": 0.0, "metode": "chart-saja"}

    shortlist = tickers
    if hasattr(prov, "pulse"):
        t0 = _t.time()
        pulses = prov.pulse(tickers, interval=interval, rng="1d")
        stats["detik_tahap1"] = round(_t.time() - t0, 2)
        stats["metode"] = "spark + chart"
        rank = []
        for t, s in pulses.items():
            if len(s) < 4:
                continue
            ret = float(s.iloc[-1] / s.iloc[0] - 1) * 100
            # momentum paruh akhir: dorongan terkini, bukan gerak pembukaan saja
            half = max(1, len(s) // 2)
            late = float(s.iloc[-1] / s.iloc[half] - 1) * 100
            rng_pct = float((s.max() - s.min()) / s.iloc[-1]) * 100
            rank.append((t, abs(ret) * 0.5 + abs(late) * 1.0 + rng_pct * 0.5))
        if rank:
            rank.sort(key=lambda x: -x[1])
            shortlist = [t for t, _ in rank[:top_deep]]

    stats["tahap2_ticker"] = len(shortlist)
    t1 = _t.time()
    df = scan_scalping(shortlist, prev_closes=prev_closes, interval=interval,
                       workers=workers, provider=prov)
    stats["detik_tahap2"] = round(_t.time() - t1, 2)
    return df, stats
