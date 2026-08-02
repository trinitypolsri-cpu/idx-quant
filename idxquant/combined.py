"""Gabungkan seluruh sinyal menjadi SATU probabilitas terkalibrasi.

Alasannya: sembilan kartu setup terpisah membuat konfluensi terasa lebih
meyakinkan daripada seharusnya. Kumo, MACD, BOS, dan TrendTemplate pada dasarnya
mengukur hal yang sama — "sedang tren naik". Melihat empat kartu menyala terasa
seperti empat konfirmasi, padahal itu satu kondisi dilihat dari empat sudut.

Regresi logistik menangani tumpang tindih itu secara otomatis: fitur yang
berkorelasi berbagi bobot, sehingga tidak dihitung berkali-kali. Keluarannya satu
angka yang berarti apa adanya — "peluang 3,2%" benar-benar terjadi ~3,2% waktu.

Target: apakah return 21 hari ke depan MENGALAHKAN base rate emiten likuid.
Bukan sekadar "naik" — karena membeli acak pun naik 43% waktu. Yang bernilai
adalah unggul dari alternatif termudah.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .classic import enrich as enrich_klasik
from .config import FEE_BUY, FEE_SELL
from .indicators import enrich as enrich_dasar
from .smc import enrich as enrich_smc

BIAYA = FEE_BUY + FEE_SELL + 2 * 0.0015
HORIZON = 21

# Fitur numerik — bukan boolean menyala/mati, agar model bisa membedakan
# "sedikit di atas MA200" dari "jauh di atas".
FITUR = [
    "rsi14", "adx14", "atr_pct", "vol_ratio", "roc21", "roc63", "roc126",
    "from_hi", "from_lo", "bb_width", "obv_slope",
    "macd_hist_norm", "stoch_k", "cci", "adr", "adr_terpakai",
    "jarak_ma50", "jarak_ma200", "jarak_kumo", "pd_posisi",
    "fvg_ukuran_isi", "bos_aktif", "st_arah", "psar_jarak",
]


def siapkan(d: pd.DataFrame) -> pd.DataFrame:
    """Hitung seluruh fitur untuk satu emiten."""
    x = enrich_smc(enrich_klasik(enrich_dasar(d)))
    c = x["close"]

    x["macd_hist_norm"] = x["macd_hist"] / c
    x["jarak_ma50"] = c / x["ma50"] - 1
    x["jarak_ma200"] = c / x["ma200"] - 1
    kumo_atas = x[["senkou_a", "senkou_b"]].max(axis=1)
    x["jarak_kumo"] = c / kumo_atas - 1
    x["fvg_ukuran_isi"] = x["fvg_ukuran"].fillna(0)
    x["bos_aktif"] = x["arah_struktur"]
    x["psar_jarak"] = (c - x["psar"]) / c

    # Target: unggul dari base rate setelah biaya
    fwd = x["open"].shift(-1)
    exit_ = c.shift(-(HORIZON))
    x["ret_fwd"] = (exit_ / fwd - 1) - BIAYA
    return x


def bangun_panel(prepared: dict[str, pd.DataFrame], likuid: set[str],
                 min_bar: int = 320) -> pd.DataFrame:
    rows = []
    for t, d in prepared.items():
        if t not in likuid or d is None or len(d) < min_bar:
            continue
        x = siapkan(d)
        x["ticker"] = t
        kol = ["ticker", "close", "ret_fwd"] + [f for f in FITUR if f in x]
        rows.append(x[kol])
    if not rows:
        return pd.DataFrame()
    P = pd.concat(rows).replace([np.inf, -np.inf], np.nan)
    return P.sort_index()


def latih_dan_uji(P: pd.DataFrame, frac_latih: float = 0.5,
                  frac_kalib: float = 0.2) -> dict:
    """Latih pada masa lalu, kalibrasi, uji pada masa depan."""
    from .probability import bootstrap_ci, brier, tabel_kalibrasi, uji_temporal

    d = P.dropna(subset=["ret_fwd"]).copy()
    base = float(d["ret_fwd"].mean())
    d["target"] = (d["ret_fwd"] > base).astype(int)

    fitur = [f for f in FITUR if f in d.columns]
    r = uji_temporal(d, fitur, "target",
                     frac_latih=frac_latih, frac_kalib=frac_kalib)
    if "error" in r:
        return r
    r["base_return"] = base
    r["fitur"] = fitur

    # Nilai ekonomi: berapa return rata-rata di tiap desil probabilitas?
    te = d.iloc[r["split_uji"]:]
    q = pd.qcut(r["p_uji"], 10, labels=False, duplicates="drop")
    ek = pd.DataFrame({"desil": q, "ret": te["ret_fwd"].to_numpy()})
    r["ekonomi"] = (ek.groupby("desil")["ret"]
                    .agg(["size", "mean", "median"])
                    .assign(vs_base=lambda x: (x["mean"] - base) * 100)
                    .round(4))
    return r


def peluang_hari_ini(model, kalibrator, prepared: dict[str, pd.DataFrame],
                     likuid: set[str], fitur: list[str]) -> pd.DataFrame:
    """Hitung probabilitas untuk bar terakhir tiap emiten."""
    rows = []
    for t, d in prepared.items():
        if t not in likuid or d is None or len(d) < 320:
            continue
        x = siapkan(d)
        last = x.iloc[[-1]].copy()
        last["ticker"] = t
        rows.append(last)
    if not rows:
        return pd.DataFrame()
    L = pd.concat(rows).replace([np.inf, -np.inf], np.nan)
    for f in fitur:
        if f not in L:
            L[f] = np.nan
    p_mentah = model.peluang(L)          # ModelProbabilitas memilih kolomnya sendiri
    L["peluang"] = kalibrator.predict(p_mentah) if kalibrator is not None else p_mentah
    return (L[["ticker", "close", "peluang"]]
            .sort_values("peluang", ascending=False).reset_index(drop=True))
