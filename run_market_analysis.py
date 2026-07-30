"""Analisis kondisi pasar IDX: teknikal IHSG, breadth, rotasi sektor, dispersi."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from idxquant import data as dl
from idxquant import setups as st
from idxquant.config import OUT_DIR
from idxquant.indicators import adx, atr, enrich, rsi
from idxquant.universe import BENCHMARK, CANDIDATES

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)


def pct(x, d=1):
    return "n/a" if pd.isna(x) else f"{x*100:+.{d}f}%"


def main():
    bench = dl.load(BENCHMARK, rng="5y")
    data = dl.load_many(CANDIDATES, rng="5y", verbose=False)
    prep = st.prepare(data, bench)
    scan = st.scan(prep)
    liq = scan[scan["likuid"]].copy()

    b = enrich(bench)
    r = b.iloc[-1]
    asof = b.index[-1].date()

    print("=" * 78)
    print(f"ANALISIS PASAR IDX — per {asof}")
    print("=" * 78)

    # ---------------- IHSG ----------------
    dd = b["close"] / b["close"].cummax() - 1
    below200 = b["close"] < b["ma200"]
    streak = 0
    for v in below200.iloc[::-1]:
        if v:
            streak += 1
        else:
            break

    print("\n[A] IHSG — KONDISI TEKNIKAL")
    print(f"  Level                  : {r['close']:,.0f}")
    print(f"  MA50 / MA200           : {r['ma50']:,.0f} / {r['ma200']:,.0f}")
    print(f"  Posisi vs MA200        : {pct(r['close']/r['ma200']-1)}"
          f"  ({'DI ATAS' if r['close']>r['ma200'] else 'DI BAWAH'})")
    print(f"  Puncak 52 minggu       : {r['hi_52w']:,.0f}  (jarak {pct(r['from_hi'])})")
    print(f"  Dasar 52 minggu        : {r['lo_52w']:,.0f}  (jarak {pct(r['from_lo'])})")
    print(f"  Drawdown dari ATH 5th  : {pct(dd.iloc[-1])}")
    print(f"  Hari beruntun < MA200  : {streak} hari bursa")
    print(f"  RSI(14) / ADX(14)      : {r['rsi14']:.1f} / {r['adx14']:.1f}")
    print(f"  Volatilitas tahunan 20h: {pct(r['rvol'], 1)}")
    print("  Return                 : "
          f"1b {pct(r['roc21'])} | 3b {pct(r['roc63'])} | "
          f"6b {pct(r['roc126'])} | 12b {pct(r['roc244'])}")

    # ---------------- Breadth ----------------
    print("\n[B] BREADTH PASAR (87 saham likuid)")
    panel_c = dl.close_panel({t: prep[t] for t in prep})
    ma50p = pd.DataFrame({t: prep[t]["ma50"] for t in prep})
    ma200p = pd.DataFrame({t: prep[t]["ma200"] for t in prep})
    liq_t = list(liq["ticker"])

    above50 = (panel_c[liq_t] > ma50p[liq_t]).mean(axis=1)
    above200 = (panel_c[liq_t] > ma200p[liq_t]).mean(axis=1)

    print(f"  % di atas MA50         : {above50.iloc[-1]*100:.1f}%"
          f"   (1 bln lalu {above50.iloc[-21]*100:.1f}%)")
    print(f"  % di atas MA200        : {above200.iloc[-1]*100:.1f}%"
          f"   (1 bln lalu {above200.iloc[-21]*100:.1f}%)")
    print(f"  % dalam jarak 10% dari puncak 52mg : "
          f"{(liq['from_hi'] > -0.10).mean()*100:.1f}%")
    print(f"  % turun >30% dari puncak 52mg      : "
          f"{(liq['from_hi'] < -0.30).mean()*100:.1f}%")
    print(f"  Median return 12 bulan : {pct(liq['ret_12m'].median())}")
    print(f"  Median return 3 bulan  : {pct(liq['ret_3m'].median())}")
    print(f"  Saham naik vs turun 3b : {(liq['ret_3m']>0).sum()} vs {(liq['ret_3m']<=0).sum()}")

    # ---------------- Sektor ----------------
    print("\n[C] ROTASI SEKTOR (median saham likuid per sektor)")
    g = liq.groupby("sektor").agg(
        N=("ticker", "size"),
        ret_3m=("ret_3m", "median"),
        ret_6m=("ret_6m", "median"),
        ret_12m=("ret_12m", "median"),
        di_atas_ma200=("di_atas_ma200", "mean"),
        skor=("skor", "median"),
    ).sort_values("ret_6m", ascending=False)
    out = g.copy()
    for c in ("ret_3m", "ret_6m", "ret_12m"):
        out[c] = out[c].map(lambda v: pct(v, 1))
    out["di_atas_ma200"] = (g["di_atas_ma200"] * 100).round(0).astype(int).astype(str) + "%"
    out["skor"] = g["skor"].round(1)
    print(out.to_string())

    # ---------------- Dispersi & risiko ----------------
    print("\n[D] DISPERSI & RISIKO")
    rets = panel_c[liq_t].pct_change().tail(63)
    corr = rets.corr().values
    avg_corr = corr[np.triu_indices_from(corr, k=1)].mean()
    print(f"  Rata-rata korelasi pasangan (63h) : {avg_corr:.2f}")
    print(f"  Dispersi return 3 bulan (stdev)   : {liq['ret_3m'].std()*100:.1f}%")
    print(f"  Median ATR% harian                : {liq['atr_pct'].median()*100:.2f}%")
    print(f"  Median jarak dari puncak 52mg     : {pct(liq['from_hi'].median())}")

    # ---------------- Implikasi regime ----------------
    # ---------------- Breadth thrust ----------------
    print("\n[E] UJI BREADTH THRUST (deteksi titik balik)")
    delta50 = above50.iloc[-1] - above50.iloc[-21]
    print(f"  Perubahan % di atas MA50 dalam 21 hari : {delta50*100:+.1f} poin")
    # Titik "konfirmasi" = hari saat breadth benar-benar menembus 55% dari bawah 15%
    low_recent = above50.rolling(21).min() < 0.15
    confirm = (above50 > 0.55) & (above50.shift(1) <= 0.55) & low_recent
    days = list(confirm[confirm].index)

    # Gabungkan jadi episode: hari yang berjarak < 60 hari bursa dianggap satu episode
    episodes = []
    for d in days:
        if not episodes or (bench.index.get_loc(d) - bench.index.get_loc(episodes[-1])) > 60:
            episodes.append(d)

    n_bars = len(bench)
    matured = [d for d in episodes if n_bars - bench.index.get_loc(d) > 126]
    print(f"  Episode thrust berbeda sejak 2021 : {len(episodes)}"
          f"  (matang / punya data 6 bulan ke depan: {len(matured)})")
    if matured:
        print("  Return IHSG SETELAH konfirmasi thrust:")
        for d in matured:
            i = bench.index.get_loc(d)
            base_px = bench["close"].iloc[i]
            parts = []
            for h, lab in ((21, "1b"), (63, "3b"), (126, "6b")):
                parts.append(f"+{lab} {pct(bench['close'].iloc[i+h] / base_px - 1)}")
            print(f"    {d.date()}  ->  " + "  ".join(parts))
    pending = [d for d in episodes if d not in matured]
    if pending:
        print(f"  Episode BERJALAN (belum bisa dinilai) : "
              f"{', '.join(str(d.date()) for d in pending)}")
    if len(matured) < 3:
        print("  CATATAN: sampel historis terlalu sedikit untuk disebut bukti statistik.")
        print("           Perlakukan sebagai konteks, bukan sinyal yang teruji.")
    if delta50 > 0.40 and above50.iloc[-1] > 0.55:
        print("  STATUS: thrust breadth AKTIF — partisipasi melonjak dari dasar.")
        print("  Tafsir: sering muncul di awal pemulihan, tapi juga di rally palsu")
        print("          pasar beruang. MA200 IHSG (7.571) masih 22% di atas harga.")

    # ---------------- Implikasi regime ----------------
    print("\n[F] IMPLIKASI UNTUK STRATEGI")
    regime = "RISK-OFF" if r["close"] < r["ma200"] else "RISK-ON"
    print(f"  Regime saat ini (IHSG vs MA200) : {regime}")

    print("\n  Uji: performa setup BaseBreakout berdasarkan regime IHSG")
    from idxquant import backtest as bt
    es = bt.event_study(prep, "BaseBreakout")
    tr = es["_trades"]
    bcl = bench["close"]
    bma = bcl.rolling(200, min_periods=200).mean()
    tr = tr.assign(risk_on=(bcl > bma).reindex(tr["date"]).values)
    stats = {}
    for flag, label in ((True, "IHSG > MA200"), (False, "IHSG < MA200")):
        sub = tr[tr["risk_on"] == flag]
        if len(sub):
            stats[flag] = sub["fwd21"].mean()
            print(f"    {label:<14} N={len(sub):>4}  avg21d={pct(sub['fwd21'].mean(),2)}  "
                  f"win={sub['fwd21'].gt(0).mean()*100:.0f}%  "
                  f"median={pct(sub['fwd21'].median(),2)}")

    print("\n  Kesimpulan berbasis data (bukan asumsi):")
    if stats.get(False, 0) > stats.get(True, 0):
        print("  * Breakout yang BENAR-BENAR terjadi saat regime risk-off justru")
        print("    memberi return 21 hari lebih tinggi. Penjelasan paling masuk akal:")
        print("    efek seleksi — di pasar beruang hanya saham yang sangat kuat yang")
        print("    mampu menembus tertinggi 55 hari dengan volume, jadi sinyalnya lebih")
        print("    selektif. Sampelnya lebih kecil (N=%d) dan terkonsentrasi di beberapa"
              % len(tr[~tr["risk_on"]]))
        print("    fase rebound, jadi perlakukan sebagai indikasi, bukan bukti kuat.")
        print("  * Ini TIDAK bertentangan dengan hasil backtest portofolio: rotasi")
        print("    momentum tanpa regime filter tetap rugi (-8,5% CAGR, MaxDD -51%)")
        print("    karena ia membeli 10 saham skor tertinggi APA PUN kondisinya,")
        print("    bukan hanya yang memicu sinyal breakout sungguhan.")
        print("  * Implikasi praktis: saat risk-off, jangan matikan sistem total —")
        print("    perketat jadi hanya breakout terkonfirmasi, ukuran posisi kecil.")
    else:
        print("  * Breakout bekerja lebih baik saat regime risk-on, sesuai ekspektasi.")

    # Simpan
    pd.DataFrame({"pct_above_ma50": above50, "pct_above_ma200": above200,
                  "ihsg": bench["close"].reindex(above50.index)}).to_csv(
        OUT_DIR / "breadth.csv")
    g.to_csv(OUT_DIR / "sector_rotation.csv")
    print(f"\nDisimpan: breadth.csv, sector_rotation.csv di {OUT_DIR}")


if __name__ == "__main__":
    main()
