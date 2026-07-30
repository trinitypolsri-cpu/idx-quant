"""Cari saham yang cocok untuk BSJP (beli sore jual pagi) atau BPJS (beli pagi jual sore)."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import overnight as ov
from idxquant import setups as st
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    scan_h = st.scan(prep)
    likuid = list(scan_h[scan_h["likuid"]]["ticker"])

    print("=" * 104)
    print(f"BSJP vs BPJS — dekomposisi return {len(likuid)} emiten likuid, 5 tahun")
    print("=" * 104)

    df = ov.scan(prep, likuid=likuid)
    if df.empty:
        print("Data tidak cukup.")
        return

    # --- gambaran besar ---
    print(f"\nRata-rata seluruh emiten likuid (per hari, KOTOR sebelum biaya):")
    print(f"  Overnight (BSJP) : {df['on_rata'].mean():+.4f}%   "
          f"menang {df['on_menang'].mean():.1f}%")
    print(f"  Intraday  (BPJS) : {df['id_rata'].mean():+.4f}%   "
          f"menang {df['id_menang'].mean():.1f}%")
    print(f"  Biaya sekali putar: {df['biaya_pct'].mean():.3f}% "
          f"(median {df['biaya_pct'].median():.3f}%)")

    n_on = int((df["on_rata"] > 0).sum())
    n_id = int((df["id_rata"] > 0).sum())
    print(f"\n  Emiten dengan overnight positif : {n_on}/{len(df)}")
    print(f"  Emiten dengan intraday positif  : {n_id}/{len(df)}")

    # --- setelah biaya ---
    lolos_on = df[df["on_net"] > 0]
    lolos_id = df[df["id_net"] > 0]
    print(f"\nSETELAH BIAYA (yang benar-benar menyisakan untung per putaran):")
    print(f"  BSJP layak : {len(lolos_on)}/{len(df)} emiten")
    print(f"  BPJS layak : {len(lolos_id)}/{len(df)} emiten")

    # --- kandidat terbaik ---
    print("\n--- 12 TERBAIK UNTUK BSJP (beli sore, jual pagi) ---")
    top = df.nlargest(12, "on_rata")[
        ["ticker", "harga", "on_rata", "on_net", "on_menang", "on_t",
         "on_sd", "biaya_pct", "id_rata"]]
    top.columns = ["Ticker", "Harga", "ON kotor%", "ON net%", "Menang%", "t",
                   "SD%", "Biaya%", "ID kotor%"]
    print(top.to_string(index=False))

    print("\n--- 12 TERBAIK UNTUK BPJS (beli pagi, jual sore) ---")
    top2 = df.nlargest(12, "id_rata")[
        ["ticker", "harga", "id_rata", "id_net", "id_menang", "id_t",
         "id_sd", "biaya_pct", "on_rata"]]
    top2.columns = ["Ticker", "Harga", "ID kotor%", "ID net%", "Menang%", "t",
                    "SD%", "Biaya%", "ON kotor%"]
    print(top2.to_string(index=False))

    # --- uji persistensi: inti dari seluruh analisis ini ---
    print("\n" + "=" * 104)
    print("UJI PERSISTENSI — apakah edge bertahan, atau cuma kebetulan masa lalu?")
    print("=" * 104)
    for kol, nama in (("overnight", "BSJP"), ("intraday", "BPJS")):
        p = ov.uji_persistensi(prep, likuid, kolom=kol)
        if not p:
            continue
        print(f"\n{nama} ({kol}) — {p['n']} emiten:")
        print(f"  Korelasi peringkat paruh-1 vs paruh-2 : {p['korelasi_peringkat']:+.3f}")
        print(f"  Rata-rata paruh-2, SEMUA emiten       : {p['rata_p2_semua']:+.4f}%/hari")
        print(f"  Rata-rata paruh-2, top-10 dari paruh-1: {p['rata_p2_top10_p1']:+.4f}%/hari")
        hasil = "UNGGUL" if p["top10_unggul"] else "TIDAK unggul"
        print(f"  -> memilih berdasar masa lalu: {hasil}")

    # --- vonis ---
    print("\n" + "=" * 104)
    print("VONIS")
    print("=" * 104)
    med_on, med_id = df["on_rata"].median(), df["id_rata"].median()
    med_biaya = df["biaya_pct"].median()
    print(f"\nMedian overnight {med_on:+.4f}%/hari vs biaya {med_biaya:.3f}% sekali putar.")
    print(f"Median intraday  {med_id:+.4f}%/hari.")
    rasio = abs(med_on) / med_biaya if med_biaya else 0
    print(f"\nRasio |overnight| terhadap biaya: {rasio:.2f}x")
    if rasio < 1:
        print("Artinya: gerak overnight rata-rata BAHKAN TIDAK MENUTUP biaya transaksi.")
        print("Melakukan BSJP setiap hari pada emiten rata-rata = rugi terstruktur,")
        print("berapa pun bagusnya pemilihan sahamnya.")

    hari = 244
    print(f"\nBila diputar tiap hari bursa ({hari} hari/tahun), biaya saja memakan "
          f"{med_biaya * hari:.0f}% per tahun.")
    print("Angka itulah yang harus dikalahkan sebelum bicara untung.")

    df.to_csv(OUT_DIR / "bsjp.csv", index=False)
    print(f"\nDisimpan: {OUT_DIR / 'bsjp.csv'}")


if __name__ == "__main__":
    main()
