"""Parameter pasar & biaya transaksi khas IDX."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
DATA_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

# --- Biaya transaksi (retail broker Indonesia, konservatif) ---
FEE_BUY = 0.0015          # 0.15% komisi beli
FEE_SELL = 0.0025         # 0.25% jual (komisi + PPh final 0.1%)
SLIPPAGE = 0.0015         # 0.15% per sisi, wajar untuk mid-cap IDX
LOT_SIZE = 100            # 1 lot = 100 lembar

# --- Filter likuiditas ---
MIN_PRICE = 100           # hindari saham gocap/nyangkut di Rp50
MIN_TURNOVER_IDR = 5e9    # median nilai transaksi harian >= Rp5 miliar
MIN_HISTORY_DAYS = 300    # butuh histori cukup untuk MA200

# --- Auto Rejection (ARA/ARB) berdasarkan tier harga ---
def ar_limit(price: float) -> float:
    """Batas auto-rejection simetris IDX (fraksi, bukan persen)."""
    if price < 200:
        return 0.35
    if price < 5000:
        return 0.25
    return 0.20


# --- Fraksi harga (tick size) ---
def tick_size(price: float) -> int:
    if price < 200:
        return 1
    if price < 500:
        return 2
    if price < 2000:
        return 5
    if price < 5000:
        return 10
    return 25


def round_to_tick(price: float) -> float:
    t = tick_size(price)
    return round(price / t) * t


TRADING_DAYS = 244        # rata-rata hari bursa IDX per tahun
RISK_FREE = 0.0575        # proxy BI-Rate / SBN jangka pendek
