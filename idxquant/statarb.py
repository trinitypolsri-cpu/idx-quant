"""Statistical arbitrage — mencari pasangan saham yang bergerak bersama.

!!! HASIL BELUM SAHIH — JANGAN DIPAKAI UNTUK KEPUTUSAN !!!
Backtest saat ini memilih pasangan memakai uji ADF pada SELURUH sampel, lalu
menguji pada sampel yang sama. Pasangan yang terbukti kointegrasi sepanjang
periode itu pasti mean-revert di dalamnya — hasilnya (+12%/trade, hit rate
mendekati 100%) adalah artefak seleksi, bukan edge.

Yang harus dikerjakan sebelum angka ini berarti:
  1. Pilih pasangan HANYA dari periode latih (mis. 2 tahun pertama)
  2. Backtest pada periode berikutnya yang belum pernah dilihat
  3. Geser jendela, ulangi (walk-forward seperti run_walkforward.py)
  4. Bandingkan dengan pasangan ACAK sesektor sebagai kontrol

Tiga bug sudah ditemukan dan diperbaiki saat membangun ini — tanda P&L terbalik,
trade yang tidak pernah tutup tidak tercatat, dan tidak adanya stop. Cacat
keempat (seleksi look-ahead) masih ada.


Ini pendekatan inti stat-arb fund dan SATU-SATUNYA dari gaya Citadel/Renaissance
yang benar-benar bisa diuji dengan data yang ada. Bedanya mendasar dari seluruh
isi proyek ini: semua yang lain adalah momentum searah (beli yang naik), ini
mencari HUBUNGAN antar dua saham lalu bertaruh pada kembalinya selisih.

Logikanya: bila dua saham digerakkan faktor ekonomi yang sama (mis. dua bank, dua
emiten batubara), rasio harganya seharusnya stabil. Ketika rasio itu melenceng
jauh dari normalnya, ia cenderung kembali.

Uji yang dipakai:
  Engle-Granger  regresi A terhadap B, lalu uji apakah residualnya stasioner.
                 Kalau stasioner -> pasangan terkointegrasi.
  ADF            uji akar unit pada residual (implementasi ringan, tanpa statsmodels)
  Half-life      seberapa cepat selisih kembali ke rata-rata (proses Ornstein-Uhlenbeck)

BATASAN BESAR UNTUK RITEL IDX: short selling tidak tersedia. Stat-arb sejati
butuh long A + short B. Karena itu modul ini juga menguji versi LONG-ONLY —
hanya membeli sisi yang murah — dan hasilnya harus dibandingkan jujur, karena
versi long-only kehilangan sifat netral-pasarnya.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def adf_ringkas(x: np.ndarray, lag: int = 1) -> float:
    """Statistik ADF sederhana. Makin negatif, makin kuat bukti stasioner.

    Ambang kritis kira-kira: -3,4 (1%), -2,9 (5%), -2,6 (10%).
    """
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 30:
        return np.nan
    dx = np.diff(x)
    X = [x[:-1]]
    for i in range(1, lag + 1):
        X.append(np.concatenate([np.zeros(i), dx[:-i]])[: len(dx)])
    X = np.column_stack([np.ones(len(dx))] + X)
    y = dx
    n = min(len(y), X.shape[0])
    X, y = X[:n], y[:n]
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        s2 = (resid ** 2).sum() / (n - X.shape[1])
        se = np.sqrt(np.diag(s2 * np.linalg.pinv(X.T @ X)))
        return float(beta[1] / se[1])
    except Exception:                                              # noqa: BLE001
        return np.nan


def half_life(spread: np.ndarray) -> float:
    """Waktu paruh kembalinya selisih ke rata-rata, dalam hari bursa."""
    s = np.asarray(spread, float)
    s = s[np.isfinite(s)]
    if len(s) < 30:
        return np.nan
    ds = np.diff(s)
    lag = s[:-1]
    X = np.column_stack([np.ones(len(lag)), lag])
    try:
        beta, *_ = np.linalg.lstsq(X, ds, rcond=None)
        if beta[1] >= 0:
            return np.inf              # tidak kembali — bukan mean reverting
        return float(-np.log(2) / beta[1])
    except Exception:                                              # noqa: BLE001
        return np.nan


def uji_pasangan(a: pd.Series, b: pd.Series, min_bar: int = 250) -> dict | None:
    """Engle-Granger: regresi log harga, lalu uji stasioneritas residual."""
    d = pd.concat([np.log(a).rename("a"), np.log(b).rename("b")], axis=1).dropna()
    if len(d) < min_bar:
        return None
    X = np.column_stack([np.ones(len(d)), d["b"].to_numpy()])
    y = d["a"].to_numpy()
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    spread = y - X @ beta
    adf = adf_ringkas(spread)
    hl = half_life(spread)
    return {
        "hedge_ratio": float(beta[1]),
        "adf": adf,
        "half_life": hl,
        "korelasi": float(d["a"].diff().corr(d["b"].diff())),
        "spread_sd": float(np.std(spread, ddof=1)),
        "z_terakhir": float((spread[-1] - spread.mean()) / np.std(spread, ddof=1)),
        "n": len(d),
        "_spread": pd.Series(spread, index=d.index),
    }


def cari_pasangan(harga: pd.DataFrame, maks_pasangan: int = 40,
                  adf_ambang: float = -2.9, hl_min: float = 2,
                  hl_maks: float = 60, sektor: dict[str, str] | None = None,
                  hanya_sesektor: bool = True) -> pd.DataFrame:
    """Pindai seluruh kombinasi pasangan, kembalikan yang terkointegrasi.

    `hanya_sesektor` sangat disarankan: pasangan lintas sektor yang lolos uji
    statistik sering kebetulan belaka. Kointegrasi tanpa alasan ekonomi adalah
    definisi data mining.
    """
    kol = list(harga.columns)
    rows = []
    for i in range(len(kol)):
        for j in range(i + 1, len(kol)):
            ta, tb = kol[i], kol[j]
            if hanya_sesektor and sektor:
                if sektor.get(ta) != sektor.get(tb):
                    continue
            r = uji_pasangan(harga[ta], harga[tb])
            if not r or not np.isfinite(r["adf"]):
                continue
            if r["adf"] > adf_ambang:
                continue
            if not (hl_min <= r["half_life"] <= hl_maks):
                continue
            rows.append({"a": ta, "b": tb,
                         "sektor": (sektor or {}).get(ta, "-"),
                         "adf": round(r["adf"], 2),
                         "half_life": round(r["half_life"], 1),
                         "korelasi": round(r["korelasi"], 3),
                         "hedge_ratio": round(r["hedge_ratio"], 3),
                         "z_sekarang": round(r["z_terakhir"], 2),
                         "n": r["n"]})
    df = pd.DataFrame(rows)
    return df.sort_values("adf").head(maks_pasangan) if len(df) else df


def backtest_pasangan(a: pd.Series, b: pd.Series, hedge: float,
                      masuk_z: float = 2.0, keluar_z: float = 0.5,
                      stop_z: float = 4.0, tahan_maks: int = 60,
                      biaya: float = 0.0083, long_only: bool = False,
                      lookback: int = 60) -> dict:
    """Backtest satu pasangan dengan z-score bergulir (bukan seluruh sampel).

    Memakai rata-rata & simpangan BERGULIR, bukan statistik seluruh periode —
    memakai statistik penuh berarti melihat masa depan.

    `biaya` 0,83% mencerminkan sekali putar di IDX. Untuk versi long-short,
    biayanya DUA KALI karena dua kaki.
    """
    d = pd.concat([np.log(a).rename("a"), np.log(b).rename("b")], axis=1).dropna()
    if len(d) < lookback + 60:
        return {}
    spread = d["a"] - hedge * d["b"]
    mu = spread.rolling(lookback).mean()
    sd = spread.rolling(lookback).std(ddof=1)
    z = (spread - mu) / sd.replace(0, np.nan)

    posisi, entry_z, trades = 0, None, []
    n_kaki = 1 if long_only else 2
    for i in range(lookback, len(d)):
        zi = z.iloc[i]
        if not np.isfinite(zi):
            continue
        if posisi == 0:
            if zi <= -masuk_z:                 # spread terlalu rendah -> beli A
                posisi, entry_z, idx_masuk = 1, zi, i
            elif zi >= masuk_z and not long_only:
                posisi, entry_z, idx_masuk = -1, zi, i
        else:
            # Tiga alasan keluar. Tanpa stop dan batas waktu, posisi yang spread-nya
            # TIDAK pernah kembali akan menggantung selamanya dan tidak pernah
            # tercatat sebagai trade — sehingga hanya reversi yang berhasil yang
            # masuk hitungan. Itu menghasilkan hit rate 100% palsu di semua pasangan.
            balik = abs(zi) <= keluar_z
            kena_stop = abs(zi) >= stop_z and np.sign(zi) == -np.sign(entry_z or 1)
            kena_stop = kena_stop or (abs(zi) >= stop_z and abs(zi) > abs(entry_z))
            habis_waktu = (i - idx_masuk) >= tahan_maks
            if balik or kena_stop or habis_waktu:
                # Laba = (spread keluar - spread masuk) x arah posisi.
                # Versi awal menulisnya terbalik: (masuk - keluar), sehingga
                # SETIAP trade rugi — 0 dari 40 pasangan untung dengan return
                # kotor -15%. Itu mustahil sebagai hasil pasar dan menjadi
                # petunjuk adanya kesalahan tanda.
                gerak = (zi - entry_z) * sd.iloc[i] * posisi
                alasan = "reversi" if balik else ("stop" if kena_stop else "waktu")
                trades.append({"masuk": d.index[idx_masuk], "keluar": d.index[i],
                               "alasan": alasan,
                               "z_masuk": entry_z, "z_keluar": zi,
                               "ret_kotor": float(gerak),
                               "ret_net": float(gerak - biaya * n_kaki),
                               "hari": i - idx_masuk})
                posisi, entry_z = 0, None

    # Posisi yang masih terbuka di akhir data HARUS dicatat, bukan diabaikan.
    if posisi != 0 and entry_z is not None:
        zi = z.iloc[-1]
        if np.isfinite(zi):
            gerak = (zi - entry_z) * sd.iloc[-1] * posisi
            trades.append({"masuk": d.index[idx_masuk], "keluar": d.index[-1],
                           "alasan": "belum tutup", "z_masuk": entry_z, "z_keluar": zi,
                           "ret_kotor": float(gerak),
                           "ret_net": float(gerak - biaya * n_kaki),
                           "hari": len(d) - 1 - idx_masuk})

    if not trades:
        return {"n_trade": 0}
    tr = pd.DataFrame(trades)
    return {
        "n_trade": len(tr),
        "ret_kotor_rata": float(tr["ret_kotor"].mean()),
        "ret_net_rata": float(tr["ret_net"].mean()),
        "menang_net": float((tr["ret_net"] > 0).mean()),
        "total_net": float(tr["ret_net"].sum()),
        "hari_rata": float(tr["hari"].mean()),
        "_trades": tr,
    }
