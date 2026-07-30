"""Server aplikasi screener IDX — FastAPI + UI satu halaman."""

from __future__ import annotations

import sys
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.engine import ENGINE                                   # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    ENGINE.refresh_async(use_cache=True)     # muat dari cache saat start
    yield


app = FastAPI(title="IDX Screener", docs_url="/api/docs", lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    return JSONResponse(ENGINE.overview())


@app.post("/api/refresh")
def refresh(full: bool = Query(False, description="True = abaikan cache, tarik data baru")):
    if ENGINE.busy:
        return JSONResponse({"ok": False, "pesan": "refresh sedang berjalan",
                             "status": ENGINE.status, "progress": ENGINE.progress})
    ENGINE.refresh_async(use_cache=not full)
    return JSONResponse({"ok": True, "pesan": "refresh dimulai"})


@app.get("/api/screen")
def screen(setup: str = "", sector: str = "", min_skor: float = 0,
           min_turnover: float = 5.0, only_above_ma200: bool = False,
           sort: str = "skor", limit: int = 300):
    return JSONResponse({
        "rows": ENGINE.screen(setup=setup, sector=sector, min_skor=min_skor,
                              min_turnover=min_turnover,
                              only_above_ma200=only_above_ma200,
                              sort=sort, limit=limit)
    })


@app.get("/api/sectors")
def sectors():
    return JSONResponse({"rows": ENGINE.sectors()})


@app.get("/api/setups")
def setups():
    return JSONResponse({"rows": ENGINE.setup_counts()})


@app.get("/api/scalping")
def scalping(top: int = 40, interval: str = "5m"):
    return JSONResponse(ENGINE.scalping(top=top, interval=interval))


@app.get("/api/providers")
def providers():
    from idxquant.providers import get_provider, probe_all
    return JSONResponse({
        "aktif": get_provider().name,
        "daftar": [{"nama": r.provider, "terkonfigurasi": r.configured,
                    "terhubung": r.reachable, "keterangan": r.detail,
                    "path": r.working_paths} for r in probe_all()],
    })


@app.get("/api/levels/{ticker}")
def levels(ticker: str, modal: float | None = None, pivot: str = "klasik"):
    from idxquant import data as dl
    from idxquant.levels import analisa_level
    t = ticker.upper()
    d = ENGINE.prepared.get(t)
    if d is None:
        d = dl.load(t, rng="5y")
    if d is None or len(d) < 30:
        return JSONResponse({"error": "data tidak cukup"}, status_code=404)
    return JSONResponse(analisa_level(d, metode_pivot=pivot, modal=modal))


@app.get("/api/chart/{ticker}")
def chart(ticker: str, rng: str = "6mo", interval: str = "1d"):
    return JSONResponse(ENGINE.chart(ticker.upper(), rng=rng, interval=interval))


if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8848
    print(f"\n  IDX Screener -> http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
