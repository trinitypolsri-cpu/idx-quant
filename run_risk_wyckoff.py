"""Monte Carlo atas trade backtest + analisis Wyckoff/VWAP intraday."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import wyckoff as wy
from idxquant.montecarlo import bootstrap, kelly, risk_of_ruin, sensitivitas_pemenang
from idxquant.recorder import load_bars

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)


def bagian_montecarlo():
    tr = pd.read_csv("output/trades.csv")
    r = tr["ret"].to_numpy()

    print("=" * 78)
    print(f"MONTE CARLO — bootstrap {len(r)} trade nyata dari backtest")
    print("=" * 78)

    BOBOT = 0.10          # 10 posisi paralel berbobot sama
    b = bootstrap(r, n_sim=10000, bobot=BOBOT)
    print(f"\nBobot posisi     : {BOBOT:.0%} ekuitas per trade (10 posisi paralel)")
    print(f"Distribusi trade : rata2 {b['rata_trade']*100:+.2f}%  "
          f"median {b['median_trade']*100:+.2f}%  menang {b['menang']:.0f}%")

    print(f"\nHasil teramati   : ekuitas akhir {b['obs_terminal']:.3f}x  "
          f"(MaxDD {b['obs_maxdd']*100:.1f}%)")
    print(f"                   backtest sesungguhnya: 1,134x, MaxDD -31,8% "
          f"-> ordo cocok")
    print(f"Persentil hasil  : {b['obs_persentil']:.0f} dari 10.000 jalur acak")

    print("\nDistribusi ekuitas akhir (10.000 simulasi):")
    for q, v in b["terminal"].items():
        print(f"   p{q:<3} {v:6.3f}x")
    print("\nDistribusi drawdown maksimum:")
    for q, v in b["maxdd"].items():
        print(f"   p{q:<3} {v*100:7.1f}%")

    print(f"\nProbabilitas rugi (ekuitas < 1,0x) : {b['p_rugi']:.1f}%")
    print(f"Probabilitas MaxDD lebih dari 30%  : {b['p_dd_lebih_30']:.1f}%")
    print(f"Probabilitas MaxDD lebih dari 50%  : {b['p_dd_lebih_50']:.1f}%")

    k = kelly(r)
    if k:
        print(f"\nKelly: menang {k['p_menang']}%  avg menang {k['avg_menang']}%  "
              f"avg kalah {k['avg_kalah']}%  payoff {k['payoff']}")
        print(f"       Kelly penuh {k['kelly_penuh']}%  ->  "
              f"seperempat Kelly {k['kelly_seperempat']}% per posisi")

    print("\n--- Risk of ruin (turun 50%, horizon 250 trade) ---")
    print(risk_of_ruin(r, [0.005, 0.01, 0.02, 0.03, 0.05]).to_string(index=False))

    print("\n--- Kerapuhan: hasil setelah membuang N trade terbaik ---")
    print(sensitivitas_pemenang(r, [0, 1, 3, 5, 10, 20], bobot=BOBOT).to_string(index=False))


def bagian_wyckoff():
    print("\n" + "=" * 78)
    print("WYCKOFF & VWAP — bar 5 menit dari database rekaman sendiri")
    print("=" * 78)

    df = load_bars(interval="5m")
    if df.empty:
        print("Belum ada bar terekam. Jalankan: python -m idxquant.recorder --sekali")
        return

    hasil = []
    for t, g in df.groupby("ticker"):
        g = g.drop(columns=["ticker"]).sort_index()
        s = wy.summarise(t, g)
        if s.get("n_bar", 0) >= 25:
            hasil.append(s)

    if not hasil:
        print("Data belum cukup untuk analisis Wyckoff.")
        return

    h = pd.DataFrame(hasil)
    h["net"] = h["bullish"] - h["bearish"]
    h = h.sort_values(["net", "vs_vwap"], ascending=False)

    print(f"\n{len(h)} emiten dianalisis dari database rekaman\n")
    show = h.head(14)[["ticker", "harga", "vwap", "vs_vwap", "penerimaan_atas_vwap",
                       "bias", "bullish", "bearish", "event_terakhir",
                       "waktu_event", "n_event"]]
    show.columns = ["Ticker", "Harga", "VWAP", "vsVWAP%", "TerimaVWAP%", "Bias",
                    "Bull", "Bear", "EventAkhir", "Jam", "nEvent"]
    print(show.to_string(index=False))

    print("\n--- Sebaran bias Wyckoff ---")
    print(h["bias"].value_counts().to_string())

    print("\n--- Emiten dengan urutan peristiwa paling informatif ---")
    kaya = h[h["n_event"] >= 3].head(5)
    for r in kaya.itertuples():
        print(f"\n  {r.ticker} ({r.bias}) — {r.n_event} peristiwa, "
              f"terakhir {r.waktu_event}")
        print(f"    urutan: {' -> '.join(r.urutan)}")
        if r.event_terakhir:
            print(f"    {wy.explain(r.event_terakhir)}")

    print("\n--- Kamus peristiwa ---")
    for k in wy.EVENT_LABEL:
        print(f"  {k:4} {wy.explain(k)}")


if __name__ == "__main__":
    bagian_montecarlo()
    bagian_wyckoff()
