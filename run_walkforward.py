"""Walk-forward: cara menguji parameter tanpa menipu diri sendiri.

CARA KERJANYA
-------------
Backtest biasa memilih parameter dengan melihat SELURUH data, lalu melaporkan
hasil pada data yang sama. Itu seperti menebak hasil pertandingan setelah menonton
rekamannya. Sapuan stop sebelumnya persis begitu: 12 kombinasi diuji pada 5 tahun
yang sama, lalu yang terbaik (6x ATR) dilaporkan sebagai temuan.

Walk-forward memisahkan keduanya secara waktu:

    [--- latih 1 ---][uji 1]
              [--- latih 2 ---][uji 2]
                        [--- latih 3 ---][uji 3]

Pada tiap langkah: pilih parameter TERBAIK di jendela latih, lalu pakai parameter
itu — tanpa mengubahnya — pada jendela uji yang belum pernah dilihat. Kumpulkan
seluruh hasil jendela uji. Itulah perkiraan performa sesungguhnya.

Kalau parameter terbaik berganti-ganti tiap jendela, itu tanda parameternya
mengejar derau, bukan menangkap sesuatu yang nyata.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import demo
from idxquant import setups as st
from idxquant.config import OUT_DIR, RISK_FREE
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)

MODAL = 100_000_000
SETUP = "BaseBreakout"
KANDIDAT_STOP = [2.0, 3.0, 4.0, 6.0]
N_JENDELA = 4


def metrik(eq: pd.Series, modal: float) -> dict:
    if eq is None or len(eq) < 20:
        return {"ret": np.nan, "dd": np.nan, "sharpe": np.nan}
    r = eq.pct_change().dropna()
    total = eq.iloc[-1] / eq.iloc[0] - 1
    dd = float((eq / eq.cummax() - 1).min())
    sh = np.nan
    if len(r) > 20 and r.std(ddof=0) > 0:
        cagr = (eq.iloc[-1] / eq.iloc[0]) ** (244 / len(eq)) - 1
        sh = (cagr - RISK_FREE) / (r.std(ddof=0) * np.sqrt(244))
    return {"ret": float(total), "dd": dd, "sharpe": float(sh)}


def potong(prep: dict, mulai, akhir) -> dict:
    return {t: d[(d.index >= mulai) & (d.index < akhir)]
            for t, d in prep.items() if len(d[(d.index >= mulai) & (d.index < akhir)]) > 60}


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    scan = st.scan(prep)
    likuid = set(scan[scan["likuid"]]["ticker"])

    tgl = bench.index
    total = len(tgl)
    lebar = total // (N_JENDELA + 1)          # latih 1 blok, uji blok berikutnya

    print("=" * 92)
    print(f"WALK-FORWARD — setup {SETUP}, parameter yang dicari: jarak stop")
    print("=" * 92)
    print(f"\n  {total} hari bursa dibagi {N_JENDELA} langkah, "
          f"tiap blok ~{lebar} hari\n")

    baris, pilihan, hasil_uji = [], [], []
    for k in range(N_JENDELA):
        a_latih, b_latih = tgl[k * lebar], tgl[(k + 1) * lebar]
        b_uji = tgl[min((k + 2) * lebar, total - 1)]

        p_latih = potong(prep, a_latih, b_latih)
        p_uji = potong(prep, b_latih, b_uji)
        if not p_latih or not p_uji:
            continue

        # --- pilih parameter TERBAIK di jendela latih ---
        skor = {}
        for s in KANDIDAT_STOP:
            r = demo.simulasi(p_latih, bench, setup=SETUP, modal=MODAL,
                              maks_posisi=5, stop_atr=s, likuid=likuid)
            m = metrik(r.get("ekuitas") if r else None, MODAL)
            skor[s] = m["sharpe"] if np.isfinite(m["sharpe"]) else -99
        terbaik = max(skor, key=skor.get)
        pilihan.append(terbaik)

        # --- pakai parameter itu pada jendela UJI (belum pernah dilihat) ---
        ru = demo.simulasi(p_uji, bench, setup=SETUP, modal=MODAL,
                           maks_posisi=5, stop_atr=terbaik, likuid=likuid)
        mu = metrik(ru.get("ekuitas") if ru else None, MODAL)
        hasil_uji.append(mu)

        baris.append({
            "Langkah": k + 1,
            "Latih": f"{a_latih.date()} .. {b_latih.date()}",
            "Uji": f"{b_latih.date()} .. {b_uji.date()}",
            "Stop terpilih": f"{terbaik}x",
            "Sharpe latih": round(skor[terbaik], 3),
            "Return uji%": round(mu["ret"] * 100, 1) if np.isfinite(mu["ret"]) else None,
            "DD uji%": round(mu["dd"] * 100, 1) if np.isfinite(mu["dd"]) else None,
            "Sharpe uji": round(mu["sharpe"], 3) if np.isfinite(mu["sharpe"]) else None,
        })

    tab = pd.DataFrame(baris)
    print(tab.to_string(index=False))

    # --- kesimpulan ---
    print("\n" + "=" * 92)
    print("KESIMPULAN")
    print("=" * 92)
    sh_latih = tab["Sharpe latih"].dropna()
    sh_uji = tab["Sharpe uji"].dropna()
    print(f"\n  Sharpe rata-rata di LATIH : {sh_latih.mean():+.3f}")
    print(f"  Sharpe rata-rata di UJI   : {sh_uji.mean():+.3f}")
    susut = sh_latih.mean() - sh_uji.mean()
    print(f"  Penyusutan                : {susut:+.3f}")
    print(f"\n  Stop terpilih tiap langkah: {pilihan}")
    if len(set(pilihan)) > 1:
        print("  BERGANTI-GANTI -> parameter mengejar derau, bukan pola nyata.")
    else:
        print("  KONSISTEN -> ada indikasi parameter ini stabil.")

    print(f"\n  Pembanding: sapuan sebelumnya melaporkan Sharpe +1,192 untuk stop 6x")
    print(f"  ATR, dipilih DAN diuji pada data yang sama. Angka luar sampel di atas")
    print(f"  adalah perkiraan yang jauh lebih jujur.")

    tab.to_csv(OUT_DIR / "walkforward.csv", index=False)
    print(f"\nDisimpan: {OUT_DIR / 'walkforward.csv'}")


if __name__ == "__main__":
    main()
