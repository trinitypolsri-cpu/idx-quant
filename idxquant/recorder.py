"""Perekam data intraday IDX — membangun dataset milik sendiri.

Alasan keberadaannya: history intraday IDX praktis tidak tersedia gratis, dan
vendor menjualnya mahal. Tapi data yang lewat hari ini bisa DIREKAM. Dijalankan
tiap hari bursa, dalam 3-6 bulan Anda punya tape intraday yang tidak bisa dibeli
murah di mana pun — dan itu bisa di-backtest.

Dua jalur perekaman:

  Jalur cepat (tick)  : endpoint spark, 20 ticker per request, HANYA harga penutup.
                        Murah, jadi seluruh universe likuid bisa dipoll tiap ~60 detik.
  Jalur lambat (bar)  : endpoint chart, OHLCV penuh per ticker. Mahal, jadi hanya
                        dijalankan tiap ~5 menit untuk emiten yang dipantau.

Penyimpanan SQLite dengan PRIMARY KEY komposit, sehingga poll berulang pada bar
yang sama menimpa alih-alih menggandakan — aman dijalankan ulang kapan saja.

    python -m idxquant.recorder --status
    python -m idxquant.recorder --sekali
    python -m idxquant.recorder --sesi          # loop sepanjang jam bursa
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import time

import pandas as pd

from .config import DATA_DIR
from .providers import YahooProvider, get_provider

WIB = dt.timezone(dt.timedelta(hours=7))
DB_PATH = DATA_DIR / "intraday.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    ticker TEXT NOT NULL,
    ts     TEXT NOT NULL,
    close  REAL NOT NULL,
    PRIMARY KEY (ticker, ts)
);
CREATE TABLE IF NOT EXISTS bars (
    ticker   TEXT NOT NULL,
    ts       TEXT NOT NULL,
    interval TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, ts, interval)
);
CREATE TABLE IF NOT EXISTS runs (
    mulai TEXT, selesai TEXT, jalur TEXT,
    n_ticker INTEGER, n_baris INTEGER, penyedia TEXT, catatan TEXT
);
CREATE INDEX IF NOT EXISTS idx_ticks_ts ON ticks(ts);
CREATE INDEX IF NOT EXISTS idx_bars_ts  ON bars(ts);
"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def market_open(now: dt.datetime | None = None) -> bool:
    """IDX: Senin-Jumat 09:00-15:50 WIB. Hari libur bursa tidak dicek."""
    now = now or dt.datetime.now(WIB)
    if now.weekday() >= 5:
        return False
    return now.replace(hour=9, minute=0) <= now <= now.replace(hour=15, minute=50)


# --------------------------------------------------------------------- rekam
def record_ticks(tickers: list[str], provider=None, interval: str = "1m") -> int:
    """Jalur cepat: harga penutup seluruh universe lewat spark."""
    prov = provider or get_provider()
    if not hasattr(prov, "pulse"):
        return 0
    pulses = prov.pulse(tickers, interval=interval, rng="1d")
    rows = []
    for t, s in pulses.items():
        for ts, c in s.items():
            rows.append((t, ts.strftime("%Y-%m-%d %H:%M:%S"), float(c)))
    if not rows:
        return 0
    con = connect()
    try:
        con.executemany("INSERT OR REPLACE INTO ticks VALUES (?,?,?)", rows)
        con.commit()
    finally:
        con.close()
    return len(rows)


def record_bars(tickers: list[str], interval: str = "5m", provider=None,
                rng: str = "1d") -> int:
    """Jalur lambat: OHLCV penuh per ticker lewat endpoint chart."""
    prov = provider or get_provider()
    rows = []
    for t in tickers:
        df = prov.intraday(t, interval=interval, rng=rng)
        if df is None or df.empty:
            continue
        for ts, r in df.iterrows():
            rows.append((t, ts.strftime("%Y-%m-%d %H:%M:%S"), interval,
                         float(r["open"]), float(r["high"]), float(r["low"]),
                         float(r["close"]), float(r["volume"])))
        time.sleep(0.12)                      # sopan terhadap penyedia
    if not rows:
        return 0
    con = connect()
    try:
        con.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?)", rows)
        con.commit()
    finally:
        con.close()
    return len(rows)


def log_run(mulai, jalur, n_ticker, n_baris, penyedia, catatan=""):
    con = connect()
    try:
        con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
                    (mulai.isoformat(timespec="seconds"),
                     dt.datetime.now(WIB).isoformat(timespec="seconds"),
                     jalur, n_ticker, n_baris, penyedia, catatan))
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------- status
def status() -> dict:
    if not DB_PATH.exists():
        return {"ada": False}
    con = connect()
    try:
        q = lambda s: con.execute(s).fetchone()                    # noqa: E731
        n_tick = q("SELECT COUNT(*) FROM ticks")[0]
        n_bar = q("SELECT COUNT(*) FROM bars")[0]
        t_rng = q("SELECT MIN(ts), MAX(ts) FROM ticks")
        b_rng = q("SELECT MIN(ts), MAX(ts) FROM bars")
        n_tk = q("SELECT COUNT(DISTINCT ticker) FROM ticks")[0]
        hari = q("SELECT COUNT(DISTINCT substr(ts,1,10)) FROM ticks")[0]
        hari_bar = q("SELECT COUNT(DISTINCT substr(ts,1,10)) FROM bars")[0]
        runs = q("SELECT COUNT(*) FROM runs")[0]
        return {"ada": True, "db": str(DB_PATH),
                "mb": round(DB_PATH.stat().st_size / 1e6, 2),
                "ticks": n_tick, "bars": n_bar, "ticker": n_tk,
                "hari_tick": hari, "hari_bar": hari_bar, "runs": runs,
                "tick_dari": t_rng[0], "tick_sampai": t_rng[1],
                "bar_dari": b_rng[0], "bar_sampai": b_rng[1]}
    finally:
        con.close()


def load_bars(ticker: str | None = None, interval: str = "5m",
              sejak: str | None = None) -> pd.DataFrame:
    """Baca bar terekam untuk backtest intraday."""
    con = connect()
    try:
        sql = "SELECT ticker, ts, open, high, low, close, volume FROM bars WHERE interval=?"
        args: list = [interval]
        if ticker:
            sql += " AND ticker=?"
            args.append(ticker)
        if sejak:
            sql += " AND ts>=?"
            args.append(sejak)
        sql += " ORDER BY ticker, ts"
        df = pd.read_sql_query(sql, con, params=args, parse_dates=["ts"])
    finally:
        con.close()
    return df.set_index("ts") if len(df) else df


def load_ticks(ticker: str | None = None, sejak: str | None = None) -> pd.DataFrame:
    con = connect()
    try:
        sql = "SELECT ticker, ts, close FROM ticks WHERE 1=1"
        args: list = []
        if ticker:
            sql += " AND ticker=?"
            args.append(ticker)
        if sejak:
            sql += " AND ts>=?"
            args.append(sejak)
        sql += " ORDER BY ticker, ts"
        df = pd.read_sql_query(sql, con, params=args, parse_dates=["ts"])
    finally:
        con.close()
    return df.set_index("ts") if len(df) else df


# --------------------------------------------------------------------- sesi
def run_session(tickers: list[str], poll_tick: int = 60, poll_bar: int = 300,
                bar_tickers: list[str] | None = None, interval_bar: str = "5m",
                max_menit: int | None = None, paksa: bool = False) -> None:
    """Loop perekaman sepanjang jam bursa."""
    prov = get_provider()
    bar_tickers = bar_tickers or tickers[:25]
    mulai = dt.datetime.now(WIB)
    last_bar = 0.0
    total_t = total_b = 0

    print(f"Perekam aktif · penyedia={prov.name} · {len(tickers)} ticker tape, "
          f"{len(bar_tickers)} ticker bar")
    print(f"DB: {DB_PATH}")
    if not market_open() and not paksa:
        print("Bursa tutup. Pakai --paksa untuk merekam di luar jam bursa "
              "(berguna untuk menangkap bar sesi terakhir).")
        return

    try:
        while True:
            now = dt.datetime.now(WIB)
            if max_menit and (now - mulai).total_seconds() > max_menit * 60:
                print("Batas waktu tercapai.")
                break
            if not market_open(now) and not paksa:
                print("Bursa tutup — perekaman berhenti.")
                break

            n = record_ticks(tickers, provider=prov)
            total_t += n
            if time.time() - last_bar > poll_bar:
                nb = record_bars(bar_tickers, interval=interval_bar, provider=prov)
                total_b += nb
                last_bar = time.time()
                print(f"  {now:%H:%M:%S}  tape +{n:5}  bar +{nb:5}  "
                      f"(total {total_t:,} / {total_b:,})")
            else:
                print(f"  {now:%H:%M:%S}  tape +{n:5}")
            time.sleep(poll_tick)
    except KeyboardInterrupt:
        print("\nDihentikan pengguna.")
    finally:
        log_run(mulai, "sesi", len(tickers), total_t + total_b, prov.name)
        print(f"Selesai. Tape {total_t:,} baris, bar {total_b:,} baris.")


def universe_likuid() -> list[str]:
    from .config import OUT_DIR
    p = OUT_DIR / "screening.csv"
    if not p.exists():
        return []
    d = pd.read_csv(p)
    return list(d[d["likuid"]]["ticker"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Perekam data intraday IDX")
    ap.add_argument("--status", action="store_true", help="tampilkan isi database")
    ap.add_argument("--sekali", action="store_true", help="rekam satu putaran lalu keluar")
    ap.add_argument("--sesi", action="store_true", help="loop sepanjang jam bursa")
    ap.add_argument("--paksa", action="store_true", help="rekam walau bursa tutup")
    ap.add_argument("--poll", type=int, default=60, help="detik antar poll tape")
    ap.add_argument("--menit", type=int, default=None, help="batas durasi (menit)")
    a = ap.parse_args()

    if a.status:
        s = status()
        if not s.get("ada"):
            print("Database belum ada. Jalankan --sekali dulu.")
        else:
            print("=" * 62)
            print("STATUS PEREKAM INTRADAY IDX")
            print("=" * 62)
            print(f"  Berkas        : {s['db']} ({s['mb']} MB)")
            print(f"  Baris tape    : {s['ticks']:,}  ({s['ticker']} ticker, "
                  f"{s['hari_tick']} hari)")
            print(f"  Baris bar     : {s['bars']:,}  ({s['hari_bar']} hari)")
            print(f"  Rentang tape  : {s['tick_dari']}  ->  {s['tick_sampai']}")
            print(f"  Rentang bar   : {s['bar_dari']}  ->  {s['bar_sampai']}")
            print(f"  Sesi tercatat : {s['runs']}")
        raise SystemExit

    uni = universe_likuid()
    if not uni:
        raise SystemExit("Jalankan run_pipeline.py dulu untuk membuat output/screening.csv")

    if a.sekali:
        t0 = dt.datetime.now(WIB)
        prov = get_provider()
        nt = record_ticks(uni, provider=prov)
        nb = record_bars(uni[:25], interval="5m", provider=prov)
        log_run(t0, "sekali", len(uni), nt + nb, prov.name)
        print(f"Terekam: {nt:,} baris tape, {nb:,} baris bar (penyedia {prov.name})")
        s = status()
        print(f"Total sekarang: {s['ticks']:,} tape / {s['bars']:,} bar "
              f"dalam {s['mb']} MB")
    elif a.sesi:
        run_session(uni, poll_tick=a.poll, max_menit=a.menit, paksa=a.paksa)
    else:
        ap.print_help()
