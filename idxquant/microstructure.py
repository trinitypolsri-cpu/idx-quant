"""Mikrostruktur pasar dari OHLCV — menaksir spread, dampak harga, dan tekanan order.

Bid/offer sesungguhnya butuh data order book level-2 yang berlisensi. Tapi literatur
mikrostruktur menyediakan estimator yang dirancang justru untuk situasi ini: menaksir
karakteristik order flow HANYA dari harga dan volume.

Yang diimplementasikan:

  Roll (1984)            spread efektif dari autokovarians perubahan harga
  Corwin-Schultz (2012)  spread dari rasio high-low dua hari — lebih akurat dari Roll
  Amihud (2002)          iliquiditas: berapa harga bergerak per rupiah transaksi
  Kyle (1985) lambda     dampak harga per unit order flow tak seimbang
  OFI                    ketidakseimbangan arus order, proksi tekanan beli/jual
  A/D, CMF, OBV          jejak akumulasi/distribusi klasik

Semua ini PROKSI. Ia menaksir apa yang biasanya terlihat di broker summary, tetapi
tidak bisa memberi tahu broker mana yang membeli. Kalau nanti berlangganan data
berlisensi, ganti proksi ini dengan angka sesungguhnya.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ------------------------------------------------------------------ spread
def roll_spread(close: pd.Series, n: int = 20) -> pd.Series:
    """Spread efektif Roll = 2*sqrt(-cov(dP_t, dP_t-1)).

    Bila autokovariansnya positif (tren kuat), estimator tidak terdefinisi —
    dikembalikan NaN, bukan angka palsu.
    """
    dp = close.diff()
    cov = dp.rolling(n).cov(dp.shift(1))
    s = 2 * np.sqrt((-cov).clip(lower=0))
    return (s / close).where(cov < 0)          # fraksi harga


def corwin_schultz(df: pd.DataFrame) -> pd.Series:
    """Estimator spread Corwin-Schultz dari high-low dua hari berurutan.

    Lebih andal daripada Roll karena tidak bergantung pada tanda autokovarians.
    """
    h, l = df["high"], df["low"]
    hi2 = pd.concat([h, h.shift(1)], axis=1).max(axis=1)
    lo2 = pd.concat([l, l.shift(1)], axis=1).min(axis=1)

    beta = (np.log(h / l) ** 2) + (np.log(h.shift(1) / l.shift(1)) ** 2)
    gamma = np.log(hi2 / lo2) ** 2

    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    alpha = alpha.clip(lower=0)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    return s.replace([np.inf, -np.inf], np.nan)


# ------------------------------------------------------------------ dampak harga
def amihud(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Iliquiditas Amihud: |return| per miliar rupiah nilai transaksi.

    Semakin tinggi, semakin mudah harga digerakkan sejumlah uang tertentu —
    justru ciri saham yang gampang 'digoreng'.
    """
    ret = df["close"].pct_change().abs()
    nilai = (df["close"] * df["volume"]).replace(0, np.nan)
    return (ret / nilai * 1e9).rolling(n).mean()


def kyle_lambda(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Lambda Kyle: koefisien regresi perubahan harga terhadap order flow bertanda.

    Dihitung bergulir memakai rumus tertutup, jadi tetap cepat untuk ratusan emiten.
    """
    dp = df["close"].diff()
    arah = np.sign(dp).replace(0, np.nan).ffill().fillna(0)
    flow = arah * np.sqrt(df["volume"].clip(lower=0))
    cov = dp.rolling(n).cov(flow)
    var = flow.rolling(n).var()
    return (cov / var.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


# ------------------------------------------------------------------ tekanan order
def order_flow_imbalance(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Proksi ketidakseimbangan arus order dari posisi penutupan dalam rentang bar.

    Bar yang ditutup dekat high berarti pembeli agresif menguasai sesi; dekat low
    berarti penjual. Dibobot volume, lalu dijumlah bergulir.
    """
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    # -1 (semua jual) .. +1 (semua beli)
    arah = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng
    signed = arah * df["volume"]
    return signed.rolling(n).sum() / df["volume"].rolling(n).sum().replace(0, np.nan)


def accumulation_distribution(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng
    return (clv.fillna(0) * df["volume"]).cumsum()


def chaikin_money_flow(df: pd.DataFrame, n: int = 20) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng
    mfv = clv.fillna(0) * df["volume"]
    return mfv.rolling(n).sum() / df["volume"].rolling(n).sum().replace(0, np.nan)


def akumulasi_diam(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Proksi 'akumulasi diam-diam': volume naik, harga TIDAK naik banyak.

    Pola khas penyerapan — pihak besar menampung tanpa mengangkat harga, sehingga
    usaha (volume) besar tapi hasil (gerak harga) kecil, dengan CMF tetap positif.
    """
    vol_z = (df["volume"] - df["volume"].rolling(60).mean()) / \
            df["volume"].rolling(60).std(ddof=0).replace(0, np.nan)
    gerak = df["close"].pct_change(n).abs()
    cmf = chaikin_money_flow(df, n)
    # tinggi bila: volume di atas normal, harga stagnan, aliran uang positif
    return (vol_z.clip(lower=0) * (1 / (1 + gerak * 20)) * cmf.clip(lower=0))


# ------------------------------------------------------------------ gabungan
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["spread_roll"] = roll_spread(d["close"])
    d["spread_cs"] = corwin_schultz(d)
    d["amihud"] = amihud(d)
    d["kyle"] = kyle_lambda(d)
    d["ofi"] = order_flow_imbalance(d)
    d["ad_line"] = accumulation_distribution(d)
    d["ad_slope"] = d["ad_line"].diff(20) / d["volume"].rolling(20).mean().replace(0, np.nan)
    d["cmf"] = chaikin_money_flow(d)
    d["akum_diam"] = akumulasi_diam(d)
    return d


def ringkas(ticker: str, df: pd.DataFrame) -> dict:
    d = enrich(df)
    r = d.iloc[-1]
    f = lambda v, m=1: None if pd.isna(v) else round(float(v) * m, 4)   # noqa: E731
    return {
        "ticker": ticker,
        "harga": float(r["close"]),
        "spread_cs_pct": f(r["spread_cs"], 100),
        "spread_roll_pct": f(r["spread_roll"], 100),
        "amihud": f(r["amihud"]),
        "kyle": f(r["kyle"]),
        "ofi": f(r["ofi"]),
        "cmf": f(r["cmf"]),
        "ad_slope": f(r["ad_slope"]),
        "akum_diam": f(r["akum_diam"]),
    }
