"""Indikator teknikal vektorisasi (pandas/numpy murni, tanpa TA-Lib)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def mulai(x: pd.Series) -> pd.Series:
    """Bar PERTAMA saat sebuah kondisi boolean mulai berlaku (transisi False->True).

    JANGAN tulis `x & ~x.shift(1).fillna(False)` secara langsung. `Series.shift()`
    pada dtype bool mengembalikan dtype OBJECT (karena harus menampung NaN), dan
    operator `~` pada object melakukan negasi bitwise integer: ~True menjadi -2,
    ~False menjadi -1. Keduanya truthy, sehingga ekspresi itu diam-diam menyusut
    menjadi `x` saja — kondisi yang persisten selama 73 bar akan terhitung 73 kali,
    bukan sekali. Tidak ada error yang muncul; hanya angkanya yang salah.
    """
    b = x.fillna(False).astype(bool)
    return b & ~b.shift(1, fill_value=False).astype(bool)


def selesai(x: pd.Series) -> pd.Series:
    """Bar pertama saat kondisi berhenti berlaku (transisi True->False)."""
    b = x.fillna(False).astype(bool)
    return (~b) & b.shift(1, fill_value=False).astype(bool)


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing — dipakai RSI/ATR/ADX agar cocok dengan Pine Script."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = rma(delta.clip(lower=0), n)
    loss = rma((-delta).clip(lower=0), n)
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100 * (gain > 0))


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift()
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = rma(true_range(df), n)
    plus_di = 100 * rma(pd.Series(plus_dm, index=df.index), n) / tr
    minus_di = 100 * rma(pd.Series(minus_dm, index=df.index), n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return rma(dx, n)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return mid - k * sd, mid, mid + k * sd


def keltner(df: pd.DataFrame, n: int = 20, k: float = 1.5):
    mid = ema(df["close"], n)
    rng = atr(df, n)
    return mid - k * rng, mid, mid + k * rng


def donchian(df: pd.DataFrame, n: int = 20):
    return df["low"].rolling(n, min_periods=n).min(), df["high"].rolling(n, min_periods=n).max()


def roc(s: pd.Series, n: int) -> pd.Series:
    return s.pct_change(n)


def obv(df: pd.DataFrame) -> pd.Series:
    sign = np.sign(df["close"].diff()).fillna(0)
    return (sign * df["volume"]).cumsum()


def turnover(df: pd.DataFrame) -> pd.Series:
    """Nilai transaksi harian (Rp)."""
    return df["close"] * df["volume"]


def realized_vol(close: pd.Series, n: int = 20, ann: int = 244) -> pd.Series:
    return close.pct_change().rolling(n, min_periods=n).std(ddof=0) * np.sqrt(ann)


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Tambahkan seluruh kolom indikator yang dipakai screener & backtest."""
    d = df.copy()
    c = d["close"]

    d["ma20"] = sma(c, 20)
    d["ma50"] = sma(c, 50)
    d["ma150"] = sma(c, 150)
    d["ma200"] = sma(c, 200)
    d["ema10"] = ema(c, 10)
    d["ema21"] = ema(c, 21)

    d["rsi14"] = rsi(c, 14)
    d["rsi2"] = rsi(c, 2)
    d["atr14"] = atr(d, 14)
    d["atr_pct"] = d["atr14"] / c
    d["adx14"] = adx(d, 14)

    bb_lo, bb_mid, bb_up = bollinger(c, 20, 2.0)
    kc_lo, _, kc_up = keltner(d, 20, 1.5)
    d["bb_lo"], d["bb_mid"], d["bb_up"] = bb_lo, bb_mid, bb_up
    d["bb_width"] = (bb_up - bb_lo) / bb_mid
    d["squeeze"] = (bb_lo > kc_lo) & (bb_up < kc_up)

    dc_lo, dc_hi = donchian(d, 20)
    d["dc20_lo"], d["dc20_hi"] = dc_lo, dc_hi
    d["dc55_hi"] = d["high"].rolling(55, min_periods=55).max()

    d["hi_52w"] = d["high"].rolling(244, min_periods=100).max()
    d["lo_52w"] = d["low"].rolling(244, min_periods=100).min()
    d["from_hi"] = c / d["hi_52w"] - 1
    d["from_lo"] = c / d["lo_52w"] - 1

    d["roc21"] = roc(c, 21)
    d["roc63"] = roc(c, 63)
    d["roc126"] = roc(c, 126)
    d["roc244"] = roc(c, 244)

    d["vol20"] = d["volume"].rolling(20, min_periods=20).mean()
    d["vol_ratio"] = d["volume"] / d["vol20"]
    d["turnover"] = turnover(d)
    d["turnover_med20"] = d["turnover"].rolling(20, min_periods=10).median()
    d["rvol"] = realized_vol(c, 20)
    d["obv"] = obv(d)
    d["obv_slope"] = d["obv"].diff(20) / d["vol20"].replace(0, np.nan)

    return d
