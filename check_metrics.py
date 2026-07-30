"""Cek kejujuran angka: pisahkan periode warm-up MA200 dari periode aktif."""
import numpy as np
import pandas as pd

from idxquant.backtest import metrics

c = pd.read_csv("output/equity_curve.csv", index_col=0, parse_dates=True)
first = c.index[c["exposure"] > 0][0]
print("Bar pertama punya posisi:", first.date())
print()

for lab, seg in (("Penuh 5 thn (termasuk warm-up MA200)", c),
                 ("Sejak posisi pertama (periode aktif)", c[c.index >= first])):
    s = metrics(seg["strategi"], seg["exposure"])
    b = metrics(seg["ihsg"])
    print(lab + ":")
    print(f"  Strategi : CAGR {s['CAGR']*100:6.2f}%  MaxDD {s['MaxDD']*100:7.2f}%  "
          f"Sharpe {s['Sharpe']:5.2f}  Expo {s['Exposure']*100:3.0f}%  "
          f"TotalRet {s['TotalReturn']*100:6.1f}%")
    print(f"  IHSG     : CAGR {b['CAGR']*100:6.2f}%  MaxDD {b['MaxDD']*100:7.2f}%  "
          f"Sharpe {b['Sharpe']:5.2f}            TotalRet {b['TotalReturn']*100:6.1f}%")
    print()

tr = pd.read_csv("output/trades.csv", parse_dates=["entry_date", "exit_date"])
print("Trade pertama:", tr["entry_date"].min().date(), "| total trade:", len(tr))
p = np.percentile(tr["ret"], [10, 50, 90, 100]) * 100
print("Return per trade : p10 %.1f%%  median %.1f%%  p90 %.1f%%  maks %.1f%%" % tuple(p))
print("Kontribusi 10 trade terbaik ke total PnL : %.0f%%"
      % (tr.nlargest(10, "pnl")["pnl"].sum() / tr["pnl"].sum() * 100))
print("Alasan keluar:")
print(tr["reason"].value_counts().to_string())

# Berapa lama strategi berada di cash total?
flat = (c["exposure"] <= 0.01).mean()
flat_active = (c[c.index >= first]["exposure"] <= 0.01).mean()
print(f"\nWaktu 100% cash: {flat*100:.0f}% dari 5 tahun penuh, "
      f"{flat_active*100:.0f}% dari periode aktif")
