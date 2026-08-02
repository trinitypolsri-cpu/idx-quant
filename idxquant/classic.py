"""Indikator teknikal klasik — MACD, Stochastic, PSAR, Supertrend, CCI, ADR,
Ichimoku, dan Fibonacci retracement.

Semua memakai Wilder smoothing di tempat yang semestinya agar angkanya cocok
dengan TradingView, sehingga sinyal di aplikasi dan di chart Anda sama.

Catatan yang berlaku untuk seluruh modul ini: indikator hanyalah transformasi
harga. Menambah banyak indikator TIDAK menambah informasi baru — semuanya
diturunkan dari OHLCV yang sama. Yang menentukan berguna atau tidak adalah
pengujian, bukan jumlahnya. Karena itu ada `run_indikator_uji.py` yang mengukur
mana yang benar-benar punya edge di IDX.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import atr, ema, rma, sma


# ------------------------------------------------------------------ momentum
def macd(close: pd.Series, cepat: int = 12, lambat: int = 26, sinyal: int = 9):
    """MACD, garis sinyal, dan histogram."""
    m = ema(close, cepat) - ema(close, lambat)
    s = ema(m, sinyal)
    return m, s, m - s


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3, halus: int = 3):
    """Stochastic %K (dihaluskan) dan %D."""
    ll = df["low"].rolling(k, min_periods=k).min()
    hh = df["high"].rolling(k, min_periods=k).max()
    raw = 100 * (df["close"] - ll) / (hh - ll).replace(0, np.nan)
    kk = raw.rolling(halus, min_periods=halus).mean()
    return kk, kk.rolling(d, min_periods=d).mean()


def cci(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Commodity Channel Index."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ma = tp.rolling(n, min_periods=n).mean()
    mad = tp.rolling(n, min_periods=n).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - ma) / (0.015 * mad.replace(0, np.nan))


# ------------------------------------------------------------------ tren
def supertrend(df: pd.DataFrame, n: int = 10, mult: float = 3.0):
    """Supertrend: garis dan arah (+1 naik, -1 turun).

    Memakai logika carry-forward baku — pita hanya boleh mengetat searah tren,
    tidak melonggar, sehingga garisnya tidak berayun mengikuti noise.
    """
    a = atr(df, n)
    hl2 = (df["high"] + df["low"]) / 2
    atas, bawah = hl2 + mult * a, hl2 - mult * a

    c = df["close"].to_numpy()
    ua, ub = atas.to_numpy(), bawah.to_numpy()
    fa = np.full(len(df), np.nan)
    fb = np.full(len(df), np.nan)
    arah = np.ones(len(df))

    for i in range(1, len(df)):
        if np.isnan(ua[i]) or np.isnan(ub[i]):
            continue
        fa[i] = ua[i] if (np.isnan(fa[i - 1]) or ua[i] < fa[i - 1]
                          or c[i - 1] > fa[i - 1]) else fa[i - 1]
        fb[i] = ub[i] if (np.isnan(fb[i - 1]) or ub[i] > fb[i - 1]
                          or c[i - 1] < fb[i - 1]) else fb[i - 1]
        if not np.isnan(fa[i - 1]) and c[i] > fa[i]:
            arah[i] = 1
        elif not np.isnan(fb[i - 1]) and c[i] < fb[i]:
            arah[i] = -1
        else:
            arah[i] = arah[i - 1]

    garis = np.where(arah > 0, fb, fa)
    return (pd.Series(garis, index=df.index),
            pd.Series(arah, index=df.index))


def parabolic_sar(df: pd.DataFrame, af0: float = 0.02, step: float = 0.02,
                  af_maks: float = 0.2) -> pd.Series:
    """Parabolic SAR (Wilder). Iteratif — tidak bisa divektorkan sepenuhnya."""
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(df)
    sar = np.full(n, np.nan)
    if n < 3:
        return pd.Series(sar, index=df.index)

    naik = h[1] > h[0]
    sar[0] = l[0] if naik else h[0]
    ep = h[0] if naik else l[0]
    af = af0

    for i in range(1, n):
        sar[i] = sar[i - 1] + af * (ep - sar[i - 1])
        if naik:
            sar[i] = min(sar[i], l[i - 1], l[max(i - 2, 0)])
            if h[i] > ep:
                ep, af = h[i], min(af + step, af_maks)
            if l[i] < sar[i]:                       # balik arah
                naik, sar[i], ep, af = False, ep, l[i], af0
        else:
            sar[i] = max(sar[i], h[i - 1], h[max(i - 2, 0)])
            if l[i] < ep:
                ep, af = l[i], min(af + step, af_maks)
            if h[i] > sar[i]:
                naik, sar[i], ep, af = True, ep, h[i], af0
    return pd.Series(sar, index=df.index)


def ichimoku(df: pd.DataFrame, tenkan: int = 9, kijun: int = 26,
             senkou: int = 52, geser: int = 26):
    """Ichimoku Kinko Hyo lengkap.

    Awan (kumo) digeser MAJU 26 bar — itu memang sifatnya, bukan look-ahead:
    nilai hari ini diproyeksikan ke depan, dan bar masa depan belum dipakai.
    """
    def garis_tengah(n):
        return (df["high"].rolling(n, min_periods=n).max()
                + df["low"].rolling(n, min_periods=n).min()) / 2

    t = garis_tengah(tenkan)
    k = garis_tengah(kijun)
    a = ((t + k) / 2).shift(geser)
    b = garis_tengah(senkou).shift(geser)
    # Chikou digeser MUNDUR — hanya untuk visual; JANGAN dipakai sebagai sinyal
    # karena membandingkannya dengan harga sekarang membocorkan masa depan.
    ch = df["close"].shift(-geser)
    return t, k, a, b, ch


# ------------------------------------------------------------------ rentang
def adr(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Average Daily Range sebagai persentase harga."""
    return ((df["high"] - df["low"]) / df["close"]).rolling(n, min_periods=n).mean() * 100


