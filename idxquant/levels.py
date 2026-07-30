"""Level perdagangan: pivot R1-R3 / S1-S3, support-resistance swing, dan TP/SL.

Semua level DIBULATKAN KE FRAKSI HARGA IDX. Ini bukan detail kosmetik: order pada
harga yang tidak kelipatan tick akan ditolak sistem bursa, jadi level yang tidak
dibulatkan tidak bisa dipakai untuk memasang order.

Level juga DIPOTONG oleh batas ARA/ARB. Target di atas batas ARA hari itu tidak
mungkin tercapai — harga tidak boleh melewatinya — jadi menampilkannya menyesatkan.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ar_limit, round_to_tick, tick_size


# ---------------------------------------------------------------- pivot
def pivot_klasik(high: float, low: float, close: float) -> dict:
    """Pivot klasik (floor trader) dari H/L/C periode sebelumnya."""
    pp = (high + low + close) / 3
    rng = high - low
    return {
        "PP": pp,
        "R1": 2 * pp - low, "S1": 2 * pp - high,
        "R2": pp + rng, "S2": pp - rng,
        "R3": high + 2 * (pp - low), "S3": low - 2 * (high - pp),
    }


def pivot_fibonacci(high: float, low: float, close: float) -> dict:
    pp = (high + low + close) / 3
    rng = high - low
    return {
        "PP": pp,
        "R1": pp + 0.382 * rng, "S1": pp - 0.382 * rng,
        "R2": pp + 0.618 * rng, "S2": pp - 0.618 * rng,
        "R3": pp + 1.000 * rng, "S3": pp - 1.000 * rng,
    }


def swing_levels(df: pd.DataFrame, lookback: int = 60, n: int = 3,
                 kiri: int = 2, kanan: int = 2) -> dict:
    """Support/resistance dari titik balik fraktal — level yang benar-benar diuji pasar.

    Lebih berguna daripada pivot rumus karena mencerminkan harga di mana transaksi
    nyata berbalik arah.
    """
    d = df.tail(lookback)
    if len(d) < kiri + kanan + 3:
        return {"resistance": [], "support": []}

    h, l = d["high"].to_numpy(), d["low"].to_numpy()
    res, sup = [], []
    for i in range(kiri, len(d) - kanan):
        if h[i] == max(h[i - kiri:i + kanan + 1]):
            res.append(float(h[i]))
        if l[i] == min(l[i - kiri:i + kanan + 1]):
            sup.append(float(l[i]))

    px = float(d["close"].iloc[-1])
    res = sorted({round_to_tick(x) for x in res if x > px})[:n]
    sup = sorted({round_to_tick(x) for x in sup if x < px}, reverse=True)[:n]
    return {"resistance": res, "support": sup}


# ---------------------------------------------------------------- TP / SL
def rencana_trade(entry: float, atr: float, prev_close: float | None = None,
                  support_terdekat: float | None = None,
                  sl_atr: float = 1.5, rr: tuple[float, ...] = (1.0, 2.0, 3.0),
                  maks_risiko_pct: float = 8.0) -> dict:
    """Susun stop loss dan target berbasis ATR, dibulatkan ke tick, dipotong ARA.

    SL memakai jarak ATR sebagai dasar. Support hanya dipakai bila LEBIH KETAT dari
    stop ATR namun masih memberi ruang, yaitu berada di antara 0,5x dan 1,5x jarak
    stop ATR. Support yang jauh di bawah diabaikan: pada saham yang baru melonjak,
    support teruji terdekat bisa 18% di bawah harga, dan memakainya sebagai stop
    berarti mempertaruhkan seperlima modal posisi untuk satu trade.

    Risiko juga dibatasi `maks_risiko_pct` — kalau stop wajar tidak tersedia, lebih
    baik posisinya dilewat daripada dipaksakan.
    """
    if not entry or entry <= 0 or not atr or atr <= 0:
        return {}

    jarak_atr = sl_atr * atr
    sl_atr_lvl = entry - jarak_atr
    sl, dasar_sl = sl_atr_lvl, "ATR"

    if support_terdekat and 0 < support_terdekat < entry:
        sl_sup = support_terdekat - tick_size(support_terdekat)
        jarak_sup = entry - sl_sup
        if 0.5 * jarak_atr <= jarak_sup <= 1.5 * jarak_atr:
            sl, dasar_sl = sl_sup, "support"

    # Batas risiko keras
    sl_maks = entry * (1 - maks_risiko_pct / 100)
    terpotong = sl < sl_maks
    if terpotong:
        sl, dasar_sl = sl_maks, f"batas {maks_risiko_pct:.0f}%"

    sl = round_to_tick(sl)
    risiko = entry - sl
    if risiko <= 0:
        return {}

    batas_ara = None
    if prev_close and prev_close > 0:
        batas_ara = round_to_tick(prev_close * (1 + ar_limit(prev_close)))

    tp = []
    for i, r in enumerate(rr, 1):
        lvl = round_to_tick(entry + r * risiko)
        kena_ara = bool(batas_ara and lvl > batas_ara)
        tp.append({
            "nama": f"TP{i}", "level": lvl, "rr": r,
            "gain_pct": round((lvl / entry - 1) * 100, 2),
            "di_atas_ara": kena_ara,
            "level_efektif": batas_ara if kena_ara else lvl,
        })

    return {
        "entry": round_to_tick(entry),
        "sl": sl,
        "dasar_sl": dasar_sl,
        "risiko_rp": round(risiko, 2),
        "risiko_pct": round(risiko / entry * 100, 2),
        "tick": tick_size(entry),
        "batas_ara": batas_ara,
        "tp": tp,
        "semua_tp_di_atas_ara": all(t["di_atas_ara"] for t in tp) if tp else False,
    }


def ukuran_posisi(modal: float, entry: float, sl: float,
                  risiko_pct: float = 0.01, lot: int = 100) -> dict:
    """Berapa lot yang boleh dibeli agar kerugian maksimum = risiko_pct dari modal."""
    risiko_per_lembar = entry - sl
    if risiko_per_lembar <= 0 or entry <= 0:
        return {}
    rupiah_risiko = modal * risiko_pct
    lembar = rupiah_risiko / risiko_per_lembar
    n_lot = int(lembar // lot)
    nilai = n_lot * lot * entry
    return {
        "modal": modal, "risiko_pct": risiko_pct * 100,
        "rupiah_risiko": round(rupiah_risiko, 0),
        "lot": n_lot, "lembar": n_lot * lot,
        "nilai_posisi": round(nilai, 0),
        "porsi_modal": round(nilai / modal * 100, 1) if modal else 0,
        "rugi_bila_sl": round(n_lot * lot * risiko_per_lembar, 0),
    }


# ---------------------------------------------------------------- gabungan
def analisa_level(df: pd.DataFrame, atr: float | None = None,
                  metode_pivot: str = "klasik", modal: float | None = None) -> dict:
    """Paket lengkap level untuk satu emiten dari data harian."""
    if df is None or len(df) < 5:
        return {}

    prev = df.iloc[-2]
    last = df.iloc[-1]
    px = float(last["close"])

    piv_fn = pivot_fibonacci if metode_pivot == "fibonacci" else pivot_klasik
    raw = piv_fn(float(prev["high"]), float(prev["low"]), float(prev["close"]))
    piv = {k: round_to_tick(v) for k, v in raw.items()}

    sw = swing_levels(df)

    if atr is None:
        tr = pd.concat([df["high"] - df["low"],
                        (df["high"] - df["close"].shift()).abs(),
                        (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean())

    sup_dekat = sw["support"][0] if sw["support"] else None
    plan = rencana_trade(px, atr, prev_close=float(prev["close"]),
                         support_terdekat=sup_dekat)

    # Level mana yang sedang ditembus / didekati
    posisi = "di atas PP" if px > piv["PP"] else "di bawah PP"
    berikut_atas = min([v for k, v in piv.items()
                        if k.startswith("R") and v > px], default=None)
    berikut_bawah = max([v for k, v in piv.items()
                         if k.startswith("S") and v < px], default=None)

    out = {
        "harga": px, "atr": round(atr, 2), "metode_pivot": metode_pivot,
        "pivot": piv, "swing": sw, "posisi": posisi,
        "resisten_berikut": berikut_atas, "support_berikut": berikut_bawah,
        "jarak_resisten_pct": (round((berikut_atas / px - 1) * 100, 2)
                               if berikut_atas else None),
        "jarak_support_pct": (round((berikut_bawah / px - 1) * 100, 2)
                              if berikut_bawah else None),
        "rencana": plan,
    }
    if modal and plan:
        out["sizing"] = ukuran_posisi(modal, plan["entry"], plan["sl"])
    return out


def format_teks(ticker: str, a: dict) -> str:
    """Ringkasan level untuk notifikasi Telegram/ntfy."""
    if not a:
        return ""
    p, r = a["pivot"], a.get("rencana") or {}
    rp = lambda v: f"{v:,.0f}".replace(",", ".")               # noqa: E731

    px = a["harga"]
    baris = [f"Harga {rp(px)} ({a['posisi']})", ""]

    # Level yang sudah dilewati harga bukan lagi resistance — tandai supaya tidak
    # dibaca terbalik. Pivot di bawah harga kini berperan sebagai support.
    dilewati = [k for k in ("R1", "R2", "R3") if p[k] < px]
    for k in ("R3", "R2", "R1", "PP", "S1", "S2", "S3"):
        v = p[k]
        if v < px and k.startswith("R"):
            baris.append(f"{k} {rp(v)}  (sudah dilewati -> jadi support)")
        elif v > px and k.startswith("S"):
            baris.append(f"{k} {rp(v)}  (di atas harga)")
        else:
            baris.append(f"{k} {rp(v)}")
    if len(dilewati) == 3:
        baris.append("")
        baris.append("Catatan: harga di atas SELURUH pivot resistance — pivot harian "
                     "tidak lagi memberi target ke atas. Pakai swing S/R di bawah.")

    if r:
        baris += ["", f"Entry {rp(r['entry'])} · SL {rp(r['sl'])} "
                      f"(-{r['risiko_pct']}%, dasar {r['dasar_sl']})"]
        for t in r["tp"]:
            tanda = "  [DI ATAS ARA - tak tercapai hari ini]" if t["di_atas_ara"] else ""
            baris.append(f"{t['nama']} {rp(t['level'])} (+{t['gain_pct']}%, "
                         f"RR {t['rr']:.0f}){tanda}")
        if r.get("batas_ara"):
            baris.append(f"Batas ARA hari ini {rp(r['batas_ara'])}")
        if r.get("semua_tp_di_atas_ara"):
            baris.append("PERINGATAN: semua TP di atas batas ARA — target hanya bisa "
                         "dicapai lintas hari, bukan intraday.")
    sw = a.get("swing") or {}
    if sw.get("resistance") or sw.get("support"):
        baris += ["", "Swing S/R teruji:"]
        if sw.get("resistance"):
            baris.append("  R: " + ", ".join(rp(x) for x in sw["resistance"]))
        if sw.get("support"):
            baris.append("  S: " + ", ".join(rp(x) for x in sw["support"]))
    return "\n".join(baris)
