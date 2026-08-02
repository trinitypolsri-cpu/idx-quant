"""Uji apakah metode yang dibangun untuk IDX bekerja di emas (XAUUSD).

Bukan opini — dijalankan ulang dengan mesin yang sama, lalu dibandingkan langsung
dengan IHSG. Yang diuji:

  1. Dekomposisi overnight vs intraday (setara BSJP)
  2. Struktur biaya — inti mengapa BSJP gagal di IDX
  3. Lompatan harga (Lee-Mykland) & memori pasar (Hurst, Ljung-Box)
  4. Volatilitas dan profil ekor
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import overnight as ov
from idxquant import portfolio as pf
from idxquant import timeseries as ts
from idxquant.config import OUT_DIR

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)

KANDIDAT = {
    "Emas spot (XAUUSD)": "XAUUSD=X",
    "Emas futures (GC=F)": "GC=F",
    "IHSG": "^JKSE",
    "BBCA (pembanding IDX)": "BBCA.JK",
}

# Biaya sekali putar, sumber berbeda:
#   IDX  = komisi 0,15%+0,25% + silang spread (dihitung dari fraksi harga)
#   XAU  = spread broker khas 0,02-0,05 USD pada harga ~2000-4000 -> ~0,001-0,003%
BIAYA = {
    "Emas spot (XAUUSD)": 0.00025,     # ~2,5 bp, spread ritel khas 20-30 sen
    "Emas futures (GC=F)": 0.00010,    # 1 bp, spread bursa lebih ketat
    "IHSG": 0.0040,                    # tidak bisa ditransaksikan langsung; acuan saja
    "BBCA (pembanding IDX)": 0.0079,   # komisi + 1 tick pada harga 6450
}


def main():
    print("=" * 96)
    print("APAKAH METODE IDX BEKERJA DI EMAS? — pengujian langsung")
    print("=" * 96)

    data = {}
    for nama, sym in KANDIDAT.items():
        d = dl.fetch_one(sym, rng="10y", interval="1d")
        cek = dl.periksa_resolusi(d, "1d") if d is not None else {"ok": False}
        if d is None or not cek.get("ok"):
            print(f"  lewati {nama} ({sym}) — {cek.get('alasan','tidak tersedia')}")
            continue
        data[nama] = d
        print(f"  {nama:24} {len(d):5} bar  {d.index[0].date()} .. {d.index[-1].date()}")

    if not data:
        print("Tidak ada data."); return

    # ---------- 1. Overnight vs intraday ----------
    print("\n" + "=" * 96)
    print("1. DEKOMPOSISI OVERNIGHT vs INTRADAY (setara BSJP)")
    print("=" * 96)
    rows = []
    for nama, d in data.items():
        p = ov.pecah(d)
        if len(p) < 100:
            continue
        b = BIAYA[nama]
        on, idr = p["overnight"], p["intraday"]
        rows.append({
            "Instrumen": nama, "N": len(p),
            "ON kotor%": round(float(on.mean()) * 100, 4),
            "ID kotor%": round(float(idr.mean()) * 100, 4),
            "Biaya putar%": round(b * 100, 4),
            "ON net%": round((float(on.mean()) - b) * 100, 4),
            "Rasio ON/biaya": round(abs(float(on.mean())) / b, 2) if b else np.nan,
            "Layak": "YA" if float(on.mean()) > b else "tidak",
        })
    t1 = pd.DataFrame(rows)
    print()
    print(t1.to_string(index=False))
    print("\nRasio ON/biaya > 1 berarti gerak overnight menutup biaya transaksi.")
    print("Di IDX rasio ini 0,26x — itulah sebab BSJP mustahil di sana.")

    # ---------- 2. Lompatan & memori ----------
    print("\n" + "=" * 96)
    print("2. LOMPATAN HARGA & MEMORI PASAR")
    print("=" * 96)
    rows = []
    for nama, d in data.items():
        r = ts.ringkas(nama, d)
        rows.append({
            "Instrumen": nama,
            "Vol EWMA%": r["vol_ewma%"],
            "Lompatan/thn": r["lompatan_per_thn"],
            "Naik": r["lompatan_naik"], "Turun": r["lompatan_turun"],
            "Hurst": r["hurst"],
            "Ljung p": r["ljung_p"],
        })
    t2 = pd.DataFrame(rows)
    print()
    print(t2.to_string(index=False))
    print("\nHurst >0,5 = tren berlanjut · <0,5 = balik arah · ~0,5 = jalan acak")
    print("Ljung p <0,05 = ada autokorelasi yang bisa dieksploitasi")

    # ---------- 3. Risiko ekor ----------
    print("\n" + "=" * 96)
    print("3. PROFIL RISIKO & EKOR")
    print("=" * 96)
    rows = []
    for nama, d in data.items():
        r = d["close"].pct_change().dropna()
        from scipy.stats import kurtosis, skew
        rows.append({
            "Instrumen": nama,
            "Vol tahunan%": round(float(r.std(ddof=1)) * np.sqrt(252) * 100, 1),
            "Skew": round(float(skew(r)), 2),
            "Kurtosis": round(float(kurtosis(r, fisher=True)), 1),
            "VaR95%": round(pf.var_historis(r) * 100, 3),
            "CVaR95%": round(pf.cvar_historis(r) * 100, 3),
            "Hari terburuk%": round(float(r.min()) * 100, 1),
        })
    t3 = pd.DataFrame(rows)
    print()
    print(t3.to_string(index=False))

    # ---------- vonis ----------
    print("\n" + "=" * 96)
    print("VONIS")
    print("=" * 96)
    emas = t1[t1["Instrumen"].str.contains("Emas")]
    idx = t1[~t1["Instrumen"].str.contains("Emas")]
    if len(emas) and len(idx):
        print(f"\n  Rasio ON/biaya emas  : {emas['Rasio ON/biaya'].max():.1f}x")
        print(f"  Rasio ON/biaya IDX   : {idx['Rasio ON/biaya'].max():.2f}x")
        lipat = emas["Rasio ON/biaya"].max() / max(idx["Rasio ON/biaya"].max(), 1e-9)
        print(f"  Emas {lipat:.0f}x lebih ramah terhadap strategi frekuensi tinggi,")
        print("  semata karena strukturnya biaya, bukan karena gerakannya lebih besar.")

    t1.to_csv(OUT_DIR / "xau_bsjp.csv", index=False)
    t2.to_csv(OUT_DIR / "xau_timeseries.csv", index=False)
    t3.to_csv(OUT_DIR / "xau_risiko.csv", index=False)
    print(f"\nDisimpan: xau_bsjp.csv, xau_timeseries.csv, xau_risiko.csv")


if __name__ == "__main__":
    main()
