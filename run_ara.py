"""Deteksi potensi ARA — validasi historis lalu pemindaian kandidat hari ini."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import ara as ar
from idxquant import data as dl
from idxquant import setups as st
from idxquant.config import OUT_DIR
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 210)


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)

    P = ar.kumpulkan(prep)
    if P.empty:
        print("Data tidak cukup.")
        return

    n_ara = int(P["ara"].sum())
    base = float(P["ara_besok"].mean())

    print("=" * 100)
    print(f"DETEKSI POTENSI ARA — {P['ticker'].nunique()} emiten, "
          f"{len(P):,} observasi hari-emiten, 5 tahun")
    print("=" * 100)
    print(f"\nKejadian ARA tercatat : {n_ara:,}")
    print(f"Base rate ARA besok   : {base*100:.3f}%  "
          f"(1 dari {1/base:.0f} hari-emiten)")
    print("\nARA itu langka. Setiap klaim 'deteksi ARA' harus dibandingkan dengan")
    print("angka dasar ini — kalau tidak, tingkat akurasi 99% pun tak berarti apa-apa")
    print("karena menebak 'tidak ARA' setiap hari sudah benar 99,9% waktu.")

    print("\n--- Ciri tunggal: seberapa besar menaikkan peluang? ---")
    e1 = ar.evaluasi(P, ar.CIRI)
    print(e1.to_string(index=False))

    print("\n--- Kombinasi ciri ---")
    e2 = ar.evaluasi(P, ar.KOMBINASI)
    print(e2.to_string(index=False))

    berguna = pd.concat([e1, e2])
    berguna = berguna[berguna.get("Berguna") == "ya"] if "Berguna" in berguna else berguna
    print(f"\nCiri yang lolos (lift >1,5x dan z >3): "
          f"{len(berguna)} dari {len(e1)+len(e2)} yang diuji")

    # --- validasi luar sampel ---
    print("\n" + "=" * 100)
    print("VALIDASI LUAR SAMPEL — paruh-1 melatih, paruh-2 menguji")
    print("=" * 100)
    P = P.sort_index()
    mid = P.index[len(P) // 2]
    tr, te = P[P.index <= mid], P[P.index > mid]
    print(f"\nLatih : {tr.index[0].date()} - {tr.index[-1].date()}  ({len(tr):,} obs)")
    print(f"Uji   : {te.index[0].date()} - {te.index[-1].date()}  ({len(te):,} obs)")

    for nama, fn in ar.KOMBINASI.items():
        m_tr, m_te = fn(tr).fillna(False), fn(te).fillna(False)
        if m_tr.sum() < 30 or m_te.sum() < 30:
            continue
        p_tr = float(tr[m_tr]["ara_besok"].mean())
        p_te = float(te[m_te]["ara_besok"].mean())
        b_te = float(te["ara_besok"].mean())
        print(f"  {nama:28} latih {p_tr*100:6.3f}%  ->  uji {p_te*100:6.3f}%  "
              f"(base uji {b_te*100:.3f}%, lift {p_te/b_te if b_te else 0:.2f}x)")

    # --- kandidat hari ini ---
    print("\n" + "=" * 100)
    print("KANDIDAT HARI INI")
    print("=" * 100)
    hari_ini = P[P.index == P.index.max()].copy()
    hari_ini["skor_ara"] = hari_ini.apply(ar.skor, axis=1)
    hari_ini["sisa_ara_pct"] = (hari_ini["limit"] - hari_ini["ret"]) * 100
    top = hari_ini.nlargest(12, "skor_ara")[
        ["ticker", "close", "skor_ara", "ret", "sisa_ara_pct", "rvol",
         "pos_close", "ara_kemarin", "dari_hi60"]].copy()
    top["ret"] = (top["ret"] * 100).round(2)
    top["dari_hi60"] = (top["dari_hi60"] * 100).round(1)
    top["pos_close"] = (top["pos_close"] * 100).round(0)
    top.columns = ["Ticker", "Harga", "Skor", "Ret%", "SisaARA%", "RVol",
                   "PosClose%", "ARAkemarin", "DariHi60%"]
    print(f"\nPer {P.index.max().date()}:\n")
    print(top.to_string(index=False))

    # Harapan realistis
    skor_tinggi = hari_ini[hari_ini["skor_ara"] >= 50]
    hist = P[P.apply(ar.skor, axis=1) >= 50] if len(P) < 200000 else None
    if hist is not None and len(hist) > 100:
        p_hist = float(hist["ara_besok"].mean())
        print(f"\nSecara historis, skor >=50 diikuti ARA keesokan hari "
              f"{p_hist*100:.2f}% waktu")
        print(f"(base rate {base*100:.3f}%, lift {p_hist/base:.1f}x). "
              f"Artinya dari {len(skor_tinggi)} kandidat hari ini,")
        print(f"perkiraan {len(skor_tinggi)*p_hist:.1f} yang benar-benar ARA besok.")

    hari_ini.to_csv(OUT_DIR / "ara_kandidat.csv")
    pd.concat([e1, e2]).to_csv(OUT_DIR / "ara_validasi.csv", index=False)
    print(f"\nDisimpan: ara_kandidat.csv, ara_validasi.csv")


if __name__ == "__main__":
    main()
