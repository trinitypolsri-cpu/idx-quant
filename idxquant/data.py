"""Loader OHLCV IDX dari endpoint chart publik Yahoo Finance, dengan cache lokal."""

from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from .config import DATA_DIR, MIN_HISTORY_DAYS
from .universe import yahoo_symbol

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _parse(payload: dict, interval: str = "1d") -> pd.DataFrame | None:
    chart = payload.get("chart") or {}
    results = chart.get("result")
    if not results:
        return None
    r = results[0]
    ts = r.get("timestamp")
    if not ts:
        return None
    q = r["indicators"]["quote"][0]
    idx = pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Jakarta")
    # Hanya data harian yang boleh dipangkas ke tanggal. Memangkas bar intraday
    # akan meruntuhkan seluruh sesi menjadi satu baris.
    if interval.endswith("d") or interval.endswith("wk") or interval.endswith("mo"):
        idx = idx.normalize()
    df = pd.DataFrame(
        {
            "open": q.get("open"),
            "high": q.get("high"),
            "low": q.get("low"),
            "close": q.get("close"),
            "volume": q.get("volume"),
        },
        index=idx,
    )
    df.index = df.index.tz_localize(None)
    df.index.name = "date"

    # Yahoo kadang mengirim bar hari terakhir dengan close=null walau sesi sudah
    # selesai, sementara meta.regularMarketPrice sudah berisi harga penutupan.
    # Tanpa penanganan ini baris tersebut terbuang dan SELURUH pipeline mundur satu
    # hari secara diam-diam — breadth, screener, dan level ikut memakai data basi.
    meta = r.get("meta") or {}
    rmp, rmt = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if len(df) and rmp and rmt and pd.isna(df["close"].iloc[-1]):
        tgl_pasar = (pd.Timestamp(rmt, unit="s", tz="UTC")
                     .tz_convert("Asia/Jakarta").tz_localize(None).normalize())
        idx_akhir = df.index[-1]
        cocok = (idx_akhir.normalize() == tgl_pasar if interval.endswith(("d", "wk", "mo"))
                 else idx_akhir <= tgl_pasar + pd.Timedelta(days=1))
        if cocok:
            df.iloc[-1, df.columns.get_loc("close")] = float(rmp)
            for col in ("open", "high", "low"):
                if pd.isna(df[col].iloc[-1]):
                    df.iloc[-1, df.columns.get_loc(col)] = float(rmp)

    df = df.dropna(subset=["close"])
    df = df[~df.index.duplicated(keep="last")]
    # Volume nol = hari suspensi/tidak ada transaksi; harga tetap dipertahankan.
    df["volume"] = df["volume"].fillna(0)
    for col in ("open", "high", "low"):
        df[col] = df[col].fillna(df["close"])
    return df


def fetch_one(ticker: str, rng: str = "5y", interval: str = "1d",
              session: requests.Session | None = None,
              retries: int = 3) -> pd.DataFrame | None:
    sym = yahoo_symbol(ticker)
    sess = session or requests.Session()
    for attempt in range(retries):
        try:
            resp = sess.get(
                CHART_URL.format(sym=sym),
                params={"range": rng, "interval": interval},
                headers=HEADERS,
                timeout=20,
            )
            if resp.status_code == 404:
                return None                      # ticker tidak ada
            if resp.status_code in (429, 502, 503):
                time.sleep(1.5 * (attempt + 1) + random.random())
                continue
            resp.raise_for_status()
            return _parse(resp.json(), interval=interval)
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(1.0 * (attempt + 1) + random.random())
    return None


def _cache_path(ticker: str, rng: str):
    return DATA_DIR / f"{ticker.replace('^', '_')}_{rng}.csv"


def load(ticker: str, rng: str = "5y", use_cache: bool = True,
         session: requests.Session | None = None) -> pd.DataFrame | None:
    path = _cache_path(ticker, rng)
    if use_cache and path.exists():
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        if len(df):
            return df
    df = fetch_one(ticker, rng=rng, session=session)
    if df is not None and len(df):
        df.to_csv(path)
    return df


def load_many(tickers: list[str], rng: str = "5y", workers: int = 8,
              use_cache: bool = True, min_days: int = MIN_HISTORY_DAYS,
              verbose: bool = True) -> dict[str, pd.DataFrame]:
    """Unduh paralel. Ticker gagal / histori terlalu pendek otomatis di-drop."""
    out: dict[str, pd.DataFrame] = {}
    dropped: list[str] = []

    def job(t):
        sess = requests.Session()
        try:
            return t, load(t, rng=rng, use_cache=use_cache, session=sess)
        finally:
            sess.close()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(job, t) for t in tickers]
        done = 0
        for fut in as_completed(futures):
            t, df = fut.result()
            done += 1
            if df is None or len(df) < min_days:
                dropped.append(t)
            else:
                out[t] = df
            if verbose and done % 25 == 0:
                print(f"  ... {done}/{len(tickers)} diproses, {len(out)} valid")

    if verbose:
        print(f"  selesai: {len(out)} ticker valid, {len(dropped)} di-drop")
        if dropped:
            print(f"  di-drop: {', '.join(sorted(dropped)[:40])}"
                  + (" ..." if len(dropped) > 40 else ""))
    return out


def close_panel(data: dict[str, pd.DataFrame], field: str = "close") -> pd.DataFrame:
    """Gabungkan satu field jadi panel wide (baris = tanggal, kolom = ticker)."""
    return pd.DataFrame({t: df[field] for t, df in data.items()}).sort_index()
