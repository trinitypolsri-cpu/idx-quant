"""Uji batas endpoint spark Yahoo: berapa ticker per request, dan seberapa cepat."""

from __future__ import annotations

import time

import pandas as pd
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
URL = "https://query1.finance.yahoo.com/v7/finance/spark"

scr = pd.read_csv("output/screening.csv")
liq = scr[scr["likuid"]].nlargest(60, "turnover_med20_M")
tickers = [f"{t}.JK" for t in liq["ticker"]]

for n in (10, 20, 40, 60):
    syms = tickers[:n]
    t0 = time.time()
    try:
        r = requests.get(URL, headers={"User-Agent": UA},
                         params={"symbols": ",".join(syms), "range": "1d",
                                 "interval": "5m"}, timeout=30)
        ms = (time.time() - t0) * 1000
        if r.status_code != 200:
            print(f"n={n:3}  HTTP {r.status_code}  {r.text[:90]}")
            continue
        js = r.json()
        res = js.get("spark", {}).get("result", []) or []
        got = len(res)
        bars = 0
        for item in res:
            resp = item.get("response") or []
            if resp and resp[0].get("timestamp"):
                bars += len(resp[0]["timestamp"])
        print(f"n={n:3}  HTTP 200  {ms:6.0f}ms  {len(r.content):>7,} byte  "
              f"terkembalikan={got:3}  total bar={bars:5}  "
              f"rata2 bar/ticker={bars/max(got,1):.0f}")
    except Exception as e:                                        # noqa: BLE001
        print(f"n={n:3}  ERROR {type(e).__name__}: {str(e)[:80]}")

# Bandingkan dengan pendekatan lama: 1 request per ticker
print("\nPembanding — 40 request terpisah (pendekatan lama):")
t0 = time.time()
ok = 0
for s in tickers[:40]:
    try:
        rr = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}",
                          headers={"User-Agent": UA},
                          params={"range": "1d", "interval": "5m"}, timeout=20)
        if rr.status_code == 200:
            ok += 1
    except Exception:
        pass
print(f"  {ok}/40 berhasil dalam {time.time()-t0:.1f} detik (serial)")
