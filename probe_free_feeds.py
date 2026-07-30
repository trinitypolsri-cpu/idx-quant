"""Probe sumber data IDX GRATIS (tanpa API key berbayar).

Menguji endpoint publik yang dipakai situs resmi IDX dan beberapa alternatif gratis.
Melaporkan mana yang benar-benar hidup, apa isinya, dan seberapa segar datanya.
"""

from __future__ import annotations

import datetime as dt
import json
import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

HDR = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Referer": "https://www.idx.co.id/",
    "X-Requested-With": "XMLHttpRequest",
}

TARGETS = [
    # --- Endpoint publik situs resmi IDX ---
    ("IDX ringkasan saham harian",
     "https://www.idx.co.id/primary/TradingSummary/GetStockSummary",
     {"length": 10, "start": 0}),
    ("IDX daftar emiten",
     "https://www.idx.co.id/primary/StockData/GetSecuritiesStock",
     {"start": 0, "length": 10, "code": "", "sector": "", "board": "",
      "language": "en-us"}),
    ("IDX pergerakan indeks",
     "https://www.idx.co.id/primary/Home/GetIndexMovement", {}),
    ("IDX chart data emiten",
     "https://www.idx.co.id/primary/ChartData/GetStockDataByCode",
     {"code": "BBCA", "period": "1M"}),
    ("IDX ringkasan broker",
     "https://www.idx.co.id/primary/TradingSummary/GetBrokerSummary",
     {"length": 10, "start": 0}),
    # --- Alternatif gratis lain ---
    ("goapi.io (butuh key gratis)",
     "https://api.goapi.io/stock/idx/BBCA/prices", {}),
    ("Yahoo (pembanding, sudah dipakai)",
     "https://query1.finance.yahoo.com/v8/finance/chart/BBCA.JK",
     {"range": "1d", "interval": "5m"}),
]


def probe(name, url, params):
    t0 = time.time()
    try:
        r = requests.get(url, headers=HDR, params=params, timeout=25)
        ms = (time.time() - t0) * 1000
        ctype = r.headers.get("content-type", "")[:40]
        line = f"[{r.status_code}] {name}\n     {ms:.0f}ms · {ctype} · {len(r.content):,} byte"
        if r.status_code == 200 and "json" in ctype:
            try:
                js = r.json()
                keys = list(js)[:6] if isinstance(js, dict) else f"list[{len(js)}]"
                line += f"\n     kunci: {keys}"
                # cari sampel record
                rows = None
                if isinstance(js, dict):
                    for k in ("data", "Data", "results", "replies", "recordsTotal"):
                        if k in js and isinstance(js[k], list) and js[k]:
                            rows = js[k]
                            break
                elif isinstance(js, list):
                    rows = js
                if rows:
                    s = rows[0]
                    line += f"\n     contoh: {json.dumps(s, ensure_ascii=False)[:280]}"
            except Exception as e:                                # noqa: BLE001
                line += f"\n     gagal parse JSON: {e}"
        elif r.status_code == 200:
            line += f"\n     bukan JSON — awal isi: {r.text[:120]!r}"
        else:
            line += f"\n     isi: {r.text[:160]!r}"
        return line
    except Exception as e:                                        # noqa: BLE001
        return f"[ERR] {name}\n     {type(e).__name__}: {str(e)[:160]}"


if __name__ == "__main__":
    print("=" * 78)
    print(f"PROBE SUMBER DATA IDX GRATIS — {dt.datetime.now():%d %b %Y %H:%M}")
    print("=" * 78)
    for name, url, params in TARGETS:
        print()
        print(probe(name, url, params))
