"""Optimasi portofolio dan pengukuran risiko untuk IDX.

Berisi:
  Mean-variance (Markowitz)  bobot optimal, garis efisien, portofolio Sharpe maksimum
  Shrinkage Ledoit-Wolf      kovarians stabil; matriks sampel mentah sangat berisik
                             saat jumlah aset mendekati jumlah observasi
  VaR & CVaR                 historis, parametrik, dan Cornish-Fisher (mengoreksi
                             skewness/kurtosis — penting karena return IDX jauh dari normal)
  Risk parity                alternatif yang tidak bergantung pada estimasi return
  Batas IDX                  long-only, pembulatan lot 100, batas bobot per emiten

Peringatan yang melekat pada metode ini: mean-variance sangat sensitif terhadap
estimasi return. Kesalahan kecil pada perkiraan return menghasilkan bobot ekstrem.
Karena itu di sini tersedia varian yang mengabaikan return sepenuhnya (min-variance
dan risk parity), dan hasilnya dibandingkan agar terlihat seberapa rapuh optimasinya.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import LOT_SIZE, RISK_FREE, TRADING_DAYS


# ------------------------------------------------------------------ kovarians
def ledoit_wolf(R: pd.DataFrame) -> np.ndarray:
    """Shrinkage kovarians ke target diagonal (varians rata-rata).

    Matriks kovarians sampel buruk ketika N aset besar relatif terhadap T observasi.
    Shrinkage menariknya ke target sederhana dan menghasilkan bobot yang jauh lebih stabil.
    """
    X = R.dropna().to_numpy()
    T, N = X.shape
    Xc = X - X.mean(axis=0)
    S = Xc.T @ Xc / T
    mu = np.trace(S) / N
    F = mu * np.eye(N)                      # target: diagonal varians rata-rata

    d2 = ((S - F) ** 2).sum()
    b2 = sum(((np.outer(Xc[t], Xc[t]) - S) ** 2).sum() for t in range(T)) / T**2
    b2 = min(b2, d2)
    shrink = b2 / d2 if d2 > 0 else 0.0
    return shrink * F + (1 - shrink) * S


# ------------------------------------------------------------------ optimasi
def _proyeksi_simpleks(w: np.ndarray, wmax: float) -> np.ndarray:
    """Proyeksikan ke {w >= 0, sum w = 1, w <= wmax}."""
    w = np.clip(w, 0, wmax)
    for _ in range(100):
        s = w.sum()
        if abs(s - 1) < 1e-9:
            break
        w = np.clip(w / s if s > 0 else np.ones_like(w) / len(w), 0, wmax)
    if w.sum() <= 0:
        w = np.ones_like(w) / len(w)
    return w / w.sum()


def optimasi(R: pd.DataFrame, tujuan: str = "sharpe", wmax: float = 0.25,
             iterasi: int = 4000, seed: int = 3) -> dict:
    """Optimasi long-only dengan batas bobot, memakai gradien proyeksi.

    tujuan: 'sharpe' | 'min_var' | 'risk_parity'
    """
    R = R.dropna(axis=1, how="any")
    if R.shape[1] < 2:
        return {}
    aset = list(R.columns)
    N = len(aset)
    S = ledoit_wolf(R) * TRADING_DAYS
    mu = R.mean().to_numpy() * TRADING_DAYS

    rng = np.random.default_rng(seed)
    w = _proyeksi_simpleks(np.ones(N) / N, wmax)
    lr = 0.02

    for i in range(iterasi):
        var = float(w @ S @ w)
        vol = np.sqrt(max(var, 1e-12))
        if tujuan == "min_var":
            g = 2 * S @ w
        elif tujuan == "risk_parity":
            # samakan kontribusi risiko: RC_i = w_i * (Sw)_i
            rc = w * (S @ w)
            target = var / N
            g = 2 * (rc - target) * (S @ w + w * np.diag(S))
        else:                                   # sharpe
            ex = mu - RISK_FREE
            num = float(w @ ex)
            g = -(ex * vol - num * (S @ w) / vol) / max(var, 1e-12)
        w = _proyeksi_simpleks(w - lr * g / (np.abs(g).max() + 1e-12), wmax)
        if i % 1000 == 999:
            lr *= 0.5

    ret = float(w @ mu)
    vol = float(np.sqrt(w @ S @ w))
    return {
        "bobot": pd.Series(w, index=aset).sort_values(ascending=False),
        "return_thn": ret, "vol_thn": vol,
        "sharpe": (ret - RISK_FREE) / vol if vol > 0 else np.nan,
        "n_aset_efektif": float(1 / (w ** 2).sum()),
        "tujuan": tujuan,
    }


def garis_efisien(R: pd.DataFrame, n: int = 12, wmax: float = 0.25) -> pd.DataFrame:
    """Beberapa titik pada garis efisien, dari min-variance ke Sharpe maksimum."""
    rows = []
    for tuj in ("min_var", "sharpe"):
        r = optimasi(R, tujuan=tuj, wmax=wmax)
        if r:
            rows.append({"tujuan": tuj, "return%": r["return_thn"] * 100,
                         "vol%": r["vol_thn"] * 100, "sharpe": r["sharpe"],
                         "n_efektif": r["n_aset_efektif"]})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ risiko
def var_historis(r: pd.Series, alpha: float = 0.05) -> float:
    return float(np.percentile(r.dropna(), alpha * 100))


def cvar_historis(r: pd.Series, alpha: float = 0.05) -> float:
    r = r.dropna()
    v = np.percentile(r, alpha * 100)
    ekor = r[r <= v]
    return float(ekor.mean()) if len(ekor) else float(v)


def var_parametrik(r: pd.Series, alpha: float = 0.05) -> float:
    from scipy.stats import norm
    r = r.dropna()
    return float(r.mean() + norm.ppf(alpha) * r.std(ddof=1))


def var_cornish_fisher(r: pd.Series, alpha: float = 0.05) -> float:
    """VaR yang dikoreksi skewness dan kurtosis.

    Return saham IDX berekor gemuk dan miring; VaR normal meremehkan risiko ekor.
    """
    from scipy.stats import kurtosis, norm, skew
    r = r.dropna()
    z = norm.ppf(alpha)
    s = float(skew(r))
    k = float(kurtosis(r, fisher=True))
    zc = (z + (z**2 - 1) * s / 6 + (z**3 - 3*z) * k / 24
          - (2*z**3 - 5*z) * s**2 / 36)
    return float(r.mean() + zc * r.std(ddof=1))


def ringkas_risiko(r: pd.Series, modal: float = 1e9,
                   alpha: float = 0.05) -> pd.DataFrame:
    r = r.dropna()
    from scipy.stats import kurtosis, skew
    metode = {
        "Historis": var_historis(r, alpha),
        "Parametrik (normal)": var_parametrik(r, alpha),
        "Cornish-Fisher": var_cornish_fisher(r, alpha),
    }
    rows = [{"Metode": k, f"VaR {int((1-alpha)*100)}%": round(v * 100, 3),
             "Rupiah": round(v * modal)} for k, v in metode.items()]
    rows.append({"Metode": f"CVaR {int((1-alpha)*100)}% (historis)",
                 f"VaR {int((1-alpha)*100)}%": round(cvar_historis(r, alpha) * 100, 3),
                 "Rupiah": round(cvar_historis(r, alpha) * modal)})
    df = pd.DataFrame(rows)
    df.attrs["skew"] = float(skew(r))
    df.attrs["kurtosis"] = float(kurtosis(r, fisher=True))
    return df


# ------------------------------------------------------------------ eksekusi IDX
def ke_lot(bobot: pd.Series, harga: pd.Series, modal: float) -> pd.DataFrame:
    """Ubah bobot menjadi jumlah lot yang benar-benar bisa dieksekusi di IDX."""
    rows = []
    for t, w in bobot.items():
        p = float(harga.get(t, np.nan))
        if not np.isfinite(p) or p <= 0 or w <= 0:
            continue
        nilai = modal * float(w)
        lot = int(nilai // (p * LOT_SIZE))
        if lot < 1:
            continue
        rows.append({"ticker": t, "bobot_target%": round(float(w) * 100, 2),
                     "harga": p, "lot": lot, "lembar": lot * LOT_SIZE,
                     "nilai": round(lot * LOT_SIZE * p),
                     "bobot_nyata%": round(lot * LOT_SIZE * p / modal * 100, 2)})
    df = pd.DataFrame(rows)
    if len(df):
        df["selisih%"] = (df["bobot_nyata%"] - df["bobot_target%"]).round(2)
    return df
