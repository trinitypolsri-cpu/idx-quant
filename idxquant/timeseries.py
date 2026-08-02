"""Deret waktu & proses stokastik: lompatan, volatilitas, dan memori pasar.

"Ketidaksinambungan pasar" dalam istilah statistik adalah JUMP — perubahan harga
yang terlalu besar untuk dijelaskan oleh difusi normal. Uji Lee-Mykland (2008)
memisahkan lompatan dari volatilitas biasa dengan menormalkan return terhadap
volatilitas lokal, lalu membandingkannya dengan distribusi nilai ekstrem Gumbel.

Ini penting untuk IDX karena ARA/ARB menciptakan diskontinuitas struktural: harga
tidak bergerak kontinu, ia melompat lalu berhenti di batas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ------------------------------------------------------------------ volatilitas
def ewma_vol(r: pd.Series, lam: float = 0.94, ann: int = 244) -> pd.Series:
    """Volatilitas EWMA gaya RiskMetrics — pengganti ringan untuk GARCH."""
    var = r.pow(2).ewm(alpha=1 - lam, adjust=False).mean()
    return np.sqrt(var * ann)


def realized_bipower(r: pd.Series, n: int = 20) -> pd.Series:
    """Bipower variation: penaksir volatilitas yang KEBAL terhadap lompatan.

    Selisihnya dengan realized variance biasa memberi ukuran kontribusi lompatan.
    """
    mu1 = np.sqrt(2 / np.pi)
    bp = (r.abs() * r.abs().shift(1)).rolling(n).sum() / (mu1 ** 2)
    return np.sqrt(bp / n)


def porsi_lompatan(r: pd.Series, n: int = 20) -> pd.Series:
    """Berapa bagian varians yang berasal dari lompatan, bukan difusi."""
    rv = r.pow(2).rolling(n).sum()
    mu1 = np.sqrt(2 / np.pi)
    bv = (r.abs() * r.abs().shift(1)).rolling(n).sum() / (mu1 ** 2)
    return ((rv - bv) / rv.replace(0, np.nan)).clip(0, 1)


# ------------------------------------------------------------------ lompatan
def lee_mykland(close: pd.Series, k: int = 20, alpha: float = 0.01) -> pd.DataFrame:
    """Uji lompatan Lee-Mykland dengan ambang nilai ekstrem Gumbel."""
    r = np.log(close).diff()
    mu1 = np.sqrt(2 / np.pi)
    sigma = (r.abs() * r.abs().shift(1)).rolling(k).mean() / (mu1 ** 2)
    sigma = np.sqrt(sigma.replace(0, np.nan))
    L = r / sigma

    n = k
    c = (2 * np.log(n)) ** 0.5 / mu1
    Cn = c - (np.log(np.pi) + np.log(np.log(n))) / (2 * mu1 * (2 * np.log(n)) ** 0.5)
    Sn = 1 / (mu1 * (2 * np.log(n)) ** 0.5)
    # Kuantil Gumbel: -log(-log(1-alpha))
    beta = -np.log(-np.log(1 - alpha))
    ambang = Cn + Sn * beta

    return pd.DataFrame({
        "ret": r, "L": L, "abs_L": L.abs(),
        "ambang": ambang,
        "lompatan": L.abs() > ambang,
        "arah": np.sign(L),
    })


# ------------------------------------------------------------------ memori
def hurst(s: pd.Series, maks_lag: int = 60) -> float:
    """Eksponen Hurst lewat rescaled range sederhana.

    H > 0,5 = tren berlanjut (persisten); H < 0,5 = balik arah (mean reverting);
    H = 0,5 = jalan acak.
    """
    x = s.dropna().to_numpy()
    if len(x) < maks_lag * 3:
        return np.nan
    lags = range(2, maks_lag)
    tau = [np.sqrt(np.std(x[lag:] - x[:-lag])) for lag in lags]
    tau = np.array(tau)
    ok = tau > 0
    if ok.sum() < 5:
        return np.nan
    poly = np.polyfit(np.log(np.array(list(lags))[ok]), np.log(tau[ok]), 1)
    return float(poly[0] * 2)


def ljung_box(r: pd.Series, lags: int = 10) -> dict:
    """Uji apakah ada autokorelasi berarti (= ada yang bisa diprediksi)."""
    from scipy.stats import chi2
    x = r.dropna().to_numpy()
    n = len(x)
    if n < lags * 5:
        return {}
    x = x - x.mean()
    denom = (x ** 2).sum()
    Q = 0.0
    for k in range(1, lags + 1):
        rk = (x[k:] * x[:-k]).sum() / denom
        Q += rk ** 2 / (n - k)
    Q *= n * (n + 2)
    return {"Q": float(Q), "p": float(1 - chi2.cdf(Q, lags)), "lags": lags}


def ringkas(ticker: str, df: pd.DataFrame) -> dict:
    c = df["close"]
    r = c.pct_change().dropna()
    lm = lee_mykland(c)
    n_jump = int(lm["lompatan"].fillna(False).sum())
    lb = ljung_box(r)
    return {
        "ticker": ticker,
        "n_bar": len(c),
        "vol_ewma%": round(float(ewma_vol(r).iloc[-1]) * 100, 1),
        "n_lompatan": n_jump,
        "lompatan_per_thn": round(n_jump / (len(c) / 244), 1) if len(c) > 244 else None,
        "lompatan_naik": int((lm["lompatan"].fillna(False) & (lm["arah"] > 0)).sum()),
        "lompatan_turun": int((lm["lompatan"].fillna(False) & (lm["arah"] < 0)).sum()),
        "porsi_var_lompatan%": round(float(porsi_lompatan(r).iloc[-1]) * 100, 1)
                               if pd.notna(porsi_lompatan(r).iloc[-1]) else None,
        "hurst": round(hurst(np.log(c)), 3),
        "ljung_p": round(lb.get("p", np.nan), 4) if lb else None,
    }
