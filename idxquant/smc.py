"""ICT / Smart Money Concepts dari OHLCV harian.

Konsep yang diterjemahkan ke aturan yang bisa diuji:

  FVG   Fair Value Gap      celah tiga-lilin: high[t-1] < low[t+1] (bullish).
                            Ketidakseimbangan yang sering "diisi" kemudian.
  OB    Order Block         lilin berlawanan terakhir sebelum dorongan impulsif.
  BOS   Break of Structure  harga menembus swing high/low sebelumnya -> tren lanjut.
  CHoCH Change of Character penembusan PERTAMA melawan struktur -> potensi balik arah.
  SWEEP Liquidity sweep     wick menembus swing low lalu ditutup kembali di atasnya
                            (stop hunt), atau sebaliknya di atas swing high.
  P/D   Premium / Discount  posisi harga dalam dealing range; di bawah 50% = discount.

PERINGATAN YANG JUJUR: ICT/SMC lahir dari pasar forex dan indeks berjangka yang
buka 24 jam dengan likuiditas dalam. IDX berbeda secara struktural — sesi pendek,
ada ARA/ARB yang memotong pergerakan, banyak emiten berfree-float kecil, dan gap
antar sesi sering. Karena itu modul ini TIDAK mengasumsikan konsep-konsep ini
bekerja di sini; semuanya diuji terlebih dulu lewat run_indikator_uji.py.

Semua deteksi memakai bar TERTUTUP dan hanya melihat ke belakang.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ------------------------------------------------------------------ struktur
def swing_points(df: pd.DataFrame, kiri: int = 2, kanan: int = 2):
    """Titik ayunan fraktal. Dikonfirmasi `kanan` bar SETELAHNYA, jadi saat dipakai
    sebagai sinyal harus digeser — kalau tidak, terjadi look-ahead."""
    h, l = df["high"], df["low"]
    n = kiri + kanan + 1
    sh = (h == h.rolling(n, center=True).max())
    sl = (l == l.rolling(n, center=True).min())
    # Geser agar hanya memakai informasi yang sudah tersedia
    return sh.shift(kanan).fillna(False), sl.shift(kanan).fillna(False)


def struktur(df: pd.DataFrame, kiri: int = 2, kanan: int = 2) -> pd.DataFrame:
    """Break of Structure dan Change of Character."""
    d = df.copy()
    sh, sl = swing_points(d, kiri, kanan)

    # Level swing terakhir yang sudah terkonfirmasi
    last_sh = d["high"].where(sh).ffill()
    last_sl = d["low"].where(sl).ffill()
    d["swing_high"], d["swing_low"] = last_sh, last_sl

    naik = d["close"] > last_sh.shift(1)
    turun = d["close"] < last_sl.shift(1)

    # Arah struktur berjalan
    arah = pd.Series(np.nan, index=d.index)
    arah[naik] = 1
    arah[turun] = -1
    arah = arah.ffill().fillna(0)
    d["arah_struktur"] = arah

    d["bos_naik"] = naik & (arah.shift(1) >= 0)
    d["bos_turun"] = turun & (arah.shift(1) <= 0)
    # CHoCH = penembusan pertama MELAWAN arah sebelumnya
    d["choch_naik"] = naik & (arah.shift(1) < 0)
    d["choch_turun"] = turun & (arah.shift(1) > 0)
    return d


# ------------------------------------------------------------------ FVG
def fair_value_gap(df: pd.DataFrame, min_pct: float = 0.002) -> pd.DataFrame:
    """Celah tiga-lilin. Ditandai pada bar KETIGA (saat celah menjadi fakta)."""
    d = df.copy()
    h1, l1 = d["high"].shift(2), d["low"].shift(2)
    h3, l3 = d["high"], d["low"]

    gap_naik = l3 - h1
    gap_turun = l1 - h3
    d["fvg_naik"] = (gap_naik > 0) & (gap_naik / d["close"] > min_pct)
    d["fvg_turun"] = (gap_turun > 0) & (gap_turun / d["close"] > min_pct)
    d["fvg_atas"] = np.where(d["fvg_naik"], l3, np.where(d["fvg_turun"], l1, np.nan))
    d["fvg_bawah"] = np.where(d["fvg_naik"], h1, np.where(d["fvg_turun"], h3, np.nan))
    d["fvg_ukuran"] = np.where(d["fvg_naik"], gap_naik / d["close"],
                               np.where(d["fvg_turun"], gap_turun / d["close"], np.nan))
    return d


# ------------------------------------------------------------------ order block
def order_block(df: pd.DataFrame, impuls: float = 0.03, lihat: int = 3) -> pd.DataFrame:
    """Lilin berlawanan terakhir sebelum dorongan impulsif `impuls` dalam `lihat` bar."""
    d = df.copy()
    dorongan = d["close"].shift(-lihat) / d["close"] - 1
    bearish = d["close"] < d["open"]
    bullish = d["close"] > d["open"]
    # OB bullish: lilin turun yang diikuti dorongan naik kuat
    # Ditandai `lihat` bar SETELAH lilin OB, yaitu saat dorongan sudah terjadi dan
    # fakta itu diketahui. Batas zonanya diambil dari lilin OB aslinya (t-lihat),
    # bukan dari bar konfirmasi.
    d["ob_bullish"] = (bearish & (dorongan >= impuls)).shift(lihat).fillna(False)
    d["ob_bearish"] = (bullish & (dorongan <= -impuls)).shift(lihat).fillna(False)
    ada_ob = d["ob_bullish"] | d["ob_bearish"]
    d["ob_atas"] = d["high"].shift(lihat).where(ada_ob).ffill()
    d["ob_bawah"] = d["low"].shift(lihat).where(ada_ob).ffill()
    return d


# ------------------------------------------------------------------ likuiditas
def liquidity_sweep(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """Stop hunt: wick menembus level lalu ditutup kembali di dalam."""
    d = df.copy()
    ll = d["low"].rolling(lookback, min_periods=lookback).min().shift(1)
    hh = d["high"].rolling(lookback, min_periods=lookback).max().shift(1)
    d["sweep_bawah"] = (d["low"] < ll) & (d["close"] > ll)     # bullish
    d["sweep_atas"] = (d["high"] > hh) & (d["close"] < hh)     # bearish
    return d


# ------------------------------------------------------------------ premium/discount
def premium_discount(df: pd.DataFrame, lookback: int = 60) -> pd.DataFrame:
    """Posisi harga dalam dealing range. <50% discount, >50% premium."""
    d = df.copy()
    hh = d["high"].rolling(lookback, min_periods=20).max()
    ll = d["low"].rolling(lookback, min_periods=20).min()
    d["pd_posisi"] = (d["close"] - ll) / (hh - ll).replace(0, np.nan) * 100
    d["discount"] = d["pd_posisi"] < 50
    d["premium"] = d["pd_posisi"] > 50
    d["ekuilibrium"] = d["pd_posisi"].between(45, 55)
    return d


# ------------------------------------------------------------------ gabungan
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    d = struktur(df)
    d = fair_value_gap(d)
    d = order_block(d)
    d = liquidity_sweep(d)
    d = premium_discount(d)

    # Konfluensi khas ICT: sweep likuiditas di zona discount, dikonfirmasi
    # perubahan struktur pada bar yang sama atau sebelumnya.
    # CATATAN: versi awal memakai bos_naik.shift(-1) — itu membaca bar BERIKUTNYA
    # dan membuat sinyal tampak jauh lebih baik dari kenyataannya. Dihapus.
    konfirm_naik = d["choch_naik"] | d["bos_naik"]
    konfirm_turun = d["choch_turun"] | d["bos_turun"]
    d["setup_ict_bullish"] = (d["sweep_bawah"] & d["discount"]
                              & konfirm_naik.rolling(3, min_periods=1).max().astype(bool))
    d["setup_ict_bearish"] = (d["sweep_atas"] & d["premium"]
                              & konfirm_turun.rolling(3, min_periods=1).max().astype(bool))
    return d
