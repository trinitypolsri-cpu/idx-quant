"""Monte Carlo atas distribusi trade nyata dari backtest.

Pertanyaan yang dijawab: hasil backtest yang kita lihat itu keahlian sistem, atau
kebetulan urutan trade yang beruntung?

Caranya bootstrap — mengacak ulang 498 trade hasil backtest ribuan kali. Kalau
sebagian besar jalur alternatif jauh lebih buruk dari yang teramati, berarti hasil
tunggal itu terletak di persentil yang menguntungkan dan tidak boleh dipercaya
sebagai ekspektasi.

Ini relevan justru karena distribusi trade-nya berekor gemuk: median trade negatif,
sementara 10 trade terbaik menyumbang 269% total PnL. Sistem seperti itu sangat
sensitif terhadap urutan dan kehadiran segelintir pemenang.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def bootstrap(returns: np.ndarray, n_sim: int = 10000, n_trade: int | None = None,
              seed: int = 42, bobot: float = 0.10) -> dict:
    """Acak ulang return per-trade untuk membangun distribusi hasil.

    `bobot` WAJIB mencerminkan ukuran posisi sebenarnya. Strategi ini memegang 10
    posisi paralel berbobot sama, jadi tiap trade hanya menggerakkan ~10% ekuitas.
    Menggandakan return per-trade pada bobot penuh (bobot=1.0) akan melebih-lebihkan
    baik compounding maupun drawdown secara ekstrem — ekuitas akhir dan MaxDD hasilnya
    tidak akan cocok dengan kurva ekuitas backtest.
    """
    rng = np.random.default_rng(seed)
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size == 0:
        return {}
    n = n_trade or r.size
    r = r * bobot                      # kontribusi ke ekuitas portofolio

    draws = rng.choice(r, size=(n_sim, n), replace=True)
    equity = np.cumprod(1.0 + draws, axis=1)
    terminal = equity[:, -1]

    running_max = np.maximum.accumulate(equity, axis=1)
    dd = equity / running_max - 1.0
    max_dd = dd.min(axis=1)

    obs_equity = np.cumprod(1.0 + r)
    obs_terminal = float(obs_equity[-1])
    obs_dd = float((obs_equity / np.maximum.accumulate(obs_equity) - 1).min())

    pct = lambda a, q: float(np.percentile(a, q))                  # noqa: E731
    return {
        "n_trade": int(n), "n_sim": int(n_sim),
        "obs_terminal": obs_terminal, "obs_maxdd": obs_dd,
        "obs_persentil": float((terminal < obs_terminal).mean() * 100),
        "terminal": {q: pct(terminal, q) for q in (5, 25, 50, 75, 95)},
        "maxdd": {q: pct(max_dd, q) for q in (5, 25, 50, 75, 95)},
        "p_rugi": float((terminal < 1.0).mean() * 100),
        "p_dd_lebih_30": float((max_dd < -0.30).mean() * 100),
        "p_dd_lebih_50": float((max_dd < -0.50).mean() * 100),
        "bobot": bobot,
        "rata_trade": float(r.mean() / bobot), "median_trade": float(np.median(r) / bobot),
        "menang": float((r > 0).mean() * 100),
    }


def risk_of_ruin(returns: np.ndarray, risiko_per_trade: list[float],
                 ambang_ruin: float = -0.50, n_sim: int = 5000,
                 n_trade: int = 250, seed: int = 7) -> pd.DataFrame:
    """Probabilitas ekuitas jatuh melewati ambang, untuk beberapa ukuran posisi.

    `risiko_per_trade` adalah fraksi ekuitas yang dipertaruhkan tiap trade; return
    per-trade diskalakan proporsional terhadapnya.
    """
    rng = np.random.default_rng(seed)
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    base = float(np.abs(r).mean()) or 1.0

    rows = []
    for f in risiko_per_trade:
        skala = f / base
        draws = rng.choice(r, size=(n_sim, n_trade), replace=True) * skala
        draws = np.clip(draws, -0.95, None)          # tidak bisa rugi >100% per trade
        eq = np.cumprod(1.0 + draws, axis=1)
        ruin = (eq.min(axis=1) <= (1 + ambang_ruin)).mean() * 100
        rows.append({
            "risiko_per_trade": f,
            "p_ruin": round(float(ruin), 1),
            "median_akhir": round(float(np.median(eq[:, -1])), 3),
            "p5_akhir": round(float(np.percentile(eq[:, -1], 5)), 3),
            "p95_akhir": round(float(np.percentile(eq[:, -1], 95)), 3),
        })
    return pd.DataFrame(rows)


def kelly(returns: np.ndarray) -> dict:
    """Fraksi Kelly dari distribusi menang/kalah teramati."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    wins, losses = r[r > 0], r[r <= 0]
    if wins.size == 0 or losses.size == 0:
        return {}
    p = wins.size / r.size
    W = float(wins.mean())
    L = float(abs(losses.mean()))
    b = W / L if L else np.inf
    f = p - (1 - p) / b if b not in (0, np.inf) else p
    return {"p_menang": round(p * 100, 1), "avg_menang": round(W * 100, 2),
            "avg_kalah": round(L * 100, 2), "payoff": round(b, 2),
            "kelly_penuh": round(f * 100, 1), "kelly_seperempat": round(f * 25, 1)}


def sensitivitas_pemenang(returns: np.ndarray, buang: list[int],
                          bobot: float = 0.10) -> pd.DataFrame:
    """Bagaimana hasil berubah bila N trade terbaik dihapus — uji kerapuhan.

    `bobot` sama artinya seperti di `bootstrap`: kontribusi tiap trade ke ekuitas.
    """
    r = np.sort(np.asarray(returns, dtype=float))[::-1]
    rows = []
    for k in buang:
        sub = r[k:] if k < r.size else np.array([])
        if sub.size == 0:
            continue
        rows.append({
            "buang_n_terbaik": k,
            "total_return": round(float(np.prod(1 + sub * bobot) - 1) * 100, 1),
            "rata_trade": round(float(sub.mean()) * 100, 3),
            "sisa_trade": int(sub.size),
        })
    return pd.DataFrame(rows)
