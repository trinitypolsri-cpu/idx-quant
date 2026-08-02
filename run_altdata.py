"""Cari alpha: makro BPS + komoditas global vs emiten tambang & komoditas IDX."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import altdata as ad
from idxquant import bps
from idxquant import data as dl
from idxquant.config import OUT_DIR

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)

DARI, SAMPAI = 2019, 2026

# Emiten berbasis komoditas — sektor yang secara ekonomi memang terhubung ke makro
SAHAM = {
    "Timah": ["TINS"],
    "Nikel": ["INCO", "ANTM", "NCKL", "MBMA"],
    "Batubara": ["ADRO", "PTBA", "ITMG", "HRUM", "INDY"],
    "Emas": ["MDKA", "PSAB", "ARCI"],
    "CPO": ["AALI", "LSIP", "TAPG", "DSNG"],
    "Energi": ["MEDC", "PGAS", "ELSA"],
    # Pangan & konsumer — terhubung ke harga pangan global dan daya beli domestik
    "Pangan olahan": ["ICBP", "INDF", "MYOR", "ULTJ", "ROTI"],
    "Protein": ["CPIN", "JPFA", "MAIN"],
    "Ritel": ["AMRT", "MIDI", "ACES", "MAPI"],
}

# Seri makro global lewat Yahoo
MAKRO_YF = {
    # Energi & logam
    "Minyak Brent": "BZ=F",
    "Minyak WTI": "CL=F",
    "Tembaga": "HG=F",
    "Emas": "GC=F",
    # Pangan
    "Gandum": "ZW=F",
    "Jagung": "ZC=F",
    "Kedelai": "ZS=F",
    "Gula": "SB=F",
    "Kopi": "KC=F",
    # Makro & siklus
    "Dollar Index": "DX-Y.NYB",
    "USD/IDR": "IDR=X",
    "Shanghai Comp": "000001.SS",
    "US 10Y Yield": "^TNX",
    "VIX": "^VIX",
}

# Seri makro BPS (bulanan) — siklus ekonomi & kebijakan domestik
MAKRO_BPS = {
    "Nilai Ekspor ID": 196,
    "Nilai Impor ID": 497,
    "Inflasi M-to-M": 1,
    "IHK Umum": 2,
}


def main():
    tickers = [t for v in SAHAM.values() for t in v]
    print(f"Mengunduh {len(tickers)} emiten + {len(MAKRO_YF)} seri global ...")
    saham = {}
    for t in tickers:
        d = dl.load(t, rng="10y")
        if d is not None and len(d) > 400:
            saham[t] = d["close"]

    makro = {}
    for nama, sym in MAKRO_YF.items():
        d = dl.fetch_one(sym, rng="10y", interval="1d")
        if d is not None and len(d) > 400:
            makro[nama] = d["close"]
        else:
            print(f"  lewati {nama} ({sym}) — data tidak tersedia")

    print(f"Mengambil {len(MAKRO_BPS)} seri BPS {DARI}-{SAMPAI} ...")
    for nama, vid in MAKRO_BPS.items():
        s = bps.deret_bulanan(vid, DARI, SAMPAI)
        if len(s) > 24:
            makro[nama] = s
            print(f"  {nama}: {len(s)} bulan ({s.attrs.get('satuan','')})")
        else:
            print(f"  {nama}: gagal / terlalu pendek")

    print(f"\n{len(saham)} emiten x {len(makro)} seri makro x 4 lag = "
          f"{len(saham)*len(makro)*4} pengujian")

    df = ad.studi(makro, saham, lags=(0, 1, 2, 3), q=0.10)
    if df.empty:
        print("Tidak ada hasil.")
        return

    n_mentah = int(df["lolos_mentah"].sum())
    n_fdr = int(df["lolos_fdr"].sum())
    print("\n" + "=" * 100)
    print("HASIL PENGUJIAN")
    print("=" * 100)
    print(f"\n  Lolos p<0,05 mentah      : {n_mentah} dari {len(df)}")
    print(f"  Diperkirakan kebetulan   : ~{len(df)*0.05:.0f}")
    print(f"  Lolos koreksi FDR (10%)  : {n_fdr}")
    if n_mentah <= len(df) * 0.05 * 1.3:
        print("\n  Jumlah yang lolos mentah setara dengan yang diharapkan dari kebetulan.")
        print("  Tanpa koreksi, semua 'temuan' ini kemungkinan besar palsu.")

    print("\n--- 15 hubungan terkuat (menurut p-value) ---")
    tampil = df.head(15)[["makro", "saham", "lag", "r", "p", "n",
                          "lolos_mentah", "lolos_fdr"]]
    print(tampil.to_string(index=False))

    # Yang paling berharga: lag >= 1 (makro MENDAHULUI harga)
    lead = df[(df["lag"] >= 1) & df["lolos_fdr"]]
    print(f"\n--- Hubungan PREDIKTIF (lag>=1, lolos FDR): {len(lead)} ---")
    if len(lead):
        print(lead.head(12).to_string(index=False))
    else:
        print("  TIDAK ADA. Semua hubungan yang lolos bersifat serentak (lag=0),")
        print("  artinya makro dan harga bergerak bersamaan — informasinya sudah")
        print("  ada di harga dan tidak bisa dipakai untuk memprediksi.")

    # Uji stabilitas pada temuan teratas
    print("\n--- Uji stabilitas paruh-1 vs paruh-2 (10 teratas) ---")
    rows = []
    for r in df.head(10).itertuples():
        st = ad.uji_stabilitas(makro[r.makro], saham[r.saham], r.lag)
        if st:
            rows.append({"makro": r.makro, "saham": r.saham, "lag": r.lag,
                         "r_penuh": r.r, **st})
    if rows:
        s = pd.DataFrame(rows)
        print(s[["makro", "saham", "lag", "r_penuh", "r_paruh1", "r_paruh2",
                 "arah_sama", "stabil"]].to_string(index=False))
        n_stabil = int(s["stabil"].sum())
        print(f"\n  Stabil di kedua paruh: {n_stabil} dari {len(s)}")
        if n_stabil == 0:
            print("  Tidak satu pun bertahan. Ini ciri khas korelasi kebetulan.")

    df.to_csv(OUT_DIR / "altdata_korelasi.csv", index=False)
    print(f"\nDisimpan: {OUT_DIR / 'altdata_korelasi.csv'}")


if __name__ == "__main__":
    main()
