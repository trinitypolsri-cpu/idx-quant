"""Probe sumber data IDX gratis TANPA API key — putaran kedua."""

from __future__ import annotations

import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "*/*"}

TARGETS = [
    ("Stooq kuotasi CSV",
     "https://stooq.com/q/l/", {"s": "bbca.jk", "f": "sd2t2ohlcv", "h": "", "e": "csv"}),
    ("Stooq historis harian CSV",
     "https://stooq.com/q/d/l/", {"s": "bbca.jk", "i": "d"}),
    ("Stooq IHSG",
     "https://stooq.com/q/l/", {"s": "^jkse", "f": "sd2t2ohlcv", "h": "", "e": "csv"}),
    ("Yahoo 1 menit (pembanding)",
     "https://query1.finance.yahoo.com/v8/finance/chart/BBCA.JK",
     {"range": "1d", "interval": "1m"}),
    ("Yahoo quote batch",
     "https://query1.finance.yahoo.com/v7/finance/quote",
     {"symbols": "BBCA.JK,BBRI.JK,TLKM.JK"}),
    ("Yahoo spark (multi-ticker ringan)",
     "https://query1.finance.yahoo.com/v7/finance/spark",
     {"symbols": "BBCA.JK,BBRI.JK", "range": "1d", "interval": "5m"}),
]


def probe(name, url, params):
    t0 = time.time()
    try:
        r = requests.get(url, headers=H, params=params, timeout=25)
        ms = (time.time() - t0) * 1000
        ct = r.headers.get("content-type", "")[:36]
        out = f"[{r.status_code}] {name}\n     {ms:.0f}ms · {ct} · {len(r.content):,} byte"
        body = r.text[:300].replace("\n", " | ")
        out += f"\n     isi: {body}"
        return out
    except Exception as e:                                        # noqa: BLE001
        return f"[ERR] {name}\n     {type(e).__name__}: {str(e)[:150]}"


if __name__ == "__main__":
    print("=" * 78)
    print("PROBE SUMBER GRATIS TANPA API KEY — PUTARAN 2")
    print("=" * 78)
    for t in TARGETS:
        print()
        print(probe(*t))
