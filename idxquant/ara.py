"""Deteksi potensi ARA — versi jujur, tanpa mengarang data foreign flow.

Produk komersial biasanya menggabungkan foreign flow + broker summary + volume +
momentum. Foreign flow dan broker summary adalah data IDX berlisensi yang TIDAK
tersedia gratis, jadi modul ini hanya memakai yang benar-benar ada: harga dan volume.

Pendekatannya bukan menebak, melainkan MENGUKUR: cari semua kejadian ARA di masa
lalu, lihat ciri-ciri hari SEBELUMNYA, lalu hitung seberapa besar tiap ciri menaikkan
peluang ARA dibanding base rate. Kalau sebuah ciri tidak menaikkan peluang secara
berarti, ia tidak dipakai — betapapun masuk akal kedengarannya.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ar_limit


def tandai_ara(d: pd.DataFrame, ambang: float = 0.98) -> pd.DataFrame:
    """Tandai hari ARA dan hitung ciri-ciri hari sebelumnya."""
    x = d.copy()
    prev = x["close"].shift(1)
    x["ret"] = x["close"] / prev - 1
    x["limit"] = prev.apply(lambda p: ar_limit(p) if p and p > 0 else np.nan)
    x["ara"] = x["ret"] >= x["limit"] * ambang

    rng = (x["high"] - x["low"]).replace(0, np.nan)
    x["pos_close"] = ((x["close"] - x["low"]) / rng).clip(0, 1)
    v20 = x["volume"].rolling(20).mean().replace(0, np.nan)
    x["rvol"] = x["volume"] / v20
    x["rvol5"] = x["volume"].rolling(5).mean() / v20
    x["ret5"] = x["close"] / x["close"].shift(5) - 1
    x["ret20"] = x["close"] / x["close"].shift(20) - 1
    hi60 = x["high"].rolling(60).max()
    x["dari_hi60"] = x["close"] / hi60 - 1
    x["atr_pct"] = ((x["high"] - x["low"]) / x["close"]).rolling(14).mean()
    x["ara_kemarin"] = x["ara"].shift(1).fillna(False)
    x["ara_5hari"] = x["ara"].shift(1).rolling(5).max().fillna(0).astype(bool)
    x["dekat_ara"] = x["ret"] >= x["limit"] * 0.6      # menyentuh 60% batas
    # Target: apakah BESOK ARA?
    x["ara_besok"] = x["ara"].shift(-1)
    return x


CIRI = {
    "Volume >2x rata2":      lambda x: x["rvol"] > 2.0,
    "Volume >3x rata2":      lambda x: x["rvol"] > 3.0,
    "Tutup di 90% atas":     lambda x: x["pos_close"] > 0.90,
    "Naik >60% batas ARA":   lambda x: x["dekat_ara"],
    "ARA kemarin":           lambda x: x["ara_kemarin"],
    "ARA dalam 5 hari":      lambda x: x["ara_5hari"],
    "Momentum 5h >15%":      lambda x: x["ret5"] > 0.15,
    "Dekat puncak 60h":      lambda x: x["dari_hi60"] > -0.02,
    "Volatil (ATR>7%)":      lambda x: x["atr_pct"] > 0.07,
}

# Kombinasi yang diuji sebagai kandidat sinyal
KOMBINASI = {
    "Vol>3x + tutup kuat":       lambda x: (x["rvol"] > 3.0) & (x["pos_close"] > 0.90),
    "Vol>2x + dekat batas ARA":  lambda x: (x["rvol"] > 2.0) & x["dekat_ara"],
    "ARA kemarin + vol>2x":      lambda x: x["ara_kemarin"] & (x["rvol"] > 2.0),
    "ARA kemarin + tutup kuat":  lambda x: x["ara_kemarin"] & (x["pos_close"] > 0.90),
    "Tiga sekaligus":            lambda x: ((x["rvol"] > 2.0) & (x["pos_close"] > 0.90)
                                            & x["dekat_ara"]),
}


def kumpulkan(prepared: dict[str, pd.DataFrame], min_bar: int = 300) -> pd.DataFrame:
    rows = []
    for t, d in prepared.items():
        if d is None or len(d) < min_bar:
            continue
        x = tandai_ara(d)
        x = x.dropna(subset=["ara_besok", "rvol", "pos_close"])
        if len(x):
            x = x.assign(ticker=t)
            rows.append(x[["ticker", "close", "ret", "limit", "ara", "ara_besok",
                           "pos_close", "rvol", "rvol5", "ret5", "ret20",
                           "dari_hi60", "atr_pct", "ara_kemarin", "ara_5hari",
                           "dekat_ara"]])
    return pd.concat(rows) if rows else pd.DataFrame()


def evaluasi(P: pd.DataFrame, ciri: dict) -> pd.DataFrame:
    """Untuk tiap ciri: peluang ARA besok, dibanding base rate."""
    base = float(P["ara_besok"].mean())
    out = []
    for nama, fn in ciri.items():
        m = fn(P).fillna(False)
        sub = P[m]
        if len(sub) < 50:
            out.append({"Ciri": nama, "N": int(len(sub)), "Catatan": "sampel kecil"})
            continue
        p = float(sub["ara_besok"].mean())
        # Uji proporsi sederhana
        se = np.sqrt(base * (1 - base) / len(sub))
        z = (p - base) / se if se > 0 else np.nan
        out.append({
            "Ciri": nama, "N": int(len(sub)),
            "P(ARA besok)%": round(p * 100, 3),
            "Base rate%": round(base * 100, 3),
            "Lift": round(p / base, 2) if base > 0 else np.nan,
            "z": round(z, 1),
            "Berguna": "ya" if (z > 3 and p / base > 1.5) else "tidak",
        })
    return pd.DataFrame(out)


def skor(x: pd.Series) -> float:
    """Skor potensi ARA 0-100 dari ciri yang terbukti berguna.

    Bobot ditentukan dari lift yang terukur, bukan dari intuisi.
    Dikalibrasi ulang bila hasil evaluasi berubah.
    """
    s = 0.0
    if x.get("ara_kemarin"):
        s += 30
    if (x.get("rvol") or 0) > 3.0:
        s += 20
    elif (x.get("rvol") or 0) > 2.0:
        s += 12
    if (x.get("pos_close") or 0) > 0.90:
        s += 18
    if x.get("dekat_ara"):
        s += 20
    if (x.get("dari_hi60") or -1) > -0.02:
        s += 8
    if (x.get("atr_pct") or 0) > 0.07:
        s += 4
    return min(100.0, s)
