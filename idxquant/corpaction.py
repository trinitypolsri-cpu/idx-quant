"""Deteksi jejak sebelum pergerakan besar — akuisisi, merger, tender offer.

Logikanya bukan menebak siapa yang akan diakuisisi, melainkan menguji secara
historis: SEBELUM sebuah saham melonjak besar, apakah ada jejak yang terlihat di
harga dan volume?

Aksi korporasi besar hampir selalu didahului periode akumulasi — pihak yang tahu
lebih dulu membeli sebelum pengumuman. Kalau jejak itu ada, ia akan muncul sebagai
pola volume/harga pada 5-20 hari sebelum lonjakan.

Kalau TIDAK ada jejak, itu juga jawaban yang berguna: berarti lonjakan di IDX
umumnya kejutan murni dan mengejarnya sebelum terjadi adalah usaha sia-sia.

Catatan penting: modul ini TIDAK bisa membedakan lonjakan karena M&A dari lonjakan
karena hal lain (rilis laba, berita sektor, spekulasi). Tanpa data aksi korporasi
berlisensi, yang bisa diukur hanyalah "pergerakan besar", bukan "merger".
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def tandai_lonjakan(d: pd.DataFrame, ambang: float = 0.20,
                    jendela: int = 5) -> pd.DataFrame:
    """Tandai awal periode lonjakan besar (kumulatif `jendela` hari >= ambang)."""
    x = d.copy()
    x["ret"] = x["close"].pct_change()
    fwd = x["close"].shift(-jendela) / x["close"] - 1
    x["lonjakan"] = fwd >= ambang
    # Hanya ambil awal episode: buang sinyal berturut-turut
    x["lonjakan_awal"] = x["lonjakan"] & ~x["lonjakan"].shift(1).fillna(False)
    return x


def ciri_sebelum(d: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """Ciri-ciri yang terukur pada hari H, dari data H dan sebelumnya saja."""
    x = d.copy()
    v20 = x["volume"].rolling(20).mean().replace(0, np.nan)
    x["rvol"] = x["volume"] / v20
    x["rvol5"] = x["volume"].rolling(5).mean() / v20
    x["rvol10"] = x["volume"].rolling(10).mean() / v20

    rng = (x["high"] - x["low"]).replace(0, np.nan)
    x["pos_close"] = ((x["close"] - x["low"]) / rng).clip(0, 1)
    x["pos_close5"] = x["pos_close"].rolling(5).mean()

    x["ret5"] = x["close"] / x["close"].shift(5) - 1
    x["ret20"] = x["close"] / x["close"].shift(20) - 1
    x["vol_ret"] = x["close"].pct_change().rolling(20).std(ddof=0)

    # Akumulasi diam: volume naik tapi harga hampir tidak bergerak
    x["akum_diam"] = (x["rvol10"].clip(lower=0)
                      / (1 + x["ret20"].abs() * 20)).replace([np.inf, -np.inf], np.nan)

    # Rentang menyempit — sering mendahului pengumuman
    x["rng_pct"] = rng / x["close"]
    x["rng_ratio"] = x["rng_pct"].rolling(5).mean() / x["rng_pct"].rolling(20).mean()

    # Beli terus-menerus: berapa dari 10 hari terakhir ditutup di paruh atas
    x["hari_kuat"] = (x["pos_close"] > 0.6).rolling(10).sum()

    x["dari_hi60"] = x["close"] / x["high"].rolling(60).max() - 1
    return x


CIRI = ["rvol5", "rvol10", "pos_close5", "ret5", "ret20", "vol_ret",
        "akum_diam", "rng_ratio", "hari_kuat", "dari_hi60"]


def kumpulkan(prepared: dict[str, pd.DataFrame], ambang: float = 0.20,
              jendela: int = 5, min_bar: int = 300) -> pd.DataFrame:
    rows = []
    for t, d in prepared.items():
        if d is None or len(d) < min_bar:
            continue
        x = ciri_sebelum(d)
        x = tandai_lonjakan(x, ambang=ambang, jendela=jendela)
        x["ticker"] = t
        rows.append(x[["ticker", "close", "volume", "lonjakan_awal"] + CIRI])
    if not rows:
        return pd.DataFrame()
    P = pd.concat(rows).replace([np.inf, -np.inf], np.nan)
    return P.dropna(subset=["lonjakan_awal"])


def bandingkan_ciri(P: pd.DataFrame) -> pd.DataFrame:
    """Apakah ciri pada hari-H berbeda antara yang diikuti lonjakan dan yang tidak?"""
    from scipy.stats import mannwhitneyu
    ya = P[P["lonjakan_awal"]]
    tidak = P[~P["lonjakan_awal"]]
    rows = []
    for c in CIRI:
        a, b = ya[c].dropna(), tidak[c].dropna()
        if len(a) < 30 or len(b) < 100:
            continue
        try:
            u, p = mannwhitneyu(a, b, alternative="two-sided")
        except Exception:                                          # noqa: BLE001
            continue
        rows.append({
            "ciri": c,
            "median_lonjakan": round(float(a.median()), 4),
            "median_biasa": round(float(b.median()), 4),
            "rasio": round(float(a.median() / b.median()), 3) if b.median() else np.nan,
            "p": p,
            "n_lonjakan": len(a),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Koreksi pengujian berganda
    from .altdata import fdr_bh
    df["lolos_fdr"] = fdr_bh(df["p"].to_numpy(), q=0.10)
    df["p"] = df["p"].map(lambda v: f"{v:.2e}")
    return df.sort_values("rasio", key=lambda s: (s - 1).abs(), ascending=False)
