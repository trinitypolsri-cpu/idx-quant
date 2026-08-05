"""Mesin screener: state in-memory, refresh latar belakang, query terfilter."""

from __future__ import annotations

import datetime as dt
import threading
import time

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import setups as st
from idxquant.indicators import enrich
from idxquant.universe import BENCHMARK, CANDIDATES, sector_of

WIB = dt.timezone(dt.timedelta(hours=7))

# Tiga setup dihapus dari daftar karena terbukti tidak signifikan
# (RSLeader t=0,89 · PullbackUptrend t=0,44 · MeanReversion N=10).
# Bukti historisnya tetap disimpan di SETUP_EVIDENCE untuk rujukan.
SETUP_LABELS = {
    "BaseBreakout":    ("Base Breakout", "Jebol tertinggi 55 hari + volume 1,8x", "kuat"),
    "FVGBullish":      ("FVG Bullish (ICT)", "Celah tiga-lilin, ketidakseimbangan", "kuat"),
    "KumoNaik":        ("Kumo Naik [filter]", "Di atas awan Ichimoku, awan naik", "kuat"),
    "SqueezeBreakout": ("Squeeze Breakout", "Volatilitas mampat lalu jebol", "sedang"),
    "ADRTenang":       ("ADR Tenang [filter]", "Rentang <50% ADR dalam tren naik", "sedang"),
    "TrendTemplate":   ("Trend Template", "Struktur MA rapi, dekat puncak 52mg", "sedang"),
    "MACDMomentum":    ("MACD Momentum [filter]", "MACD >0 dan menguat, di atas MA50", "sedang"),
    "BOSNaik":         ("BOS Naik [filter]", "Harga di atas swing high terakhir", "sedang"),
}

# Bukti dari event study 5 tahun: (avg return 21 hari setelah biaya, jumlah sinyal, t-stat)
# Untuk setup baru, `edge` adalah KELEBIHAN di atas base rate (bukan return mentah),
# karena itulah yang menentukan apakah sinyal menambah nilai. Base rate return 21
# hari untuk emiten likuid setelah biaya: +0,834%.
SETUP_EVIDENCE = {
    "BaseBreakout":    {"edge": 1.58, "n": 1300,  "t": 2.49},
    "FVGBullish":      {"edge": 1.24, "n": 9722,  "t": 5.10},
    "KumoNaik":        {"edge": 1.14, "n": 22498, "t": 7.92},
    "ADRTenang":       {"edge": 1.11, "n": 9579,  "t": 4.45},
    "MACDMomentum":    {"edge": 0.73, "n": 24189, "t": 5.36},
    "BOSNaik":         {"edge": 0.54, "n": 25343, "t": 4.08},
    "SqueezeBreakout": {"edge": 1.01, "n": 1916,  "t": 1.95},
    "TrendTemplate":   {"edge": 0.58, "n": 13471, "t": 3.48},
    "RSLeader":        {"edge": 0.22, "n": 6797,  "t": 0.89},
    "PullbackUptrend": {"edge": 0.11, "n": 2835,  "t": 0.44},
    # N=10 — sampel terlalu kecil untuk dipercaya meski rata-ratanya tinggi
    "MeanReversion":   {"edge": 3.11, "n": 10,    "t": 0.49},
}
SETUP_EDGE = {k: v["edge"] for k, v in SETUP_EVIDENCE.items()}

# Urutan tampilan: keandalan dulu, baru besaran edge. Setup dengan sampel kecil
# atau t-stat lemah tidak boleh muncul di atas hanya karena rata-ratanya besar.
_STRENGTH_RANK = {"kuat": 0, "sedang": 1, "lemah": 2}


