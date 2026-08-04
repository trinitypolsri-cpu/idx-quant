"""Definisi setup kuantitatif + screener cross-section untuk universe IDX."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MIN_PRICE, MIN_TURNOVER_IDR
from .indicators import enrich
from .indicators import mulai
from .universe import sector_of

# ---------------------------------------------------------------------------
# Setup: masing-masing mengembalikan boolean Series sepanjang df.
# Semua kondisi dievaluasi pada bar tertutup -> tidak ada look-ahead.
# ---------------------------------------------------------------------------


def trend_template(d: pd.DataFrame) -> pd.Series:
    """Trend template gaya Minervini: struktur MA rapi + dekat puncak 52 minggu."""
    return (
        (d["close"] > d["ma50"])
        & (d["ma50"] > d["ma150"])
        & (d["ma150"] > d["ma200"])
        & (d["ma200"] > d["ma200"].shift(21))
        & (d["from_hi"] > -0.25)
        & (d["from_lo"] > 0.30)
        & (d["adx14"] > 20)
    )


def squeeze_breakout(d: pd.DataFrame) -> pd.Series:
    """Volatilitas mampat (BB di dalam Keltner) lalu jebol ke atas dengan volume."""
    was_squeezed = d["squeeze"].shift(1).rolling(10, min_periods=1).max().astype(bool)
    return (
        was_squeezed
        & (~d["squeeze"])
        & (d["close"] > d["bb_up"].shift(1))
        & (d["vol_ratio"] > 1.5)
        & (d["close"] > d["ma50"])
    )


def base_breakout(d: pd.DataFrame) -> pd.Series:
    """Jebol tertinggi 55 hari dari basis, konfirmasi volume dan tren jangka panjang."""
    return (
        (d["close"] > d["dc55_hi"].shift(1))
        & (d["close"] > d["ma200"])
        & (d["vol_ratio"] > 1.8)
        & (d["atr_pct"] < 0.09)
    )


def pullback_uptrend(d: pd.DataFrame) -> pd.Series:
    """Koreksi sehat dalam tren naik: sentuh EMA21, RSI2 jenuh jual, tren utuh."""
    return (
        (d["close"] > d["ma200"])
        & (d["ma50"] > d["ma200"])
        & (d["low"] <= d["ema21"] * 1.02)
        & (d["rsi2"] < 15)
        & (d["from_hi"] > -0.20)
        & (d["adx14"] > 18)
    )


def mean_reversion(d: pd.DataFrame) -> pd.Series:
    """Mean reversion jangka pendek: jatuh jauh di bawah BB bawah tapi di atas MA200."""
    return (
        (d["close"] > d["ma200"])
        & (d["close"] < d["bb_lo"])
        & (d["rsi14"] < 32)
        & (d["close"] > d["close"].shift(1))
    )


def rs_leader(d: pd.DataFrame, rs_line: pd.Series) -> pd.Series:
    """Garis kekuatan relatif (vs IHSG) mencetak tertinggi 63 hari."""
    rs_high = rs_line.rolling(63, min_periods=63).max()
    return (rs_line >= rs_high * 0.999) & (d["close"] > d["ma50"])


# --------------------------------------------------------------------------
# Setup dari indikator klasik & ICT/SMC — HANYA yang lolos pengujian.
# Dari 25 sinyal yang diuji (run_indikator_uji.py), 7 mengalahkan base rate dan
# lolos koreksi FDR. Yang gagal TIDAK dipasang, termasuk Supertrend, PSAR,
# Stochastic, CCI oversold, RSI oversold, EMA cross, dan Tenkan/Kijun cross.
#
# Dua konsep ICT bahkan terbukti MERUGIKAN di IDX dan sengaja tidak dipakai:
#   Discount zone     -0,667% vs base, t = -10,70  (N=57.684)
#   Sweep + discount  -0,874% vs base, t =  -2,91
# Membeli "murah" di zona discount adalah pola menangkap pisau jatuh di pasar
# yang didominasi momentum seperti IDX.
# --------------------------------------------------------------------------


def fvg_bullish(d: pd.DataFrame, min_pct: float = 0.002) -> pd.Series:
    """Fair Value Gap bullish (ICT) — celah tiga-lilin, sinyal tunggal terkuat."""
    celah = d["low"] - d["high"].shift(2)
    return (celah > 0) & (celah / d["close"] > min_pct)


def kumo_naik(d: pd.DataFrame) -> pd.Series:
    """FILTER, bukan pemicu: harga di atas awan Ichimoku dan awan berarah naik.

    Versi PERISTIWA (bar saat harga baru menembus awan) sudah diuji dan TIDAK
    punya edge: +0,316% vs base dengan t=0,65, bahkan negatif bila hanya
    menembus tanpa syarat awan naik (-0,541%, t=-1,42). Yang punya edge adalah
    KEADAANNYA (+1,136%, t=7,92). Karena itu ini dipakai sebagai penyaring
    kondisi, bukan sinyal "beli hari ini".
    """
    return ((d["close"] > d["senkou_a"]) & (d["close"] > d["senkou_b"])
            & (d["senkou_a"] > d["senkou_b"]))


def macd_momentum(d: pd.DataFrame) -> pd.Series:
    """MACD di atas nol dan masih menguat — bukan sekadar persilangan."""
    return (d["macd"] > 0) & (d["macd"] > d["macd"].shift(1)) & (d["close"] > d["ma50"])


def bos_naik(d: pd.DataFrame, kiri: int = 2, kanan: int = 2) -> pd.Series:
    """Break of Structure naik (SMC) — menembus swing high terkonfirmasi."""
    h = d["high"]
    n = kiri + kanan + 1
    sh = (h == h.rolling(n, center=True).max()).shift(kanan).fillna(False)
    level = h.where(sh).ffill()
    return d["close"] > level.shift(1)


def adr_tenang(d: pd.DataFrame) -> pd.Series:
    """Rentang hari ini di bawah 50% ADR — kontraksi volatilitas dalam tren."""
    return (d["adr_terpakai"] < 50) & (d["close"] > d["ma50"])


SETUPS = {
    "TrendTemplate": trend_template,
    "SqueezeBreakout": squeeze_breakout,
    "BaseBreakout": base_breakout,
    # DIMATIKAN — terbukti tidak signifikan pada event study 5 tahun:
    #   PullbackUptrend  edge +0,11%  t=0,44  (N=2.835)
    #   MeanReversion    edge +3,11%  t=0,49  tapi N hanya 10
    #   RSLeader         edge +0,22%  t=0,89  (N=6.797)
    # Menampilkan sinyal yang tidak terbukti melatih pengguna mengabaikan
    # SEMUA sinyal, termasuk yang terbukti. Definisinya tetap ada di atas agar
    # bisa diuji ulang, tapi tidak lagi masuk pemindaian.
    "FVGBullish": fvg_bullish,
    "KumoNaik": kumo_naik,
    "MACDMomentum": macd_momentum,
    "BOSNaik": bos_naik,
    "ADRTenang": adr_tenang,
}

# Sinyal yang bersifat KEADAAN (berlaku berhari-hari), bukan pemicu entry.
# Dipisahkan agar tidak dibaca sebagai "beli hari ini" — keempatnya menyala pada
# 40-46% emiten karena memang sebanyak itu yang sedang dalam kondisi tersebut.
FILTER = {"KumoNaik", "MACDMomentum", "BOSNaik", "ADRTenang"}


# ---------------------------------------------------------------------------
# Screener
# ---------------------------------------------------------------------------


def prepare(data: dict[str, pd.DataFrame], bench: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Hitung indikator + kolom sinyal untuk tiap ticker."""
    from .classic import enrich as enrich_klasik

    bench_close = bench["close"]
    out = {}
    for t, raw in data.items():
        # Indikator klasik (MACD, Ichimoku, ADR, dll) dibutuhkan setup baru
        d = enrich_klasik(enrich(raw))
        rs_line = (d["close"] / bench_close.reindex(d.index).ffill()).replace(
            [np.inf, -np.inf], np.nan
        )
        d["rs_line"] = rs_line
        for name, fn in SETUPS.items():
            d[f"sig_{name}"] = fn(d).fillna(False)
        # RSLeader dimatikan (t=0,89 — tidak signifikan)
        d["sig_RSLeader"] = False
        out[t] = d
    return out


