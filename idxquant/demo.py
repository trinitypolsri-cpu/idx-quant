"""Simulasi portofolio demo — membeli saham yang direkomendasikan sistem.

Menjawab pertanyaan paling penting: kalau saya benar-benar membeli apa yang
direkomendasikan, hasilnya berapa?

Berbeda dari backtest rotasi yang sudah ada, simulasi ini mengikuti ATURAN YANG
DIPAKAI APLIKASI HARI INI — setup yang sama, filter likuiditas yang sama, biaya
yang sama, dan stop yang sama. Jadi hasilnya bisa dibandingkan langsung dengan apa
yang Anda lihat di layar, bukan dengan strategi teoretis yang berbeda.

Yang dihitung realistis untuk IDX:
  - lot 100 lembar (sisa dana jadi kas, tidak dipaksakan)
  - komisi 0,15% beli + 0,25% jual, slippage 0,15% per sisi
  - eksekusi di OPEN hari berikutnya setelah sinyal (bukan di harga sinyal)
  - stop loss chandelier berbasis ATR
  - batas jumlah posisi bersamaan
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FEE_BUY, FEE_SELL, LOT_SIZE, SLIPPAGE, TRADING_DAYS


def simulasi(prepared: dict[str, pd.DataFrame], bench: pd.DataFrame,
             setup: str = "FVGBullish", modal: float = 100_000_000,
             maks_posisi: int = 5, stop_atr: float = 3.0,
             tahan_maks: int = 21, likuid: set[str] | None = None,
             mulai_dari: str | None = None) -> dict:
    """Beli tiap kali `setup` menyala, sampai batas posisi. Jual saat stop/waktu habis.

    `setup` bisa nama satu setup, atau 'apa_saja' untuk semua sinyal.
    """
    kol = f"sig_{setup}"
    tanggal = sorted({d for t, x in prepared.items() for d in x.index})
    if mulai_dari:
        tanggal = [d for d in tanggal if d >= pd.Timestamp(mulai_dari)]
    if not tanggal:
        return {}

    # Panel harga penutup yang di-forward-fill. WAJIB: kalender gabungan seluruh
    # emiten memuat tanggal yang tidak dimiliki sebagian emiten (suspensi, beda
    # jadwal). Tanpa ffill, posisi pada tanggal itu bernilai NOL dan kurva ekuitas
    # anjlok semu — sempat menghasilkan MaxDD -99,8% yang tidak nyata.
    idx = pd.DatetimeIndex(tanggal)
    panel = pd.DataFrame(
        {t: x["close"] for t, x in prepared.items()}).reindex(idx).ffill()

    kas = modal
    posisi: dict[str, dict] = {}
    riwayat, ekuitas, antre = [], [], []

    for i, hari in enumerate(tanggal):
        # --- eksekusi pembelian yang diputuskan kemarin, di OPEN hari ini ---
        for t in antre:
            if t in posisi or len(posisi) >= maks_posisi:
                continue
            d = prepared.get(t)
            if d is None or hari not in d.index:
                continue
            r = d.loc[hari]
            harga = float(r["open"]) * (1 + SLIPPAGE)
            if not np.isfinite(harga) or harga <= 0:
                continue
            slot = (kas + sum(p["lembar"] * float(panel.loc[hari, k])
                              for k, p in posisi.items()
                              if pd.notna(panel.loc[hari, k]))) / maks_posisi
            lot = int(min(slot, kas * 0.98) // (harga * LOT_SIZE * (1 + FEE_BUY)))
            if lot < 1:
                continue
            lembar = lot * LOT_SIZE
            biaya = lembar * harga * (1 + FEE_BUY)
            if biaya > kas:
                continue
            kas -= biaya
            atr = float(r.get("atr14", harga * 0.03))
            posisi[t] = {"lembar": lembar, "entry": harga, "tgl": hari,
                         "stop": harga - stop_atr * atr, "puncak": harga}
        antre = []

        # --- kelola posisi terbuka ---
        for t in list(posisi):
            d = prepared.get(t)
            if d is None or hari not in d.index:
                continue
            r = d.loc[hari]
            p = posisi[t]
            atr = float(r.get("atr14", p["entry"] * 0.03))
            p["puncak"] = max(p["puncak"], float(r["high"]))
            p["stop"] = max(p["stop"], p["puncak"] - stop_atr * atr)

            umur = len([x for x in tanggal[:i + 1] if x > p["tgl"]])
            kena_stop = float(r["low"]) <= p["stop"]
            habis_waktu = umur >= tahan_maks
            if kena_stop or habis_waktu:
                keluar = (p["stop"] if kena_stop else float(r["close"])) * (1 - SLIPPAGE)
                hasil = p["lembar"] * keluar * (1 - FEE_SELL)
                modal_awal = p["lembar"] * p["entry"] * (1 + FEE_BUY)
                kas += hasil
                riwayat.append({
                    "ticker": t, "masuk": p["tgl"], "keluar": hari,
                    "harga_masuk": round(p["entry"]), "harga_keluar": round(keluar),
                    "lembar": p["lembar"], "pnl": round(hasil - modal_awal),
                    "ret": hasil / modal_awal - 1, "hari": umur,
                    "alasan": "stop" if kena_stop else "waktu"})
                del posisi[t]

        # --- nilai portofolio ---
        # Pakai panel ber-ffill, bukan indeks per-emiten: posisi yang emitennya
        # tidak punya bar hari itu tetap dinilai dengan harga terakhir.
        mv = sum(p["lembar"] * float(panel.loc[hari, t])
                 for t, p in posisi.items() if pd.notna(panel.loc[hari, t]))
        ekuitas.append({"tgl": hari, "nilai": kas + mv,
                        "kas": kas, "posisi": len(posisi)})

        # --- cari sinyal baru untuk besok ---
        if len(posisi) < maks_posisi and i < len(tanggal) - 1:
            kandidat = []
            for t, d in prepared.items():
                if likuid and t not in likuid:
                    continue
                if t in posisi or hari not in d.index:
                    continue
                r = d.loc[hari]
                if setup == "apa_saja":
                    nyala = any(bool(r.get(c, False)) for c in d.columns
                                if c.startswith("sig_"))
                else:
                    nyala = bool(r.get(kol, False))
                if nyala:
                    kandidat.append((t, float(r.get("roc63", 0) or 0)))
            kandidat.sort(key=lambda x: -x[1])
            antre = [t for t, _ in kandidat[:maks_posisi - len(posisi)]]

    eq = pd.DataFrame(ekuitas).set_index("tgl")["nilai"]
    tr = pd.DataFrame(riwayat)
    return {"ekuitas": eq, "trade": tr, "modal": modal,
            "metrik": _metrik(eq, tr, modal)}


def _metrik(eq: pd.Series, tr: pd.DataFrame, modal: float) -> dict:
    if eq.empty:
        return {}
    total = eq.iloc[-1] / modal - 1
    tahun = len(eq) / TRADING_DAYS
    ret = eq.pct_change().dropna()
    dd = (eq / eq.cummax() - 1).min()
    m = {
        "nilai_akhir": round(float(eq.iloc[-1])),
        "laba_rugi": round(float(eq.iloc[-1] - modal)),
        "total_return": total,
        "cagr": (eq.iloc[-1] / modal) ** (1 / tahun) - 1 if tahun > 0 else np.nan,
        "maxdd": float(dd),
        "vol": float(ret.std(ddof=0) * np.sqrt(TRADING_DAYS)) if len(ret) > 1 else np.nan,
        "n_trade": len(tr),
    }
    if len(tr):
        menang = tr[tr["ret"] > 0]
        kalah = tr[tr["ret"] <= 0]
        m.update({
            "hit_rate": len(menang) / len(tr),
            "avg_menang": float(menang["ret"].mean()) if len(menang) else np.nan,
            "avg_kalah": float(kalah["ret"].mean()) if len(kalah) else np.nan,
            "profit_factor": (menang["pnl"].sum() / abs(kalah["pnl"].sum()))
                             if len(kalah) and kalah["pnl"].sum() else np.inf,
            "hari_rata": float(tr["hari"].mean()),
            "keluar_stop": float((tr["alasan"] == "stop").mean()),
        })
    return m
