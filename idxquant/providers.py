"""Lapisan penyedia data — Yahoo (default), Sectors.app, Invezgo.

Kenapa abstraksi ini ada: Yahoo gratis tapi delay 10-20 menit dan tanpa data
broker/asing. Untuk scalping serius Anda butuh feed berbayar. Seluruh kode di
atas lapisan ini (screener, backtest, aplikasi) tidak perlu diubah saat pindah
penyedia — cukup set environment variable.

    setx SECTORS_API_KEY  "kunci-anda"      # sectors.app (Supertype)
    setx INVEZGO_API_KEY  "kunci-anda"      # invezgo.com

CATATAN KEJUJURAN: path endpoint Sectors dan Invezgo TIDAK terdokumentasi publik
tanpa akun berbayar. Yang terkonfirmasi hanya base URL dan mekanisme auth. Karena
itu tiap provider punya metode `probe()` yang mencoba beberapa kandidat path
terhadap API sungguhan dan melaporkan mana yang hidup — supaya integrasi
diverifikasi terhadap kenyataan, bukan terhadap tebakan saya.

Jalankan: python -m idxquant.providers
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pandas as pd
import requests

from .data import fetch_one as _yahoo_fetch

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


@dataclass
class ProbeResult:
    provider: str
    configured: bool
    reachable: bool = False
    detail: str = ""
    working_paths: list[str] = field(default_factory=list)


class Provider:
    name = "base"
    needs_key = False

    def configured(self) -> bool:
        return True

    def daily(self, ticker: str, rng: str = "5y") -> pd.DataFrame | None:
        raise NotImplementedError

    def intraday(self, ticker: str, interval: str = "5m",
                 rng: str = "1d") -> pd.DataFrame | None:
        raise NotImplementedError

    def probe(self) -> ProbeResult:
        raise NotImplementedError


# ---------------------------------------------------------------- Yahoo
class YahooProvider(Provider):
    """Default. Gratis, tanpa key, delay ~10-20 menit. Terbukti bekerja."""

    name = "yahoo"

    SPARK = "https://query1.finance.yahoo.com/v7/finance/spark"
    SPARK_MAX = 20          # >20 simbol -> HTTP 400 (diverifikasi 30 Jul 2026)

    def daily(self, ticker, rng="5y"):
        return _yahoo_fetch(ticker, rng=rng, interval="1d")

    def intraday(self, ticker, interval="5m", rng="1d"):
        return _yahoo_fetch(ticker, rng=rng, interval=interval)

    def pulse(self, tickers: list[str], interval: str = "5m",
              rng: str = "1d") -> dict[str, pd.Series]:
        """Ambil deret harga penutupan banyak ticker sekaligus (endpoint spark).

        HANYA berisi `close` — tanpa OHLC/volume. Dipakai sebagai saringan tahap-1
        yang cepat: 20 ticker per request, ~0,4 detik, dibanding ~0,6 detik PER
        ticker lewat endpoint chart.
        """
        out: dict[str, pd.Series] = {}
        syms = [t if t.startswith("^") else f"{t}.JK" for t in tickers]
        sess = requests.Session()
        try:
            for i in range(0, len(syms), self.SPARK_MAX):
                chunk = syms[i:i + self.SPARK_MAX]
                try:
                    r = sess.get(self.SPARK, headers={"User-Agent": UA},
                                 params={"symbols": ",".join(chunk),
                                         "range": rng, "interval": interval},
                                 timeout=25)
                    if r.status_code != 200:
                        continue
                    for item in (r.json().get("spark", {}).get("result") or []):
                        sym = item.get("symbol", "")
                        resp = (item.get("response") or [None])[0]
                        if not resp or not resp.get("timestamp"):
                            continue
                        closes = ((resp.get("indicators") or {}).get("quote")
                                  or [{}])[0].get("close") or []
                        idx = pd.to_datetime(resp["timestamp"], unit="s", utc=True)
                        idx = idx.tz_convert("Asia/Jakarta").tz_localize(None)
                        s = pd.Series(closes, index=idx, dtype="float64").dropna()
                        if len(s):
                            out[sym.replace(".JK", "")] = s
                except Exception:                                  # noqa: BLE001
                    continue
        finally:
            sess.close()
        return out

    def probe(self):
        df = self.intraday("BBCA", "5m", "1d")
        ok = df is not None and len(df) > 5
        return ProbeResult("yahoo", True, ok,
                           f"{len(df)} bar 5m untuk BBCA" if ok else "tidak ada data",
                           ["/v8/finance/chart/{sym}"])


# ---------------------------------------------------------------- Sectors.app
class SectorsProvider(Provider):
    """sectors.app (Supertype). Base & auth terkonfirmasi; path perlu diverifikasi.

    Auth: header `Authorization: <kunci mentah>` (bukan Bearer).
    """

    name = "sectors"
    needs_key = True
    BASE = "https://api.sectors.app/v1"

    # Kandidat path untuk di-probe. Yang hidup akan dilaporkan.
    CANDIDATES = [
        "/subsectors/", "/sectors/", "/companies/",
        "/daily/{sym}/", "/company/report/{sym}/",
        "/index/", "/most-traded/",
    ]

    def __init__(self, key: str | None = None):
        self.key = key or os.getenv("SECTORS_API_KEY", "")

    def configured(self):
        return bool(self.key)

    def _get(self, path: str, **params):
        r = requests.get(self.BASE + path,
                         headers={"Authorization": self.key, "User-Agent": UA},
                         params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def daily(self, ticker, rng="5y"):
        if not self.configured():
            return None
        sym = ticker.replace(".JK", "")
        try:
            js = self._get(f"/daily/{sym}/")
            return _frame_from_records(js)
        except Exception:
            return None

    def intraday(self, ticker, interval="5m", rng="1d"):
        # Sectors berfokus pada data harian/fundamental; intraday belum terkonfirmasi.
        return None

    def probe(self):
        if not self.configured():
            return ProbeResult("sectors", False, detail="SECTORS_API_KEY belum diset")
        live, err = [], ""
        for p in self.CANDIDATES:
            path = p.replace("{sym}", "BBCA")
            try:
                r = requests.get(self.BASE + path,
                                 headers={"Authorization": self.key, "User-Agent": UA},
                                 timeout=15)
                if r.status_code == 200:
                    live.append(path)
                elif r.status_code in (401, 403):
                    err = f"HTTP {r.status_code} — kunci ditolak"
                    break
            except Exception as e:                                # noqa: BLE001
                err = str(e)
        return ProbeResult("sectors", True, bool(live),
                           err or f"{len(live)} path merespons 200", live)


# ---------------------------------------------------------------- Invezgo
class InvezgoProvider(Provider):
    """invezgo.com. Realtime IDX + broker summary + foreign flow — paling relevan
    untuk scalping. Base URL terkonfirmasi; nama header auth TIDAK dipublikasikan,
    jadi probe mencoba beberapa varian.

    Metode SDK yang terdokumentasi: getStockList, getIntradayData(code, 'RG'),
    getIntradayChart, getBrokerSummaryStock, getTopRitel(date), getTopForeign,
    getIndexList, getCalendar. 'RG' = papan Reguler IDX.
    """

    name = "invezgo"
    needs_key = True
    BASE = "https://api.invezgo.com"

    AUTH_STYLES = [
        ("Authorization", "{k}"),
        ("Authorization", "Bearer {k}"),
        ("X-API-Key", "{k}"),
        ("x-api-key", "{k}"),
    ]
    CANDIDATES = [
        "/v1/analysis/stock-list", "/analysis/stock-list", "/v1/stock/list",
        "/v1/analysis/intraday", "/v1/analysis/index-list",
    ]

    def __init__(self, key: str | None = None):
        self.key = key or os.getenv("INVEZGO_API_KEY", "")
        self.auth_header = os.getenv("INVEZGO_AUTH_HEADER", "Authorization")
        self.auth_fmt = os.getenv("INVEZGO_AUTH_FORMAT", "{k}")

    def configured(self):
        return bool(self.key)

    def _headers(self):
        return {self.auth_header: self.auth_fmt.format(k=self.key), "User-Agent": UA}

    def _get(self, path, **params):
        r = requests.get(self.BASE + path, headers=self._headers(),
                         params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def daily(self, ticker, rng="5y"):
        return None          # belum terverifikasi — jangan pura-pura bisa

    def intraday(self, ticker, interval="5m", rng="1d"):
        if not self.configured():
            return None
        sym = ticker.replace(".JK", "")
        for path in ("/v1/analysis/intraday", "/analysis/intraday"):
            try:
                js = self._get(path, code=sym, type="RG")
                df = _frame_from_records(js)
                if df is not None and len(df):
                    return df
            except Exception:
                continue
        return None

    def probe(self):
        if not self.configured():
            return ProbeResult("invezgo", False, detail="INVEZGO_API_KEY belum diset")
        for hname, hfmt in self.AUTH_STYLES:
            live = []
            for path in self.CANDIDATES:
                try:
                    r = requests.get(self.BASE + path,
                                     headers={hname: hfmt.format(k=self.key), "User-Agent": UA},
                                     params={"code": "BBCA", "type": "RG"}, timeout=15)
                    if r.status_code == 200:
                        live.append(path)
                except Exception:
                    continue
            if live:
                return ProbeResult(
                    "invezgo", True, True,
                    f"auth berhasil dengan header '{hname}: {hfmt}' — "
                    f"set INVEZGO_AUTH_HEADER={hname} dan INVEZGO_AUTH_FORMAT='{hfmt}'",
                    live)
        return ProbeResult("invezgo", True, False,
                           "tidak ada kombinasi auth/path yang merespons 200 — "
                           "cek dokumentasi di https://api.invezgo.com/documentation")


def _frame_from_records(js) -> pd.DataFrame | None:
    """Normalisasi respons JSON apa pun ke OHLCV berindeks waktu."""
    rows = js.get("data", js) if isinstance(js, dict) else js
    if not isinstance(rows, list) or not rows:
        return None
    df = pd.DataFrame(rows)
    tcol = next((c for c in ("date", "datetime", "time", "timestamp", "trade_date")
                 if c in df.columns), None)
    if tcol is None:
        return None
    df[tcol] = pd.to_datetime(df[tcol], errors="coerce", utc=False)
    df = df.dropna(subset=[tcol]).set_index(tcol).sort_index()
    ren = {}
    for want, opts in (("open", ("open", "o", "open_price")),
                       ("high", ("high", "h", "high_price")),
                       ("low", ("low", "l", "low_price")),
                       ("close", ("close", "c", "close_price", "last")),
                       ("volume", ("volume", "v", "vol"))):
        for o in opts:
            if o in df.columns:
                ren[o] = want
                break
    df = df.rename(columns=ren)
    need = {"open", "high", "low", "close", "volume"}
    if not need.issubset(df.columns):
        return None
    return df[list(need)].astype(float)


PROVIDERS = {"yahoo": YahooProvider, "sectors": SectorsProvider, "invezgo": InvezgoProvider}


def get_provider(name: str | None = None) -> Provider:
    """Pilih penyedia. Prioritas: argumen > IDX_PROVIDER > key yang tersedia > Yahoo."""
    name = name or os.getenv("IDX_PROVIDER", "").lower()
    if name in PROVIDERS:
        p = PROVIDERS[name]()
        if p.configured():
            return p
    for cand in ("invezgo", "sectors"):
        p = PROVIDERS[cand]()
        if p.configured():
            return p
    return YahooProvider()


def probe_all() -> list[ProbeResult]:
    return [PROVIDERS[n]().probe() for n in PROVIDERS]


if __name__ == "__main__":
    print("=" * 74)
    print("PROBE PENYEDIA DATA IDX")
    print("=" * 74)
    for r in probe_all():
        mark = "OK  " if r.reachable else ("--  " if not r.configured else "GAGAL")
        print(f"\n[{mark}] {r.provider}")
        print(f"       terkonfigurasi : {'ya' if r.configured else 'tidak'}")
        print(f"       terhubung      : {'ya' if r.reachable else 'tidak'}")
        print(f"       keterangan     : {r.detail}")
        if r.working_paths:
            for p in r.working_paths:
                print(f"         - {p}")
    print(f"\nPenyedia aktif saat ini: {get_provider().name}")
