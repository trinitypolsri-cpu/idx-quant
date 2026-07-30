"""Dekomposisi return overnight vs intraday — untuk strategi BSJP / BPJS.

BSJP (Beli Sore Jual Pagi) menangkap return OVERNIGHT:
    open[t] / close[t-1] - 1

BPJS (Beli Pagi Jual Sore) menangkap return INTRADAY:
    close[t] / open[t] - 1

Keduanya menjumlah menjadi return harian total, jadi ini benar-benar memecah
"dari mana return sebuah saham berasal".

DUA HAL YANG MENENTUKAN, dan sering diabaikan:

1. BIAYA. Sekali putar di IDX ~0,40% (komisi 0,15% beli + 0,25% jual) DITAMBAH
   silang spread minimal 1 tick. Strategi harian berarti membayar itu SETIAP HARI.
   Rata-rata overnight harus melebihi biaya tersebut, bukan sekadar positif.

2. PERSISTENSI. Saham dengan overnight terbaik lima tahun terakhir belum tentu
   punya edge; bisa saja kebetulan. Karena itu ada uji paruh-1 vs paruh-2: kalau
   peringkatnya tidak berkorelasi, yang kita lihat cuma derau.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FEE_BUY, FEE_SELL, tick_size

BIAYA_KOMISI = FEE_BUY + FEE_SELL          # 0,40%


def biaya_putaran(harga: float) -> float:
    """Biaya sekali putar dalam fraksi: komisi + sekali silang spread."""
    if harga <= 0:
        return 1.0
    return BIAYA_KOMISI + tick_size(harga) / harga


def pecah(df: pd.DataFrame) -> pd.DataFrame:
    """Pecah return harian jadi komponen overnight dan intraday."""
    d = df.copy()
    d["overnight"] = d["open"] / d["close"].shift(1) - 1
    d["intraday"] = d["close"] / d["open"] - 1
    d["harian"] = d["close"] / d["close"].shift(1) - 1
    return d.dropna(subset=["overnight", "intraday"])


def _stat(r: pd.Series, biaya: float) -> dict:
    r = r.dropna()
    if len(r) < 30:
        return {}
    net = r - biaya
    return {
        "n": int(len(r)),
        "rata_kotor": float(r.mean()) * 100,
        "rata_net": float(net.mean()) * 100,
        "median_kotor": float(r.median()) * 100,
        "menang_kotor": float((r > 0).mean()) * 100,
        "menang_net": float((net > 0).mean()) * 100,
        "t": float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))) if r.std(ddof=1) else np.nan,
        "total_net": float(np.prod(1 + net) - 1) * 100,
        "sd": float(r.std(ddof=1)) * 100,
    }


def analisa(ticker: str, df: pd.DataFrame, min_bar: int = 250) -> dict | None:
    d = pecah(df)
    if len(d) < min_bar:
        return None
    harga = float(d["close"].iloc[-1])
    b = biaya_putaran(harga)

    on = _stat(d["overnight"], b)
    id_ = _stat(d["intraday"], b)
    if not on or not id_:
        return None

    return {
        "ticker": ticker, "harga": harga, "n_bar": len(d),
        "biaya_pct": round(b * 100, 3),
        "on_rata": round(on["rata_kotor"], 4), "on_net": round(on["rata_net"], 4),
        "on_menang": round(on["menang_kotor"], 1), "on_t": round(on["t"], 2),
        "on_total_net": round(on["total_net"], 1), "on_sd": round(on["sd"], 2),
        "id_rata": round(id_["rata_kotor"], 4), "id_net": round(id_["rata_net"], 4),
        "id_menang": round(id_["menang_kotor"], 1), "id_t": round(id_["t"], 2),
        "id_total_net": round(id_["total_net"], 1), "id_sd": round(id_["sd"], 2),
        "condong": "BSJP" if on["rata_kotor"] > id_["rata_kotor"] else "BPJS",
    }


def scan(prepared: dict[str, pd.DataFrame], likuid: list[str] | None = None,
         min_bar: int = 250) -> pd.DataFrame:
    rows = []
    for t, d in prepared.items():
        if likuid and t not in likuid:
            continue
        a = analisa(t, d, min_bar=min_bar)
        if a:
            rows.append(a)
    return pd.DataFrame(rows)


def uji_persistensi(prepared: dict[str, pd.DataFrame], likuid: list[str],
                    kolom: str = "overnight") -> dict:
    """Apakah edge overnight bertahan? Bandingkan peringkat paruh-1 vs paruh-2.

    Kalau korelasi peringkat mendekati nol, edge yang terlihat pada seluruh sampel
    tidak bisa dipakai untuk memilih saham ke depan — ia tidak stabil.
    """
    p1, p2 = {}, {}
    for t in likuid:
        d = prepared.get(t)
        if d is None:
            continue
        s = pecah(d)
        if len(s) < 400:
            continue
        mid = len(s) // 2
        p1[t] = float(s[kolom].iloc[:mid].mean())
        p2[t] = float(s[kolom].iloc[mid:].mean())

    if len(p1) < 20:
        return {}
    a = pd.Series(p1)
    b = pd.Series(p2).reindex(a.index)
    ok = a.notna() & b.notna()
    a, b = a[ok], b[ok]

    rho = float(a.rank().corr(b.rank()))
    # Apakah 10 teratas paruh-1 tetap unggul di paruh-2?
    top = a.nlargest(10).index
    return {
        "n": int(len(a)),
        "korelasi_peringkat": round(rho, 3),
        "rata_p2_semua": round(float(b.mean()) * 100, 4),
        "rata_p2_top10_p1": round(float(b[top].mean()) * 100, 4),
        "top10_unggul": bool(b[top].mean() > b.mean()),
    }


def kurva_ekuitas(df: pd.DataFrame, kolom: str, biaya: float) -> pd.Series:
    d = pecah(df)
    return (1 + (d[kolom] - biaya)).cumprod()
