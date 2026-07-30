"""Bandingkan pendekatan lama (chart-saja) vs corong dua tahap (spark + chart)."""

import time
import warnings

import pandas as pd

from idxquant import data as dl
from idxquant.providers import get_provider
from idxquant.scalping import scan_funnel, scan_scalping

warnings.filterwarnings("ignore")

scr = pd.read_csv("output/screening.csv")
liq = scr[scr["likuid"]]
semua = list(liq["ticker"])
prev = {}
for t in semua:
    d = dl.load(t, rng="5y")
    if d is not None and len(d) > 1:
        prev[t] = float(d["close"].iloc[-2])

prov = get_provider()
print("=" * 74)
print(f"BENCHMARK — {len(semua)} emiten likuid | penyedia: {prov.name}")
print("=" * 74)

t0 = time.time()
lama = scan_scalping(semua[:40], prev_closes=prev, provider=prov)
d_lama = time.time() - t0
print(f"\nLAMA  (chart-saja, 40 ticker)   : {d_lama:5.1f} detik -> {len(lama)} hasil")

t0 = time.time()
baru, stats = scan_funnel(semua, prev_closes=prev, top_deep=20, provider=prov)
d_baru = time.time() - t0
print(f"BARU  (corong, {len(semua)} ticker disaring) : {d_baru:5.1f} detik -> {len(baru)} hasil")
print(f"        tahap1 spark : {stats['detik_tahap1']:.2f}s untuk {stats['tahap1_ticker']} ticker")
print(f"        tahap2 chart : {stats['detik_tahap2']:.2f}s untuk {stats['tahap2_ticker']} ticker")
print(f"        metode       : {stats['metode']}")

print(f"\nCakupan: {len(semua)} vs 40 emiten  ({len(semua)/40:.1f}x lebih luas)")
if d_baru > 0:
    print(f"Waktu  : {d_lama:.1f}s -> {d_baru:.1f}s")

if not baru.empty:
    print("\nTop 8 corong:")
    print(baru.head(8)[["ticker", "harga", "skor", "label", "ret_sesi", "vs_vwap",
                        "rvol", "biaya_putaran", "peluang"]].to_string(index=False))
