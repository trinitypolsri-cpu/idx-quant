"""Scanner scalping IDX — momentum intraday pada emiten paling likuid."""

from __future__ import annotations

import sys
import warnings

import pandas as pd

from idxquant import data as dl
from idxquant.providers import get_provider
from idxquant.scalping import scan_scalping

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)

TOP_N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
INTERVAL = sys.argv[2] if len(sys.argv) > 2 else "5m"


def main():
    scr = pd.read_csv("output/screening.csv")
    liq = scr[scr["likuid"]].nlargest(TOP_N, "turnover_med20_M")
    tickers = list(liq["ticker"])
    prev = {}
    for t in tickers:
        try:
            d = dl.load(t, rng="5y")
            if d is not None and len(d) > 1:
                prev[t] = float(d["close"].iloc[-2])
        except Exception:
            pass

    prov = get_provider()
    print("=" * 118)
    print(f"SCANNER SCALPING IDX — {len(tickers)} emiten terlikuid | "
          f"interval {INTERVAL} | penyedia: {prov.name}")
    print("=" * 118)

    df = scan_scalping(tickers, prev_closes=prev, interval=INTERVAL, provider=prov)
    if df.empty:
        print("Tidak ada data intraday. Bursa mungkin belum buka atau penyedia gagal.")
        return

    show = df.head(20)[[
        "ticker", "harga", "skor", "label", "ret_sesi", "vs_vwap", "posisi_range",
        "rvol", "range_pct", "tick", "tick_pct", "biaya_putaran", "tick_untuk_bep",
        "peluang", "ara_head", "orb_up"]]
    show.columns = ["Ticker", "Harga", "Skor", "Label", "Sesi%", "vsVWAP", "PosRange",
                    "RVol", "Range%", "Tick", "Tick%", "Biaya%", "TickBEP",
                    "Peluang", "SisaARA", "ORB"]
    print(show.to_string(index=False))

    print("\n--- GESEKAN FRAKSI HARGA: emiten termahal untuk di-scalp ---")
    worst = df.nlargest(6, "biaya_putaran")[
        ["ticker", "harga", "tick", "tick_pct", "biaya_putaran", "tick_untuk_bep", "range_pct"]]
    worst.columns = ["Ticker", "Harga", "Tick", "Tick%", "BiayaPutaran%", "TickUntukBEP", "Range%"]
    print(worst.to_string(index=False))

    print("\n--- TERMURAH untuk di-scalp ---")
    best = df.nsmallest(6, "biaya_putaran")[
        ["ticker", "harga", "tick", "tick_pct", "biaya_putaran", "tick_untuk_bep", "range_pct"]]
    best.columns = ["Ticker", "Harga", "Tick", "Tick%", "BiayaPutaran%", "TickUntukBEP", "Range%"]
    print(best.to_string(index=False))

    n_layak = int((df["range_pct"] > df["biaya_putaran"] * 2).sum())
    print(f"\nEmiten yang rentang hariannya >2x biaya putaran: {n_layak} dari {len(df)}")
    df.to_csv("output/scalping.csv", index=False)
    print("Disimpan: output/scalping.csv")


if __name__ == "__main__":
    main()
