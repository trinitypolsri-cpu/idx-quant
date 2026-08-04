"""Manajemen risiko berbasis ATR — penyamaan risiko, trailing stop, filter volatilitas.

Ini bukan indikator tambahan. Sesi riset menunjukkan masalah terbesar sistem ini
bukan kekurangan sinyal, melainkan SEBARAN HASIL yang rapuh:

  - 10 trade terbaik dari 498 menyumbang 269% total PnL; sisanya net negatif
  - Kurtosis harian 9-10 (ekor sangat gemuk)
  - Bobot sama rata membuat saham ber-ATR 8% menyumbang risiko 4x lipat
    dibanding saham ber-ATR 2%, padahal porsi rupiahnya sama

Penyamaan risiko berbasis ATR menyerang persoalan ketiga secara langsung: alih-alih
menyamakan RUPIAH per posisi, ia menyamakan RISIKO per posisi. Efeknya bukan
menaikkan return, melainkan mengurangi ketergantungan pada segelintir posisi.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import LOT_SIZE


def bobot_atr(atr_pct: pd.Series, wmaks: float = 0.25,
              wmin: float = 0.02) -> pd.Series:
    """Bobot berbanding terbalik dengan volatilitas (inverse-volatility weighting).

    Saham ber-ATR 8% mendapat porsi seperempat dari saham ber-ATR 2%, sehingga
    kontribusi risikonya setara. Dibatasi wmin/wmaks agar tidak terkonsentrasi
    pada satu emiten paling tenang.
    """
    a = atr_pct.replace([np.inf, -np.inf], np.nan).dropna()
    a = a[a > 0]
    if a.empty:
        return pd.Series(dtype=float)
    w = 1.0 / a
    w = w / w.sum()
    for _ in range(50):                       # iterasi agar batas tetap terpenuhi
        w = w.clip(wmin, wmaks)
        s = w.sum()
        if abs(s - 1) < 1e-9:
            break
        w = w / s
    return w / w.sum()


def ukuran_risiko(modal: float, entry: float, stop: float,
                  risiko_pct: float = 0.01) -> dict:
    """Berapa lot agar kerugian saat stop = `risiko_pct` dari modal."""
    r = entry - stop
    if r <= 0 or entry <= 0:
        return {}
    lot = int((modal * risiko_pct / r) // LOT_SIZE)
    return {"lot": lot, "lembar": lot * LOT_SIZE,
            "nilai": round(lot * LOT_SIZE * entry),
            "risiko_rp": round(lot * LOT_SIZE * r),
            "porsi_modal%": round(lot * LOT_SIZE * entry / modal * 100, 1)}


def chandelier_exit(df: pd.DataFrame, n: int = 22, mult: float = 3.0) -> pd.Series:
    """Trailing stop dari TERTINGGI n hari dikurangi mult x ATR.

    Berbeda dari trailing stop biasa yang mengikuti harga penutupan, chandelier
    menggantung dari puncak — sehingga tidak mudah tersentuh koreksi normal dalam
    tren yang masih utuh.
    """
    from .indicators import atr
    return df["high"].rolling(n, min_periods=n).max() - mult * atr(df, n)


def regime_volatilitas(df: pd.DataFrame, n: int = 20,
                       lookback: int = 252) -> pd.Series:
    """Persentil volatilitas saat ini terhadap sejarahnya sendiri (0-100).

    Nilai >90 berarti volatilitas sedang ekstrem — historisnya periode seperti ini
    memperlebar stop dan memperkecil ukuran posisi yang wajar.
    """
    from .indicators import atr
    a = atr(df, n) / df["close"]
    return a.rolling(lookback, min_periods=60).rank(pct=True) * 100


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["chandelier"] = chandelier_exit(d)
    d["vol_persentil"] = regime_volatilitas(d)
    return d
