"""Studi korelasi data makro/komoditas terhadap emiten IDX.

Mencari alpha berarti menemukan hubungan yang (a) nyata secara statistik,
(b) MENDAHULUI harga, dan (c) bertahan di periode yang berbeda. Menghitung
korelasi saja tidak cukup dan justru menyesatkan:

  1. Korelasi serentak tidak berguna untuk trading. Kalau ekspor batubara naik
     bersamaan dengan harga PTBA, informasinya sudah ada di harga. Yang bernilai
     adalah lead — makro bulan ini memprediksi saham bulan depan.

  2. Menguji 15 saham x 10 seri makro x 4 lag = 600 kombinasi berarti sekitar
     30 akan lolos p<0,05 MURNI KEBETULAN. Modul ini menerapkan koreksi
     Benjamini-Hochberg (FDR) supaya penemuan palsu terkendali.

  3. Hubungan yang tidak bertahan di paruh kedua sampel adalah derau. Setiap
     temuan diuji ulang secara terpisah pada paruh-1 dan paruh-2.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ke_bulanan(harga: pd.Series) -> pd.Series:
    """Return bulanan dari deret harga harian."""
    return harga.resample("ME").last().pct_change().dropna()


def perubahan(s: pd.Series, mode: str = "pct") -> pd.Series:
    """Ubah level makro jadi perubahan — level cenderung tidak stasioner."""
    s = s.resample("ME").last()
    if mode == "pct":
        return s.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if mode == "diff":
        return s.diff().dropna()
    return s.dropna()


def korelasi_lag(x: pd.Series, y: pd.Series, lag: int) -> tuple[float, float, int]:
    """Korelasi Pearson antara x (makro) yang MENDAHULUI y (saham) sejauh `lag` bulan.

    lag = 0 -> serentak; lag = 1 -> x bulan ini vs y bulan depan.
    Mengembalikan (r, p, n).
    """
    from scipy.stats import pearsonr
    xs = x.shift(lag) if lag else x
    d = pd.concat([xs.rename("x"), y.rename("y")], axis=1).dropna()
    if len(d) < 18:
        return (np.nan, np.nan, len(d))
    r, p = pearsonr(d["x"], d["y"])
    return (float(r), float(p), len(d))


def fdr_bh(p: np.ndarray, q: float = 0.10) -> np.ndarray:
    """Benjamini-Hochberg: tandai mana yang lolos pada tingkat penemuan palsu q."""
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    keluar = np.zeros(len(p), bool)
    idx = np.flatnonzero(ok)
    if idx.size == 0:
        return keluar
    urut = idx[np.argsort(p[idx])]
    m = urut.size
    ambang = q * (np.arange(1, m + 1)) / m
    lolos = p[urut] <= ambang
    if lolos.any():
        k = np.max(np.flatnonzero(lolos))
        keluar[urut[: k + 1]] = True
    return keluar


def studi(makro: dict[str, pd.Series], saham: dict[str, pd.Series],
          lags=(0, 1, 2, 3), q: float = 0.10) -> pd.DataFrame:
    """Uji semua pasangan makro x saham x lag, lalu koreksi pengujian berganda."""
    rows = []
    for nm, ms in makro.items():
        mx = perubahan(ms)
        for ns, ss in saham.items():
            sy = ke_bulanan(ss)
            for lg in lags:
                r, p, n = korelasi_lag(mx, sy, lg)
                if not np.isfinite(r):
                    continue
                rows.append({"makro": nm, "saham": ns, "lag": lg,
                             "r": round(r, 3), "p": p, "n": n})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["lolos_mentah"] = df["p"] < 0.05
    df["lolos_fdr"] = fdr_bh(df["p"].to_numpy(), q=q)
    df["p"] = df["p"].round(4)
    return df.sort_values("p").reset_index(drop=True)


def uji_stabilitas(makro: pd.Series, saham: pd.Series, lag: int) -> dict:
    """Apakah hubungan bertahan bila sampel dibelah dua menurut waktu?"""
    mx, sy = perubahan(makro), ke_bulanan(saham)
    d = pd.concat([mx.shift(lag).rename("x"), sy.rename("y")], axis=1).dropna()
    if len(d) < 36:
        return {}
    mid = len(d) // 2
    from scipy.stats import pearsonr
    r1, p1 = pearsonr(d["x"].iloc[:mid], d["y"].iloc[:mid])
    r2, p2 = pearsonr(d["x"].iloc[mid:], d["y"].iloc[mid:])
    return {"r_paruh1": round(float(r1), 3), "p_paruh1": round(float(p1), 4),
            "r_paruh2": round(float(r2), 3), "p_paruh2": round(float(p2), 4),
            "n1": mid, "n2": len(d) - mid,
            "arah_sama": bool(np.sign(r1) == np.sign(r2)),
            "stabil": bool(np.sign(r1) == np.sign(r2) and abs(r2) > 0.15)}
