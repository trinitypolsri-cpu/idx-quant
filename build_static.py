"""Bangun dashboard statis + kirim alert — dijalankan GitHub Actions tanpa server.

Alurnya: unduh data -> pindai -> tulis JSON ke docs/data/ -> GitHub Pages menyajikannya.
Tidak ada server yang perlu dibayar atau dinyalakan.

    python build_static.py            # bangun JSON saja
    python build_static.py --alert    # bangun + kirim notifikasi
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import warnings
from pathlib import Path

import pandas as pd

from idxquant import alerts as al
from idxquant import data as dl
from idxquant import setups as st
from idxquant import wyckoff as wy
from idxquant.indicators import enrich
from idxquant.levels import analisa_level, format_teks
from idxquant.providers import get_provider
from idxquant.scalping import scan_funnel
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
DATA = DOCS / "data"
WIB = dt.timezone(dt.timedelta(hours=7))


def tulis(nama: str, obj) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / nama).write_text(json.dumps(obj, ensure_ascii=False, default=str),
                             encoding="utf-8")
    print(f"  tulis docs/data/{nama}")


def main(kirim_alert: bool = False, top_scalp: int = 20):
    now = dt.datetime.now(WIB)
    print(f"Build statis · {now:%d %b %Y %H:%M WIB}")

    bench = dl.load(BENCHMARK, rng="5y", use_cache=False)
    if bench is None:
        raise SystemExit("Gagal mengambil IHSG")
    data = dl.load_many(CANDIDATES, rng="5y", use_cache=False, verbose=False)
    print(f"  {len(data)} emiten terunduh")

    prep = st.prepare(data, bench)
    scan = st.scan(prep)
    liq = scan[scan["likuid"]].copy()

    # ---- ringkasan pasar ----
    b = enrich(bench)
    r = b.iloc[-1]
    ringkas = {
        "waktu": now.isoformat(timespec="seconds"),
        "tanggal_data": b.index[-1].strftime("%Y-%m-%d"),
        "ihsg": round(float(r["close"]), 2),
        "ma50": round(float(r["ma50"]), 0),
        "ma200": round(float(r["ma200"]), 0),
        "vs_ma200": round(float(r["close"] / r["ma200"] - 1) * 100, 2),
        "dari_puncak": round(float(r["from_hi"]) * 100, 2),
        "ret_1b": round(float(r["roc21"]) * 100, 2),
        "regime": "risk-on" if r["close"] > r["ma200"] else "risk-off",
        "breadth_ma200": round(float(liq["di_atas_ma200"].mean()) * 100, 1),
        "n_likuid": int(len(liq)),
        "n_total": int(len(scan)),
    }
    tulis("ringkasan.json", ringkas)

    # ---- screener harian ----
    kol = ["ticker", "sektor", "close", "skor", "ret_1m", "ret_3m", "ret_6m",
           "ret_12m", "from_hi", "rsi14", "adx14", "atr_pct", "vol_ratio",
           "turnover_med20_M", "di_atas_ma200"]
    rows = []
    for x in liq.itertuples():
        sig = [k for k in list(st.SETUPS) + ["RSLeader"]
               if getattr(x, f"sig_{k}", False)]
        d = {k: getattr(x, k) for k in kol if hasattr(x, k)}
        for k in ("ret_1m", "ret_3m", "ret_6m", "ret_12m", "from_hi", "atr_pct"):
            if d.get(k) is not None and pd.notna(d[k]):
                d[k] = round(float(d[k]) * 100, 2)
        d["turnover_M"] = round(float(x.turnover_med20_M) / 1000, 1)
        d.pop("turnover_med20_M", None)
        d["rsi"] = None if pd.isna(x.rsi14) else round(float(x.rsi14), 1)
        d["adx"] = None if pd.isna(x.adx14) else round(float(x.adx14), 1)
        d.pop("rsi14", None); d.pop("adx14", None)
        d["setups"] = sig
        d["di_atas_ma200"] = bool(x.di_atas_ma200)
        rows.append(d)
    rows.sort(key=lambda z: -(z.get("skor") or 0))
    tulis("screener.json", {"rows": rows})

    # ---- sektor ----
    g = liq.groupby("sektor")
    sekt = [{
        "sektor": n, "n": int(len(s)),
        "ret_1m": round(float(s["ret_1m"].median()) * 100, 1),
        "ret_3m": round(float(s["ret_3m"].median()) * 100, 1),
        "ret_12m": round(float(s["ret_12m"].median()) * 100, 1),
        "above_ma200": round(float(s["di_atas_ma200"].mean()) * 100, 0),
        "n_sinyal": int((s["n_sinyal"] > 0).sum()),
    } for n, s in g]
    sekt.sort(key=lambda z: -z["ret_1m"])
    tulis("sektor.json", {"rows": sekt})

    # ---- scalping intraday ----
    prev = {t: float(prep[t]["close"].iloc[-2]) for t in liq["ticker"]
            if len(prep.get(t, [])) > 1}
    prov = get_provider()
    sc_df, stats = scan_funnel(list(liq["ticker"]), prev_closes=prev,
                               top_deep=top_scalp, provider=prov)
    sc_rows = [] if sc_df.empty else sc_df.where(pd.notna(sc_df), None).to_dict("records")
    tulis("scalping.json", {"rows": sc_rows, "penyedia": prov.name,
                            "dipindai": stats["tahap1_ticker"],
                            "digali": stats["tahap2_ticker"]})

    # ---- model gabungan: satu probabilitas terkalibrasi ----
    from idxquant import combined as cb
    from idxquant import journal as jr

    likuid_set = set(liq["ticker"])
    print("  melatih model gabungan ...")
    P = cb.bangun_panel(prep, likuid_set)
    gab_rows = []
    if not P.empty:
        r = cb.latih_dan_uji(P)
        if "error" not in r:
            pk = cb.peluang_hari_ini(r["model"], r.get("kalibrator"),
                                     prep, likuid_set, r["fitur"])
            peta_setup = {x["ticker"]: x["setups"] for x in rows}
            gab_rows = [{
                "ticker": t.ticker, "harga": round(float(t.close)),
                "peluang": round(float(t.peluang) * 100, 2),
                "setups": peta_setup.get(t.ticker, []),
            } for t in pk.itertuples()]
            tulis("gabungan.json", {
                "rows": gab_rows[:40],
                "auc": round(r["auc"], 4),
                "n_uji": r["n_uji"],
                "base_return": round(r["base_return"] * 100, 3),
                "n_fitur": len(r["fitur"]),
                "kalibrasi": r["kalibrasi"].reset_index().astype(str).to_dict("records"),
            })
            print(f"    AUC {r['auc']:.4f} · {len(r['fitur'])} fitur · "
                  f"base return {r['base_return']*100:+.2f}%")

            # ---- catat prediksi ke jurnal (sebelum hasilnya diketahui) ----
            tgl = b.index[-1].strftime("%Y-%m-%d")
            n = jr.catat(gab_rows[:40], tgl, base=r["base_return"])
            print(f"    jurnal: {n} prediksi baru dicatat untuk {tgl}")

    # ---- data grafik untuk HP ----
    kandidat_chart = [x["ticker"] for x in gab_rows[:30]] or \
                     [x["ticker"] for x in rows[:30]]
    charts = {}
    for t in kandidat_chart:
        d = prep.get(t)
        if d is None or len(d) < 70:
            continue
        w = d.tail(60)
        charts[t] = {
            "t": [x.strftime("%d/%m") for x in w.index],
            # dibulatkan agar payload tetap ringan di jaringan seluler
            "o": [round(float(v), 1) for v in w["open"]],
            "h": [round(float(v), 1) for v in w["high"]],
            "l": [round(float(v), 1) for v in w["low"]],
            "c": [round(float(v), 1) for v in w["close"]],
            "v": [int(v) for v in w["volume"].fillna(0)],
            "ma20": [None if pd.isna(v) else round(float(v), 1) for v in w["ma20"]],
            "ma50": [None if pd.isna(v) else round(float(v), 1) for v in w["ma50"]],
        }
    tulis("chart.json", charts)

    # ---- level: kandidat bersinyal DAN kandidat model gabungan ----
    # Harus setelah blok gabungan, karena tab Peluang di HP menampilkan emiten
    # yang belum tentu punya setup — tanpa ini levelnya kosong di sana.
    dari_gab = [{"ticker": g["ticker"], "setups": g.get("setups", [])}
                for g in gab_rows[:30]]
    sudah, kandidat = set(), []
    for x in [x for x in rows if x["setups"]][:25] + dari_gab:
        if x["ticker"] not in sudah:
            sudah.add(x["ticker"])
            kandidat.append(x)
    lv = {}
    for x in kandidat:
        d = prep.get(x["ticker"])
        if d is None or len(d) < 30:
            continue
        a = analisa_level(d)
        if a:
            lv[x["ticker"]] = a
            x["level_teks"] = format_teks(x["ticker"], a)
    tulis("level.json", lv)

    # ---- kandidat ARA ----
    from idxquant import ara as ar
    A = ar.kumpulkan(prep)
    if not A.empty:
        hari = A[A.index == A.index.max()].copy()
        hari["skor_ara"] = hari.apply(ar.skor, axis=1)
        hari["sisa_ara"] = ((hari["limit"] - hari["ret"]) * 100).round(1)
        hari = hari[hari["skor_ara"] >= 20].nlargest(15, "skor_ara")
        ara_rows = [{
            "ticker": r.ticker, "harga": round(float(r.close)),
            "skor": round(float(r.skor_ara)),
            "ret": round(float(r.ret) * 100, 2),
            "sisa_ara": float(r.sisa_ara),
            "rvol": round(float(r.rvol), 2) if pd.notna(r.rvol) else None,
            "pos_close": round(float(r.pos_close) * 100) if pd.notna(r.pos_close) else None,
            "ara_kemarin": bool(r.ara_kemarin),
            # Peluang dari tabel kalibrasi historis 302rb observasi
            "peluang": (14.3 if r.skor_ara >= 70 else 11.9 if r.skor_ara >= 60
                        else 4.4 if r.skor_ara >= 50 else 1.3 if r.skor_ara >= 40
                        else 0.5 if r.skor_ara >= 30 else 0.4),
        } for r in hari.itertuples()]
        tulis("ara.json", {"rows": ara_rows, "base_rate": 0.171,
                           "tanggal": str(A.index.max().date())})

    # ---- Wyckoff dari bar intraday hasil scan ----
    wy_rows = []
    for t in [x["ticker"] for x in sc_rows[:top_scalp]]:
        bars = prov.intraday(t, interval="5m", rng="1d")
        if bars is None or len(bars) < 25:
            continue
        s = wy.summarise(t, bars)
        if s.get("n_bar"):
            wy_rows.append(s)
    tulis("wyckoff.json", {"rows": wy_rows})

    # ---- alert ----
    if kirim_alert:
        a = []
        a += al.cek_setup_harian(kandidat)
        a += al.cek_momentum_intraday(sc_rows)
        a += al.cek_wyckoff(wy_rows)
        if a:
            hasil = al.proses(a, kirim_beneran=True)
            indiv = sum(1 for x in hasil if x.get("mode") == "individual")
            ring = any(x.get("mode") == "ringkasan" for x in hasil)
            print(f"  alert: {len(hasil)} sinyal -> {indiv + (1 if ring else 0)} notifikasi")
        else:
            print("  alert: tidak ada sinyal baru")
        tulis("alert.json", {"riwayat": al.riwayat(30)})

    # ---- salin UI mobile ----
    src = ROOT / "app" / "static" / "mobile.html"
    if src.exists():
        shutil.copy(src, DOCS / "index.html")
        print("  salin docs/index.html")

    print("Selesai.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alert", action="store_true")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()
    main(kirim_alert=a.alert, top_scalp=a.top)
