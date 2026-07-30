"""Cek kemampuan data intraday & tingkat keterlambatan untuk saham IDX."""
import datetime as dt
import json
import urllib.request

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0"}


def get(url):
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


for sym, rng, iv in [("BBCA.JK", "1d", "5m"), ("BBCA.JK", "5d", "15m"),
                     ("%5EJKSE", "1d", "5m"), ("BFIN.JK", "1d", "1m")]:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?range={rng}&interval={iv}")
    try:
        d = get(url)
        r = d["chart"]["result"][0]
        meta, ts = r["meta"], r.get("timestamp") or []
        mkt = dt.datetime.fromtimestamp(meta["regularMarketTime"], dt.timezone.utc)
        now = dt.datetime.now(dt.timezone.utc)
        lag = (now - mkt).total_seconds() / 60
        last_bar = (dt.datetime.fromtimestamp(ts[-1], dt.timezone.utc) if ts else None)
        print(f"{sym:10} {rng:3} {iv:4} -> {len(ts):4} bar | "
              f"harga {meta.get('regularMarketPrice')} | "
              f"status {meta.get('marketState','?')} | "
              f"lag quote {lag:.0f} menit | bar terakhir "
              f"{last_bar.strftime('%Y-%m-%d %H:%M UTC') if last_bar else '-'}")
    except Exception as e:
        print(f"{sym:10} {rng:3} {iv:4} -> GAGAL: {e}")