def posisi_adr(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Berapa persen ADR yang sudah terpakai hari ini — >100% berarti hari ekstrem."""
    hari_ini = (df["high"] - df["low"]) / df["close"] * 100
    return hari_ini / adr(df, n).replace(0, np.nan) * 100


# ------------------------------------------------------------------ Fibonacci
FIB = (0.236, 0.382, 0.5, 0.618, 0.786)


def fibonacci_retracement(df: pd.DataFrame, lookback: int = 60) -> dict:
    """Level retracement dari ayunan tertinggi/terendah `lookback` bar terakhir."""
    d = df.tail(lookback)
    if len(d) < 10:
        return {}
    hi, lo = float(d["high"].max()), float(d["low"].min())
    if hi <= lo:
        return {}
    naik = d["high"].idxmax() > d["low"].idxmin()      # ayunan terakhir naik?
    rng = hi - lo
    level = {}
    for f in FIB:
        level[f"fib_{f:.3f}"] = (hi - rng * f) if naik else (lo + rng * f)
    level["swing_high"], level["swing_low"] = hi, lo
    level["arah_swing"] = "naik" if naik else "turun"
    px = float(d["close"].iloc[-1])
    level["posisi_dalam_swing"] = (px - lo) / rng * 100
    return level


# ------------------------------------------------------------------ gabungan
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d["close"]

    m, s, h = macd(c)
    d["macd"], d["macd_sinyal"], d["macd_hist"] = m, s, h
    d["macd_cross"] = np.sign(h) != np.sign(h.shift(1))

    kk, dd = stochastic(d)
    d["stoch_k"], d["stoch_d"] = kk, dd

    d["cci"] = cci(d)

    st_garis, st_arah = supertrend(d)
    d["supertrend"], d["st_arah"] = st_garis, st_arah

    d["psar"] = parabolic_sar(d)
    d["psar_naik"] = c > d["psar"]

    t, k, a, b, _ = ichimoku(d)
    d["tenkan"], d["kijun"] = t, k
    d["senkou_a"], d["senkou_b"] = a, b
    d["di_atas_kumo"] = (c > a) & (c > b)
    d["di_bawah_kumo"] = (c < a) & (c < b)
    d["tebal_kumo"] = (a - b).abs() / c

    d["adr"] = adr(d)
    d["adr_terpakai"] = posisi_adr(d)

    return d