class Engine:
    def __init__(self):
        self.prepared: dict[str, pd.DataFrame] = {}
        self.bench: pd.DataFrame | None = None
        self.scan: pd.DataFrame = pd.DataFrame()
        self.last_refresh: dt.datetime | None = None
        self.status = "belum dimuat"
        self.progress = {"done": 0, "total": 0}
        self.busy = False
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- refresh
    def refresh(self, use_cache: bool = True) -> None:
        """Muat ulang seluruh universe. Aman dipanggil dari thread latar."""
        with self._lock:
            if self.busy:
                return
            self.busy = True
        try:
            self.status = "mengunduh IHSG..."
            self.progress = {"done": 0, "total": len(CANDIDATES)}
            bench = dl.load(BENCHMARK, rng="5y", use_cache=use_cache)
            if bench is None:
                self.status = "gagal: data IHSG tidak terambil"
                return
            self.bench = bench

            self.status = f"mengunduh {len(CANDIDATES)} emiten..."
            data = dl.load_many(CANDIDATES, rng="5y", use_cache=use_cache, verbose=False)
            self.progress = {"done": len(data), "total": len(CANDIDATES)}

            self.status = "menghitung indikator & sinyal..."
            self.prepared = st.prepare(data, bench)

            self.status = "memindai..."
            self.scan = st.scan(self.prepared)
            self.last_refresh = dt.datetime.now(WIB)
            self.status = "siap"
        except Exception as e:                                    # noqa: BLE001
            self.status = f"gagal: {e}"
        finally:
            self.busy = False

    def refresh_async(self, use_cache: bool = True) -> None:
        threading.Thread(target=self.refresh, args=(use_cache,), daemon=True).start()

    # ---------------------------------------------------------------- status
    def market_state(self) -> dict:
        """Status bursa IDX (Senin-Jumat 09:00-15:50 WIB, di luar hari libur)."""
        now = dt.datetime.now(WIB)
        weekday = now.weekday() < 5
        openp = now.replace(hour=9, minute=0, second=0, microsecond=0)
        closep = now.replace(hour=15, minute=50, second=0, microsecond=0)
        if not weekday:
            state, label = "closed", "Bursa tutup (akhir pekan)"
        elif now < openp:
            state, label = "pre", "Pra-pembukaan"
        elif now <= closep:
            state, label = "open", "Bursa buka"
        else:
            state, label = "closed", "Bursa tutup"
        return {"state": state, "label": label, "waktu_wib": now.strftime("%d %b %Y %H:%M")}

    def overview(self) -> dict:
        if self.bench is None or self.scan.empty:
            return {"siap": False, "status": self.status,
                    "progress": self.progress, "market": self.market_state()}

        b = enrich(self.bench)
        r = b.iloc[-1]
        liq = self.scan[self.scan["likuid"]]
        above200 = float(liq["di_atas_ma200"].mean()) if len(liq) else 0.0

        return {
            "siap": True,
            "status": self.status,
            "market": self.market_state(),
            "tanggal_data": b.index[-1].strftime("%d %b %Y"),
            "last_refresh": self.last_refresh.strftime("%d %b %Y %H:%M WIB")
                            if self.last_refresh else None,
            "ihsg": {
                "level": round(float(r["close"]), 2),
                "ma50": round(float(r["ma50"]), 0),
                "ma200": round(float(r["ma200"]), 0),
                "vs_ma200": round(float(r["close"] / r["ma200"] - 1) * 100, 2),
                "dari_puncak": round(float(r["from_hi"]) * 100, 2),
                "ret_1b": round(float(r["roc21"]) * 100, 2),
                "ret_3b": round(float(r["roc63"]) * 100, 2),
                "rsi": round(float(r["rsi14"]), 1),
            },
            "regime": "risk-on" if r["close"] > r["ma200"] else "risk-off",
            "breadth_ma200": round(above200 * 100, 1),
            "n_likuid": int(len(liq)),
            "n_total": int(len(self.scan)),
            "n_sinyal": int((liq["n_sinyal"] > 0).sum()) if len(liq) else 0,
        }

    # ---------------------------------------------------------------- query
    def screen(self, setup: str = "", sector: str = "", min_skor: float = 0,
               min_turnover: float = 5.0, only_above_ma200: bool = False,
               sort: str = "skor", limit: int = 300) -> list[dict]:
        if self.scan.empty:
            return []
        d = self.scan.copy()
        d = d[d["turnover_med20_M"] >= min_turnover * 1000]     # input dalam Rp miliar
        d = d[d["close"] >= 100]
        if setup:
            col = f"sig_{setup}"
            if col in d:
                d = d[d[col]]
        if sector:
            d = d[d["sektor"] == sector]
        if min_skor:
            d = d[d["skor"] >= min_skor]
        if only_above_ma200:
            d = d[d["di_atas_ma200"]]

        asc = sort in ("rsi14", "atr_pct", "from_hi_asc")
        key = "from_hi" if sort == "from_hi_asc" else sort
        if key in d:
            d = d.sort_values(key, ascending=asc)

        rows = []
        for r in d.head(limit).itertuples():
            sigs = [k for k in SETUP_LABELS if getattr(r, f"sig_{k}", False)]
            rows.append({
                "ticker": r.ticker,
                "sektor": r.sektor,
                "close": float(r.close),
                "skor": float(r.skor),
                "ret_1m": _p(r.ret_1m), "ret_3m": _p(r.ret_3m),
                "ret_6m": _p(r.ret_6m), "ret_12m": _p(r.ret_12m),
                "from_hi": _p(r.from_hi),
                "rsi": round(float(r.rsi14), 1) if pd.notna(r.rsi14) else None,
                "adx": round(float(r.adx14), 1) if pd.notna(r.adx14) else None,
                "atr_pct": _p(r.atr_pct, 2),
                "vol_ratio": round(float(r.vol_ratio), 2) if pd.notna(r.vol_ratio) else None,
                "turnover_M": round(float(r.turnover_med20_M) / 1000, 1),   # Rp miliar
                "di_atas_ma200": bool(r.di_atas_ma200),
                "setups": sigs,
                "edge": max([SETUP_EDGE.get(s, 0) for s in sigs], default=0),
            })
        return rows

    def sectors(self) -> list[dict]:
        if self.scan.empty:
            return []
        liq = self.scan[self.scan["likuid"]]
        if liq.empty:
            return []
        g = liq.groupby("sektor")
        out = []
        for name, sub in g:
            out.append({
                "sektor": name, "n": int(len(sub)),
                "ret_1m": _p(sub["ret_1m"].median()),
                "ret_3m": _p(sub["ret_3m"].median()),
                "ret_6m": _p(sub["ret_6m"].median()),
                "ret_12m": _p(sub["ret_12m"].median()),
                "above_ma200": round(float(sub["di_atas_ma200"].mean()) * 100, 0),
                "skor": round(float(sub["skor"].median()), 1),
                "n_sinyal": int((sub["n_sinyal"] > 0).sum()),
                "top": list(sub.nlargest(3, "skor")["ticker"]),
            })
        return sorted(out, key=lambda x: (x["ret_1m"] is None, -(x["ret_1m"] or 0)))

    def setup_counts(self) -> list[dict]:
        if self.scan.empty:
            return []
        liq = self.scan[self.scan["likuid"]]
        out = []
        for key, (label, desc, strength) in SETUP_LABELS.items():
            col = f"sig_{key}"
            hits = liq[liq[col]] if col in liq else liq.iloc[:0]
            ev = SETUP_EVIDENCE.get(key, {"edge": 0, "n": 0, "t": 0})
            unreliable = ev["n"] < 200 or ev["t"] < 1.5
            out.append({
                "key": key, "label": label, "desc": desc, "strength": strength,
                "edge": ev["edge"], "ev_n": ev["n"], "ev_t": ev["t"],
                "unreliable": unreliable,
                "n": int(len(hits)),
                "tickers": list(hits.nlargest(8, "skor")["ticker"]),
            })
        return sorted(out, key=lambda x: (_STRENGTH_RANK.get(x["strength"], 9), -x["edge"]))

    # ---------------------------------------------------------------- scalping
    def scalping(self, top: int = 40, interval: str = "5m",
                 max_age_sec: int = 120) -> dict:
        """Scan momentum intraday. Di-cache singkat karena butuh ~20s per panggilan."""
        from idxquant.providers import get_provider
        from idxquant.scalping import scan_funnel

        now = time.time()
        cache = getattr(self, "_scalp_cache", None)
        if (cache and cache["interval"] == interval and cache["top"] == top
                and now - cache["ts"] < max_age_sec):
            return cache["payload"]

        if self.scan.empty:
            return {"siap": False, "pesan": "data harian belum dimuat"}

        # Corong: saring SELURUH emiten likuid lewat spark, lalu gali top-N via chart.
        liq = self.scan[self.scan["likuid"]]
        tickers = list(liq["ticker"])
        prev = {}
        for t in tickers:
            d = self.prepared.get(t)
            if d is not None and len(d) > 1:
                prev[t] = float(d["close"].iloc[-2])

        prov = get_provider()
        df, stats = scan_funnel(tickers, prev_closes=prev, interval=interval,
                                top_deep=top, provider=prov)
        rows = [] if df.empty else df.replace({np.nan: None}).to_dict("records")
        payload = {
            "siap": True, "penyedia": prov.name, "interval": interval,
            "n": len(rows), "rows": rows,
            "dipindai": stats["tahap1_ticker"], "digali": stats["tahap2_ticker"],
            "detik": round(stats["detik_tahap1"] + stats["detik_tahap2"], 1),
            "metode": stats["metode"],
            "catatan": ("Data Yahoo delay 10-20 menit — layak untuk riset dan seleksi "
                        "kandidat, TIDAK untuk eksekusi scalping. Feed realtime IDX "
                        "berlisensi dan berbayar; tidak ada versi gratisnya.")
                       if prov.name == "yahoo" else "",
        }
        self._scalp_cache = {"ts": now, "interval": interval, "top": top,
                             "payload": payload}
        return payload

    def chart(self, ticker: str, rng: str = "6mo", interval: str = "1d") -> dict:
        """Data chart. Interval harian pakai cache; intraday ditarik langsung."""
        if interval == "1d" and ticker in self.prepared:
            d = self.prepared[ticker]
            n = {"1mo": 22, "3mo": 66, "6mo": 130, "1y": 250, "2y": 500}.get(rng, 130)
            d = d.tail(n)
            return {
                "ticker": ticker, "sektor": sector_of(ticker), "interval": interval,
                "t": [x.strftime("%Y-%m-%d") for x in d.index],
                "o": _l(d["open"]), "h": _l(d["high"]), "l": _l(d["low"]),
                "c": _l(d["close"]), "v": _l(d["volume"]),
                "ma20": _l(d["ma20"]), "ma50": _l(d["ma50"]), "ma200": _l(d["ma200"]),
                "bb_up": _l(d["bb_up"]), "bb_lo": _l(d["bb_lo"]),
            }
        raw = dl.fetch_one(ticker, rng=rng, interval=interval)
        if raw is None or raw.empty:
            return {"ticker": ticker, "error": "data tidak tersedia"}
        fmt = "%Y-%m-%d" if interval == "1d" else "%d/%m %H:%M"
        return {
            "ticker": ticker, "sektor": sector_of(ticker), "interval": interval,
            "t": [x.strftime(fmt) for x in raw.index],
            "o": _l(raw["open"]), "h": _l(raw["high"]), "l": _l(raw["low"]),
            "c": _l(raw["close"]), "v": _l(raw["volume"]),
            "ma20": _l(raw["close"].rolling(20).mean()),
            "ma50": _l(raw["close"].rolling(50).mean()),
            "ma200": [], "bb_up": [], "bb_lo": [],
        }


def _p(v, d=1):
    return None if v is None or pd.isna(v) else round(float(v) * 100, d)


def _l(s):
    return [None if pd.isna(x) else round(float(x), 4) for x in s]


ENGINE = Engine()
