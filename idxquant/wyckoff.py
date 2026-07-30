"""Analisis Wyckoff & VWAP pada bar intraday.

Wyckoff membaca hubungan antara USAHA (volume) dan HASIL (rentang harga).
Prinsipnya: volume besar yang gagal menghasilkan gerak berarti ada pihak yang
menyerap — dan penyerapan itu biasanya mendahului pembalikan.

Peristiwa yang dideteksi:

    SC  Selling Climax    volume ekstrem, bar turun lebar, tutup di atas -> penyerapan
    BC  Buying Climax     volume ekstrem, bar naik lebar, tutup di bawah -> distribusi
    SPR Spring            tembus ke bawah support lalu tutup kembali di dalam (jebakan bear)
    UT  Upthrust          tembus ke atas resistance lalu tutup kembali di dalam (jebakan bull)
    SOS Sign of Strength  jebol ke atas dengan volume mengembang
    SOW Sign of Weakness  jebol ke bawah dengan volume mengembang
    ABS Absorption        volume tinggi tapi rentang sempit -> ada yang menyerap diam-diam

Semua dievaluasi pada bar tertutup. Tidak ada peristiwa yang dinilai dari bar berjalan.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EVENT_LABEL = {
    "SC": ("Selling Climax", "Volume ekstrem pada bar turun lebar, tapi tutup di paruh atas — "
                             "penjualan diserap pembeli besar."),
    "BC": ("Buying Climax", "Volume ekstrem pada bar naik lebar, tapi tutup di paruh bawah — "
                            "pembelian didistribusikan."),
    "SPR": ("Spring", "Harga menembus support lalu ditutup kembali di dalam rentang — "
                      "jebakan bagi penjual."),
    "UT": ("Upthrust", "Harga menembus resistance lalu ditutup kembali di dalam rentang — "
                       "jebakan bagi pembeli."),
    "SOS": ("Sign of Strength", "Jebol ke atas rentang dengan volume mengembang."),
    "SOW": ("Sign of Weakness", "Jebol ke bawah rentang dengan volume mengembang."),
    "ABS": ("Absorption", "Volume tinggi tapi rentang sempit — pasokan/permintaan diserap."),
}
BULLISH = {"SC", "SPR", "SOS"}
BEARISH = {"BC", "UT", "SOW"}


def vwap_bands(df: pd.DataFrame, k: float = 1.0):
    """VWAP sesi + pita deviasi standar berbobot volume."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    v = df["volume"].replace(0, np.nan)
    cum_v = v.cumsum()
    vw = (tp * v).cumsum() / cum_v
    var = ((tp - vw) ** 2 * v).cumsum() / cum_v
    sd = np.sqrt(var)
    return vw, vw - k * sd, vw + k * sd


def detect(df: pd.DataFrame, lookback: int = 20, vol_z: float = 2.0) -> pd.DataFrame:
    """Tandai peristiwa Wyckoff pada tiap bar."""
    d = df.copy()
    if len(d) < lookback + 3:
        d["event"] = None
        return d

    rng = (d["high"] - d["low"]).replace(0, np.nan)
    med_rng = rng.rolling(lookback, min_periods=5).median()
    med_vol = d["volume"].rolling(lookback, min_periods=5).median().replace(0, np.nan)

    d["rel_vol"] = d["volume"] / med_vol
    d["rel_rng"] = rng / med_rng
    # Posisi penutupan dalam bar: 1 = tutup di puncak, 0 = di dasar
    d["close_pos"] = ((d["close"] - d["low"]) / rng).clip(0, 1)

    # Support/resistance dari rentang sebelumnya (tidak termasuk bar berjalan)
    sup = d["low"].rolling(lookback, min_periods=5).min().shift(1)
    res = d["high"].rolling(lookback, min_periods=5).max().shift(1)
    d["support"], d["resistance"] = sup, res

    ev: list[str | None] = []
    for i in range(len(d)):
        r = d.iloc[i]
        e = None
        rv, rr, cp = r["rel_vol"], r["rel_rng"], r["close_pos"]
        if pd.isna(rv) or pd.isna(rr):
            ev.append(None)
            continue

        turun = r["close"] < r["open"]
        naik = r["close"] > r["open"]

        # Spring / Upthrust: tembus level lalu kembali masuk
        if pd.notna(r["support"]) and r["low"] < r["support"] and r["close"] > r["support"]:
            e = "SPR"
        elif pd.notna(r["resistance"]) and r["high"] > r["resistance"] and r["close"] < r["resistance"]:
            e = "UT"
        # Klimaks: volume ekstrem + rentang lebar + tutup melawan arah bar
        elif rv >= vol_z and rr >= 1.5 and turun and cp >= 0.55:
            e = "SC"
        elif rv >= vol_z and rr >= 1.5 and naik and cp <= 0.45:
            e = "BC"
        # Sign of strength / weakness: jebol dengan volume
        elif pd.notna(r["resistance"]) and r["close"] > r["resistance"] and rv >= 1.5:
            e = "SOS"
        elif pd.notna(r["support"]) and r["close"] < r["support"] and rv >= 1.5:
            e = "SOW"
        # Absorption: usaha besar, hasil kecil
        elif rv >= vol_z and rr <= 0.6:
            e = "ABS"
        ev.append(e)

    d["event"] = ev
    return d


def summarise(ticker: str, df: pd.DataFrame, lookback: int = 20) -> dict:
    """Ringkasan Wyckoff + VWAP untuk satu emiten pada satu sesi."""
    d = detect(df, lookback=lookback)
    if "event" not in d or d.empty:
        return {"ticker": ticker, "n_bar": 0}

    vw, lo_b, up_b = vwap_bands(d)
    d["vwap"] = vw
    last = d.iloc[-1]
    price = float(last["close"])
    vwv = float(vw.iloc[-1]) if pd.notna(vw.iloc[-1]) else None

    events = d[d["event"].notna()]
    recent = events.tail(6)
    n_bull = int(recent["event"].isin(BULLISH).sum())
    n_bear = int(recent["event"].isin(BEARISH).sum())

    # Berapa lama harga bertahan di atas VWAP (penerimaan harga)
    above = (d["close"] > d["vwap"]).tail(min(len(d), 24))
    acceptance = float(above.mean()) * 100 if len(above) else None

    if n_bull > n_bear:
        bias = "akumulasi"
    elif n_bear > n_bull:
        bias = "distribusi"
    else:
        bias = "netral"

    return {
        "ticker": ticker,
        "n_bar": len(d),
        "harga": price,
        "vwap": None if vwv is None else round(vwv, 2),
        "vs_vwap": None if not vwv else round((price / vwv - 1) * 100, 2),
        "penerimaan_atas_vwap": None if acceptance is None else round(acceptance, 0),
        "pita_bawah": None if pd.isna(lo_b.iloc[-1]) else round(float(lo_b.iloc[-1]), 2),
        "pita_atas": None if pd.isna(up_b.iloc[-1]) else round(float(up_b.iloc[-1]), 2),
        "support": None if pd.isna(last["support"]) else round(float(last["support"]), 2),
        "resistance": None if pd.isna(last["resistance"]) else round(float(last["resistance"]), 2),
        "n_event": int(len(events)),
        "event_terakhir": None if recent.empty else recent["event"].iloc[-1],
        "waktu_event": None if recent.empty else recent.index[-1].strftime("%H:%M"),
        "bullish": n_bull, "bearish": n_bear, "bias": bias,
        "urutan": list(recent["event"]),
    }


def explain(kode: str) -> str:
    label, desc = EVENT_LABEL.get(kode, (kode, ""))
    return f"{label} — {desc}"