def liquid_mask(d: pd.DataFrame) -> pd.Series:
    return (d["close"] >= MIN_PRICE) & (d["turnover_med20"] >= MIN_TURNOVER_IDR)


def scan(prepared: dict[str, pd.DataFrame], asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """Snapshot cross-section pada tanggal terakhir (atau `asof`)."""
    rows = []
    for t, d in prepared.items():
        dd = d if asof is None else d[d.index <= asof]
        if len(dd) < 250:
            continue
        r = dd.iloc[-1]
        rows.append(
            {
                "ticker": t,
                "sektor": sector_of(t),
                "tanggal": dd.index[-1].date(),
                "close": r["close"],
                "turnover_med20_M": r["turnover_med20"] / 1e6,
                "ret_1m": r["roc21"],
                "ret_3m": r["roc63"],
                "ret_6m": r["roc126"],
                "ret_12m": r["roc244"],
                "from_hi": r["from_hi"],
                "from_lo": r["from_lo"],
                "rsi14": r["rsi14"],
                "adx14": r["adx14"],
                "atr_pct": r["atr_pct"],
                "vol_ratio": r["vol_ratio"],
                "bb_width": r["bb_width"],
                "di_atas_ma200": bool(r["close"] > r["ma200"]) if pd.notna(r["ma200"]) else False,
                "obv_slope": r["obv_slope"],
                "likuid": bool(liquid_mask(dd).iloc[-1]),
                **{f"sig_{k}": bool(r.get(f"sig_{k}", False)) for k in
                   list(SETUPS) + ["RSLeader"]},
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Skor momentum komposit: rata-rata rank persentil ROC multi-horizon,
    # dipenalti volatilitas (mendekati konstruksi faktor momentum institusional).
    for col in ("ret_1m", "ret_3m", "ret_6m", "ret_12m"):
        df[f"rank_{col}"] = df[col].rank(pct=True)
    df["mom_score"] = (
        0.15 * df["rank_ret_1m"]
        + 0.30 * df["rank_ret_3m"]
        + 0.35 * df["rank_ret_6m"]
        + 0.20 * df["rank_ret_12m"]
    )
    df["vol_rank"] = df["atr_pct"].rank(pct=True)
    df["skor"] = (100 * (0.80 * df["mom_score"] + 0.20 * (1 - df["vol_rank"]))).round(1)
    df["n_sinyal"] = df[[c for c in df.columns if c.startswith("sig_")]].sum(axis=1)
    return df.sort_values("skor", ascending=False).reset_index(drop=True)
