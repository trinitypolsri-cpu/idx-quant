"""Apakah BSJP layak pada saham berharga tinggi, di mana gesekan tick kecil?

Fraksi harga IDX absolut, jadi tick% mengecil drastis di harga tinggi:
    Rp140    -> 0,714% per tick
    Rp24.250 -> 0,103% per tick

Kalau sinyal "tutup kuat + volume + naik" memberi ~0,54% overnight, ia mungkin
hanya menutup biaya pada tier harga tertinggi.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import setups as st
from idxquant.config import OUT_DIR, tick_size
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)

KOMISI = 0.0040
TIER = [(0, 200, "<200"), (200, 500, "200-500"), (500, 2000, "500-2rb"),
        (2000, 5000, "2rb-5rb"), (5000, 10**9, ">=5rb")]


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    scan = st.scan(prep)
    likuid = list(scan[scan["likuid"]]["ticker"])

    rows = []
    for t in likuid:
        d = prep.get(t)
        if d is None or len(d) < 300:
            continue
        x = d.copy()
        rng = (x["high"] - x["low"]).replace(0, np.nan)
        pos = (x["close"] - x["low"]) / rng
        vr = x["volume"] / x["volume"].rolling(20).mean().replace(0, np.nan)
        ret = x["close"] / x["close"].shift(1) - 1
        on = x["open"].shift(-1) / x["close"] - 1
        sinyal = (pos > 0.80) & (vr > 1.5) & (ret > 0.02)
        biaya = KOMISI + x["close"].apply(lambda p: tick_size(p) / p if p > 0 else 1)
        sub = pd.DataFrame({"ticker": t, "harga": x["close"], "on": on,
                            "biaya": biaya, "sinyal": sinyal.fillna(False)}).dropna()
        rows.append(sub)

    P = pd.concat(rows)
    S = P[P["sinyal"]]

    print("=" * 92)
    print(f"BSJP per TIER HARGA — sinyal 'tutup kuat + volume + naik>2%'")
    print(f"{len(S):,} sinyal dari {len(P):,} observasi")
    print("=" * 92)

    hasil = []
    for lo, hi, nama in TIER:
        sub = S[(S["harga"] >= lo) & (S["harga"] < hi)]
        if len(sub) < 80:
            hasil.append({"Tier harga": nama, "N": len(sub), "Catatan": "sampel kecil"})
            continue
        net = sub["on"] - sub["biaya"]
        hasil.append({
            "Tier harga": nama, "N": len(sub),
            "Harga median": round(float(sub["harga"].median())),
            "ON kotor%": round(float(sub["on"].mean()) * 100, 4),
            "Biaya%": round(float(sub["biaya"].mean()) * 100, 3),
            "ON net%": round(float(net.mean()) * 100, 4),
            "Menang net%": round(float((net > 0).mean()) * 100, 1),
            "t": round(float(sub["on"].mean() / (sub["on"].std(ddof=1) /
                       np.sqrt(len(sub)))), 2),
            "Layak": "YA" if net.mean() > 0 else "tidak",
        })
    print()
    print(pd.DataFrame(hasil).to_string(index=False))

    # Skenario komisi lebih murah
    print("\n" + "=" * 92)
    print("SKENARIO: BAGAIMANA KALAU KOMISI LEBIH MURAH?")
    print("=" * 92)
    print("\nBanyak broker menawarkan komisi lebih rendah untuk nasabah aktif.")
    print("Ini menghitung ambang di mana BSJP mulai masuk akal.\n")

    tinggi = S[S["harga"] >= 5000]
    if len(tinggi) >= 80:
        on_avg = float(tinggi["on"].mean())
        tick_avg = float((tinggi["biaya"] - KOMISI).mean())
        baris = []
        for beli, jual in [(0.0015, 0.0025), (0.0010, 0.0020), (0.0008, 0.0018),
                           (0.0005, 0.0015), (0.0000, 0.0010)]:
            kom = beli + jual
            net = on_avg - (kom + tick_avg)
            baris.append({
                "Komisi beli": f"{beli*100:.2f}%", "Komisi jual": f"{jual*100:.2f}%",
                "Total komisi": f"{kom*100:.2f}%",
                "+ gesekan tick": f"{tick_avg*100:.3f}%",
                "Biaya total": f"{(kom+tick_avg)*100:.3f}%",
                "ON net%": round(net * 100, 4),
                "Layak": "YA" if net > 0 else "tidak",
            })
        print(f"Pada saham >= Rp5.000 (overnight rata-rata {on_avg*100:.4f}%):\n")
        print(pd.DataFrame(baris).to_string(index=False))
        impas = on_avg - tick_avg
        print(f"\nKomisi bolak-balik harus di bawah {impas*100:.3f}% agar impas.")
        print(f"Komisi standar ritel 0,40% -> {'MASIH RUGI' if impas < 0.004 else 'bisa untung'}.")

    S.to_csv(OUT_DIR / "bsjp_tier.csv")
    print(f"\nDisimpan: {OUT_DIR / 'bsjp_tier.csv'}")


if __name__ == "__main__":
    main()
