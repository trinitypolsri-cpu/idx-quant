"""BSJP kondisional — apakah ada HARI TERTENTU yang overnight-nya menutup biaya?

Rata-rata seluruh hari sudah terbukti kalah biaya. Tapi strategi bersinyal tidak
masuk setiap hari. Pertanyaan sebenarnya: adakah kondisi penutupan sore yang membuat
return overnight cukup besar untuk melampaui ~0,8% biaya sekali putar?

Kondisi yang diuji (semua diketahui SEBELUM penutupan, jadi bisa dieksekusi):
  - Penutupan kuat  : close di 20% teratas rentang harian
  - Volume naik     : volume > 1,5x rata-rata 20 hari
  - Momentum        : naik >2% hari itu
  - ARA             : menyentuh batas auto-rejection atas
  - Gabungan        : kuat + volume
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import setups as st
from idxquant.config import OUT_DIR, ar_limit, tick_size
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)

BIAYA_KOMISI = 0.0040


def siapkan(d: pd.DataFrame) -> pd.DataFrame:
    x = d.copy()
    rng = (x["high"] - x["low"]).replace(0, np.nan)
    x["pos_close"] = (x["close"] - x["low"]) / rng          # 1 = tutup di puncak
    x["vol20"] = x["volume"].rolling(20).mean()
    x["vol_ratio"] = x["volume"] / x["vol20"].replace(0, np.nan)
    x["ret_hari"] = x["close"] / x["close"].shift(1) - 1
    x["overnight"] = x["open"].shift(-1) / x["close"] - 1     # dieksekusi besok pagi
    x["ara_limit"] = x["close"].shift(1).apply(
        lambda p: ar_limit(p) if p and p > 0 else np.nan)
    x["kena_ara"] = x["ret_hari"] >= x["ara_limit"] * 0.98
    x["biaya"] = BIAYA_KOMISI + x["close"].apply(
        lambda p: tick_size(p) / p if p > 0 else 1)
    return x.dropna(subset=["overnight", "pos_close"])


KONDISI = {
    "Semua hari":        lambda x: pd.Series(True, index=x.index),
    "Tutup kuat (>80%)": lambda x: x["pos_close"] > 0.80,
    "Volume >1,5x":      lambda x: x["vol_ratio"] > 1.5,
    "Naik >2%":          lambda x: x["ret_hari"] > 0.02,
    "Kena ARA":          lambda x: x["kena_ara"],
    "Kuat + volume":     lambda x: (x["pos_close"] > 0.80) & (x["vol_ratio"] > 1.5),
    "Kuat + vol + naik": lambda x: ((x["pos_close"] > 0.80) & (x["vol_ratio"] > 1.5)
                                    & (x["ret_hari"] > 0.02)),
}


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    scan = st.scan(prep)
    likuid = list(scan[scan["likuid"]]["ticker"])

    semua = []
    for t in likuid:
        d = prep.get(t)
        if d is None or len(d) < 300:
            continue
        x = siapkan(d)
        x["ticker"] = t
        semua.append(x[["ticker", "overnight", "pos_close", "vol_ratio",
                        "ret_hari", "kena_ara", "biaya"]])
    if not semua:
        print("Data tidak cukup.")
        return
    P = pd.concat(semua)

    print("=" * 96)
    print(f"BSJP KONDISIONAL — {len(likuid)} emiten likuid, {len(P):,} observasi hari-emiten")
    print("=" * 96)
    print("\nReturn OVERNIGHT (beli di penutupan, jual di pembukaan besok):\n")

    baris = []
    for nama, fn in KONDISI.items():
        m = fn(P).fillna(False)
        sub = P[m]
        if len(sub) < 100:
            baris.append({"Kondisi": nama, "N": len(sub), "Catatan": "sampel terlalu kecil"})
            continue
        r = sub["overnight"]
        biaya = sub["biaya"]
        net = r - biaya
        baris.append({
            "Kondisi": nama,
            "N": len(sub),
            "%hari": round(len(sub) / len(P) * 100, 1),
            "ON kotor%": round(float(r.mean()) * 100, 4),
            "Biaya%": round(float(biaya.mean()) * 100, 3),
            "ON net%": round(float(net.mean()) * 100, 4),
            "Menang%": round(float((r > 0).mean()) * 100, 1),
            "Menang net%": round(float((net > 0).mean()) * 100, 1),
            "t": round(float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))), 2),
            "Layak": "YA" if net.mean() > 0 else "tidak",
        })
    tab = pd.DataFrame(baris)
    print(tab.to_string(index=False))

    # Seberapa besar overnight yang DIBUTUHKAN agar layak?
    biaya_med = float(P["biaya"].median()) * 100
    print(f"\nAmbang impas: overnight harus > {biaya_med:.3f}% agar sekadar balik modal.")

    terbaik = tab[tab.get("ON kotor%").notna()].nlargest(1, "ON kotor%") if "ON kotor%" in tab else None
    if terbaik is not None and len(terbaik):
        b = terbaik.iloc[0]
        print(f"Kondisi terbaik  : {b['Kondisi']} -> {b['ON kotor%']}% kotor "
              f"({b['ON kotor%'] / biaya_med:.2f}x biaya)")

    # Berapa lama harus ditahan agar biaya tertutup?
    print("\n" + "=" * 96)
    print("ALTERNATIF: TAHAN LEBIH LAMA, BUKAN PUTAR TIAP HARI")
    print("=" * 96)
    hari_ret = P.groupby(P.index)["overnight"].mean()
    med_daily = float(P["ret_hari"].median()) * 100
    med_on = float(P["overnight"].median()) * 100
    print(f"\nMedian return harian total : {med_daily:+.4f}%/hari")
    print(f"Median return overnight    : {med_on:+.4f}%/hari")
    print(f"Biaya sekali putar         : {biaya_med:.3f}%")
    if med_daily > 0:
        n = biaya_med / med_daily
        print(f"\nDitahan {n:.0f} hari bursa, biaya sekali putar sudah tertutup "
              f"oleh akumulasi drift.")
        print("Semakin lama ditahan, semakin kecil porsi biaya — inilah alasan")
        print("frekuensi rendah mengalahkan frekuensi tinggi di IDX.")

    P.to_csv(OUT_DIR / "bsjp_kondisional.csv")
    print(f"\nDisimpan: {OUT_DIR / 'bsjp_kondisional.csv'}")


if __name__ == "__main__":
    main()
