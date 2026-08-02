"""Jurnal prediksi — satu-satunya cara membuktikan sistem ini benar atau tidak.

INILAH JAWABAN untuk "bagaimana membuktikan". Semua backtest adalah janji tentang
masa depan yang diuji pada masa lalu. Jurnal ini menguji janji itu pada masa depan
yang sesungguhnya, dengan aturan yang tidak bisa dicurangi:

  1. Setiap pemindaian MENULIS prediksinya lebih dulu — ticker, harga, probabilitas,
     tanggal. Ditulis SEBELUM hasilnya diketahui.
  2. Baris yang sudah tertulis TIDAK PERNAH diubah. Tidak ada revisi, tidak ada
     penghapusan prediksi yang memalukan.
  3. Setelah 21 hari bursa, harga penutup diambil dan return dihitung otomatis.
  4. Prediksi dibandingkan dengan kenyataan: kalau model bilang 3%, apakah benar
     terjadi ~3% waktu?

Yang membuat ini jujur adalah urutannya. Backtest bisa dioptimasi berulang sampai
terlihat bagus (dan tanpa sadar Anda memilih parameter yang cocok dengan masa lalu).
Prediksi yang ditulis lebih dulu tidak bisa diperlakukan begitu.

    python -m idxquant.journal --status
    python -m idxquant.journal --nilai      # hitung hasil yang sudah matang
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3

import pandas as pd

from .config import DATA_DIR

WIB = dt.timezone(dt.timedelta(hours=7))
DB = DATA_DIR / "jurnal.db"
HORIZON = 21

SCHEMA = """
CREATE TABLE IF NOT EXISTS prediksi (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    dibuat    TEXT NOT NULL,          -- kapan prediksi ditulis
    tgl_data  TEXT NOT NULL,          -- tanggal bar terakhir yang dipakai
    ticker    TEXT NOT NULL,
    sumber    TEXT NOT NULL,          -- 'gabungan' | nama setup
    harga     REAL NOT NULL,
    peluang   REAL,                   -- probabilitas terkalibrasi (0-1)
    setups    TEXT,                   -- daftar setup aktif
    horizon   INTEGER NOT NULL,
    -- diisi belakangan, TIDAK boleh diubah setelah terisi
    tgl_nilai TEXT,
    harga_exit REAL,
    ret       REAL,
    unggul    INTEGER,                -- 1 bila mengalahkan base rate
    UNIQUE(tgl_data, ticker, sumber)
);
CREATE INDEX IF NOT EXISTS idx_pred_tgl ON prediksi(tgl_data);
CREATE TABLE IF NOT EXISTS base_rate (
    tgl_data TEXT PRIMARY KEY, nilai REAL
);
"""


def _con():
    con = sqlite3.connect(DB, timeout=30)
    con.executescript(SCHEMA)
    return con


def catat(rows: list[dict], tgl_data: str, base: float | None = None) -> int:
    """Tulis prediksi. UNIQUE mencegah satu tanggal tercatat dua kali."""
    if not rows:
        return 0
    now = dt.datetime.now(WIB).isoformat(timespec="seconds")
    con = _con()
    try:
        n = 0
        for r in rows:
            try:
                con.execute(
                    "INSERT INTO prediksi (dibuat,tgl_data,ticker,sumber,harga,"
                    "peluang,setups,horizon) VALUES (?,?,?,?,?,?,?,?)",
                    (now, tgl_data, r["ticker"], r.get("sumber", "gabungan"),
                     float(r["harga"]), r.get("peluang"),
                     ",".join(r.get("setups", [])) or None, HORIZON))
                n += 1
            except sqlite3.IntegrityError:
                pass                      # sudah tercatat — jangan ditimpa
        if base is not None:
            con.execute("INSERT OR IGNORE INTO base_rate VALUES (?,?)",
                        (tgl_data, float(base)))
        con.commit()
        return n
    finally:
        con.close()


def nilai(harga_fn) -> int:
    """Isi hasil untuk prediksi yang sudah lewat horizon.

    `harga_fn(ticker) -> pd.Series` mengembalikan deret harga penutup berindeks
    tanggal. Hanya baris dengan `ret` masih NULL yang disentuh.
    """
    con = _con()
    try:
        belum = pd.read_sql_query(
            "SELECT id,tgl_data,ticker,harga,horizon FROM prediksi WHERE ret IS NULL",
            con)
        if belum.empty:
            return 0
        base = dict(con.execute("SELECT tgl_data,nilai FROM base_rate").fetchall())
        terisi = 0
        for r in belum.itertuples():
            s = harga_fn(r.ticker)
            if s is None or s.empty:
                continue
            idx = s.index
            pos = idx.searchsorted(pd.Timestamp(r.tgl_data))
            j = pos + r.horizon
            if j >= len(idx):
                continue                  # belum matang
            exit_px = float(s.iloc[j])
            ret = exit_px / float(r.harga) - 1
            b = base.get(r.tgl_data)
            unggul = None if b is None else int(ret > b)
            con.execute(
                "UPDATE prediksi SET tgl_nilai=?,harga_exit=?,ret=?,unggul=? "
                "WHERE id=? AND ret IS NULL",
                (str(idx[j].date()), exit_px, ret, unggul, r.id))
            terisi += 1
        con.commit()
        return terisi
    finally:
        con.close()


def status() -> dict:
    if not DB.exists():
        return {"ada": False}
    con = _con()
    try:
        q = lambda s: con.execute(s).fetchone()                     # noqa: E731
        total = q("SELECT COUNT(*) FROM prediksi")[0]
        matang = q("SELECT COUNT(*) FROM prediksi WHERE ret IS NOT NULL")[0]
        rng = q("SELECT MIN(tgl_data),MAX(tgl_data) FROM prediksi")
        hari = q("SELECT COUNT(DISTINCT tgl_data) FROM prediksi")[0]
        return {"ada": True, "total": total, "matang": matang,
                "menunggu": total - matang, "hari": hari,
                "dari": rng[0], "sampai": rng[1]}
    finally:
        con.close()


def rapor() -> pd.DataFrame:
    """Prediksi vs kenyataan, dikelompokkan per rentang probabilitas."""
    con = _con()
    try:
        df = pd.read_sql_query(
            "SELECT peluang,ret,unggul,sumber FROM prediksi WHERE ret IS NOT NULL", con)
    finally:
        con.close()
    if df.empty or df["peluang"].isna().all():
        return pd.DataFrame()
    df = df.dropna(subset=["peluang"])
    df["kelompok"] = pd.cut(df["peluang"], [0, .2, .35, .5, .65, 1.0],
                            labels=["<20%", "20-35%", "35-50%", "50-65%", ">65%"])
    g = df.groupby("kelompok", observed=True).agg(
        N=("ret", "size"),
        diramal=("peluang", "mean"),
        terjadi=("unggul", "mean"),
        ret_rata=("ret", "mean"))
    g["diramal%"] = (g["diramal"] * 100).round(1)
    g["terjadi%"] = (g["terjadi"] * 100).round(1)
    g["ret_rata%"] = (g["ret_rata"] * 100).round(2)
    g["selisih"] = (g["terjadi%"] - g["diramal%"]).round(1)
    return g[["N", "diramal%", "terjadi%", "selisih", "ret_rata%"]]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Jurnal prediksi")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--nilai", action="store_true")
    ap.add_argument("--rapor", action="store_true")
    a = ap.parse_args()

    if a.nilai:
        from . import data as dl
        cache: dict[str, pd.Series] = {}

        def harga(t):
            if t not in cache:
                d = dl.load(t, rng="1y", use_cache=False)
                cache[t] = d["close"] if d is not None else pd.Series(dtype=float)
            return cache[t]

        n = nilai(harga)
        print(f"{n} prediksi dinilai.")

    s = status()
    if not s.get("ada"):
        print("Jurnal belum ada. Jalankan build_static.py untuk mulai mencatat.")
    else:
        print("=" * 60)
        print("JURNAL PREDIKSI")
        print("=" * 60)
        print(f"  Total prediksi : {s['total']:,}")
        print(f"  Sudah matang   : {s['matang']:,}")
        print(f"  Menunggu       : {s['menunggu']:,}  (butuh {HORIZON} hari bursa)")
        print(f"  Hari tercatat  : {s['hari']}")
        print(f"  Rentang        : {s['dari']} .. {s['sampai']}")
        r = rapor()
        if len(r):
            print("\n--- Prediksi vs kenyataan ---")
            print(r.to_string())
            print("\n'selisih' mendekati nol = probabilitas model dapat dipercaya.")
        elif s["matang"] == 0:
            print(f"\n  Belum ada yang matang. Rapor muncul setelah {HORIZON} hari")
            print("  bursa sejak prediksi pertama.")
